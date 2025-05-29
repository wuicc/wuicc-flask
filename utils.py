import base64
import json
from flask import jsonify
from models import db, Game, User, UserData, RefreshLog
from datetime import datetime


def decode_request_data(encoded_data):
    """解码Base64编码的请求数据"""
    try:
        # 添加可能的缺失填充
        padding = len(encoded_data) % 4
        if padding:
            encoded_data += "=" * (4 - padding)

        # 解码Base64
        decoded_bytes = base64.urlsafe_b64decode(encoded_data)
        return json.loads(decoded_bytes.decode("utf-8"))

    except Exception as e:
        raise ValueError(f"Failed to decode data: {str(e)}")


def make_json_response(code=200, message="success", data=None):
    return jsonify({"code": code, "message": message, "data": data})


def update_game_refresh_time(game_id, success=True):
    game = Game.query.filter_by(game_id=game_id).first()
    if game:
        game.last_refresh = datetime.utcnow()

        log = RefreshLog(
            game_id=game_id,
            language="all",
            refresh_time=datetime.utcnow(),
            success=1 if success else 0,
        )
        db.session.add(log)
        db.session.commit()
        return True
    return False


def get_user_config(user_id):
    user_data = UserData.query.filter_by(user_id=user_id).first()
    if user_data:
        return json.loads(user_data.config_json)
    return {}


def update_user_config(user_id, config):
    user_data = UserData.query.filter_by(user_id=user_id).first()
    if not user_data:
        user_data = UserData(user_id=user_id)
        db.session.add(user_data)

    user_data.config_json = json.dumps(config)
    db.session.commit()
    return True
