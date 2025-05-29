from flask import Flask, request, jsonify
import os
import json
import base64
from werkzeug.exceptions import MethodNotAllowed
from datetime import datetime
from models import db, Game, User
from ann_model import (
    get_announcement_model,
    init_announcement_tables,
    create_refresh_tables,
)
from utils import decode_request_data, make_json_response
from auth import login, logout, logout_all, token_required
from services.announcement_service import AnnouncementService
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.json.ensure_ascii = False
app.config.from_object("config")
GAME_JSON_FILE = os.path.join(os.path.dirname(__file__), "data", "games.json")
LANG_JSON_FILE = os.path.join(os.path.dirname(__file__), "data", "languages.json")
announcement_service = AnnouncementService()


# 初始化数据库
def create_tables():
    db.create_all()
    # 初始化默认游戏
    if not Game.query.first():
        default_games = [
            {"game_id": "genshin", "name": "Genshin Impact"},
            {"game_id": "starrail", "name": "Honkai: Star Rail"},
            {"game_id": "zenless", "name": "Zenless Zone Zero"},
            {"game_id": "wuthering", "name": "Wuthering Waves"},
        ]
        for game in default_games:
            db.session.add(Game(**game))
        db.session.commit()

    game_ids = [game.game_id for game in Game.query.all()]
    init_announcement_tables()
    create_refresh_tables(game_ids)


def load_supported_languages():
    try:
        with open(LANG_JSON_FILE, "r", encoding="utf-8") as f:
            languages = json.load(f)["languages"]
        return {lang.lower(): lang for lang in languages}
    except Exception as e:
        print(f"Error loading languages.json: {str(e)}")
        return {"en": "en", "zh-hans": "zh-Hans"}


SUPPORTED_LANGUAGES = load_supported_languages()


@app.route("/api/announcements", methods=["GET"])
def get_announcements():
    """
    Get game announcements API
    Parameters:
    - lang: Language code (e.g. zh-CN) [required]
    - games: Dot-separated game IDs (e.g. genshin.starrail) [required]
    - {game_id}_subgroup: Dot-separated activity types (e.g. genshin_subgroup=version.gacha) [optional]

    Error Codes:
    - 400: Bad Request (invalid parameters)
    - 404: Not Found (requested resource not available)
    - 500: Internal Server Error
    """
    try:
        # Validate language parameter
        lang = request.args.get("lang")
        if not lang:
            return make_json_response(
                code=400,
                message="Missing required parameter: lang",
            )

        normalized_lang = SUPPORTED_LANGUAGES.get(lang.lower())
        if not normalized_lang:
            valid_langs = ", ".join(sorted(SUPPORTED_LANGUAGES.values()))
            return make_json_response(
                code=400,
                message=f"Unsupported language: '{lang}'. Supported languages: {valid_langs}",
            )

        # Validate games parameter
        games_param = request.args.get("games")
        if not games_param:
            return make_json_response(
                code=400,
                message="Missing required parameter: games",
            )

        games = [
            game.strip().lower() for game in games_param.split(".") if game.strip()
        ]
        if not games:
            return make_json_response(
                code=400,
                message="Empty game list provided",
            )

        # Validate game IDs
        valid_games = {
            game.game_id for game in Game.query.filter(Game.game_id.in_(games)).all()
        }
        invalid_games = set(games) - valid_games

        if invalid_games:
            return make_json_response(
                code=400,
                message=f"Invalid game IDs: {', '.join(invalid_games)}",
                data={"valid_games": list(valid_games)},
            )

        # Parse activity subgroups
        activities_map = {}
        for game_id in games:
            subgroup_key = f"{game_id}_subgroup"
            subgroup_param = request.args.get(subgroup_key, "")

            activity_types = [
                t.strip().lower() for t in subgroup_param.split(".") if t.strip()
            ]

            if activity_types:
                # Validate activity types if provided
                valid_types = {"version", "event", "gacha", "update", "maintenance"}
                invalid_types = set(activity_types) - valid_types

                if invalid_types:
                    return make_json_response(
                        code=400,
                        message=f"Invalid activity types for {game_id}: {', '.join(invalid_types)}",
                        data={"valid_types": list(valid_types)},
                    )

                activities_map[game_id] = activity_types

        # Fetch announcements
        result = []
        for game_id in games:
            try:
                # print("now in app,go to service:",game_id)
                announcements = announcement_service.get_announcements(
                    game_id, normalized_lang
                )

                if not announcements:
                    continue  # Skip if no announcements found

                # Apply activity type filtering
                activity_types = activities_map.get(game_id, [])
                if activity_types:
                    announcements = [
                        ann
                        for ann in announcements
                        if ann.get("type") in activity_types
                    ]

                result.append({"game_id": game_id, "announcements": announcements})

            except Exception as e:
                # Log but continue with other games
                app.logger.error(f"Error processing {game_id}: {str(e)}", exc_info=True)
                continue

        if not result:
            return make_json_response(
                code=404,
                message="No announcements found for the specified criteria",
            )

        return make_json_response(data={"announcements": result})

    except ValueError as ve:
        return make_json_response(
            code=400,
            message=f"Invalid parameter value: {str(ve)}",
        )
    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return make_json_response(
            code=500,
            message="Internal server error",
        )


@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(500)
def handle_errors(error):
    if isinstance(error, MethodNotAllowed):
        return make_json_response(
            code=405,
            message="Method Not Allowed",
            data={"allowed_methods": error.valid_methods},
        )
    elif error.code == 404:
        return make_json_response(code=404, message="Not Found")
    else:
        return make_json_response(code=500, message="Internal Server Error")


@app.route("/api/games", methods=["GET"])
def get_games():
    try:
        # 从JSON文件加载基础游戏数据
        with open(GAME_JSON_FILE, "r", encoding="utf-8") as f:
            games_data = json.load(f)

        # 从数据库获取已启用的游戏ID
        enabled_games = {
            game.game_id: game for game in Game.query.filter_by(enabled=1).all()
        }

        # 过滤只返回启用的游戏
        filtered_games = [
            game for game in games_data["games"] if game["game_id"] in enabled_games
        ]

        return make_json_response(
            data={"games": filtered_games, "meta": games_data["meta"]}
        )

    except FileNotFoundError:
        return make_json_response(code=404, message="Game data file not found")
    except Exception as e:
        return make_json_response(code=500, message=f"Server error: {str(e)}")


@app.route("/api/auth/login", methods=["POST"])
def handle_login():
    return login()


@app.route("/api/auth/logout", methods=["POST"])
@token_required
def handle_logout(current_user):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split()[1]
    if logout(token):
        return make_json_response(message="Logged out successfully")
    return make_json_response(code=400, message="Invalid token")


@app.route("/api/auth/logout_all", methods=["POST"])
@token_required
def handle_logout_all(current_user):
    logout_all(current_user)
    return make_json_response(message="All sessions logged out")


# 受保护的路由示例
@app.route("/api/user/profile", methods=["GET"])
@token_required
def get_profile(current_user):
    return make_json_response(
        data={
            "user_id": current_user.id,
            "username": current_user.user_name,
            "nickname": current_user.user_nickname,
        }
    )


def is_plaintext_password(password):
    if not password:
        return False
    if password.startswith(("$2a$", "$2b$", "$2y$", "scrypt:")):
        return False
    if len(password) in [32, 40, 64, 128]:
        return False
    return True


def migrate_plaintext_passwords():
    users = User.query.all()
    for user in users:
        if is_plaintext_password(user.password_hash):
            print(f"Migrating password for user: {user.user_name}")
            user.set_password(user.password_hash)
    db.session.commit()


def scheduled_refresh():
    """定时刷新公告数据"""
    with app.app_context():
        announcement_service.refresh_all_games()


# 启动定时任务
scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_refresh, "cron", hour=9, minute=0)
scheduler.add_job(scheduled_refresh, "cron", hour=11, minute=10)
scheduler.add_job(scheduled_refresh, "cron", hour=16, minute=0)
scheduler.add_job(scheduled_refresh, "cron", hour=18, minute=0)
scheduler.add_job(scheduled_refresh, "cron", hour=22, minute=0)
scheduler.start()

if __name__ == "__main__":
    with app.app_context():
        db.init_app(app)
        create_tables()
        migrate_plaintext_passwords()
        init_announcement_tables()
    app.run(host="0.0.0.0", port=8182, debug=True)
