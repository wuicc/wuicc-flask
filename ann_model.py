import json
import os
import uuid
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from models import db, RefreshRecord
from flask import current_app


# Base announcement model (abstract)
class AnnouncementBase(db.Model):
    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    official_id = db.Column(db.String(32), nullable=False)
    uuid = db.Column(db.String(64), nullable=False, unique=True)
    title = db.Column(db.Text, nullable=False)
    raw_data = db.Column(db.Text)
    content = db.Column(db.Text)
    banner_img = db.Column(db.Text)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    type = db.Column(db.String(32))

    def __init__(self, **kwargs):
        super(AnnouncementBase, self).__init__(**kwargs)
        self.uuid = self.generate_uuid()

    def __repr__(self):
        return f"<Announcement {self.id}: {self.title}>"

    def generate_uuid(self):
        namespace = uuid.NAMESPACE_DNS
        name = f"{self.official_id}-{self.title}"
        return str(uuid.uuid3(namespace, name))


# Load languages from JSON file
def load_languages():
    with open("data/languages.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["languages"]


LANGUAGES = load_languages()


def load_game_ids():
    """从games.json文件加载游戏ID列表"""
    try:
        with open("data/games.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return [game["game_id"] for game in data["games"]]
    except Exception as e:
        print(f"Error loading games.json: {e}")
        # 默认返回常用游戏ID
        return ["genshin", "starrail"]


def create_announcement_tables(game_ids):
    binds = current_app.config.get("SQLALCHEMY_BINDS", {})

    for game_id in game_ids:
        if game_id not in binds:
            continue

        for lang in LANGUAGES:
            table_lang = lang.lower().replace("-", "")
            table_name = f"announcements_{game_id}_{table_lang}"

            # 检查是否已存在该模型类
            if table_name in globals():
                continue

            attrs = {
                "__tablename__": table_name,
                "__bind_key__": game_id,
            }

            try:
                model_cls = type(table_name, (AnnouncementBase,), attrs)
                globals()[table_name] = model_cls
            except Exception as e:
                current_app.logger.warning(
                    f"Failed to create table {table_name}: {str(e)}"
                )
                continue

        # 只为新表创建
        db.create_all(bind_key=game_id)


# Example initialization
def init_announcement_tables():
    """Initialize tables for all supported games"""
    game_ids = load_game_ids()  # 从JSON文件加载游戏ID
    # print("* create:", game_ids)
    create_announcement_tables(game_ids)


# Utility functions
def get_announcement_model(game_id: str, language: str):
    table_lang = language.lower().replace("-", "")
    table_name = f"announcements_{game_id}_{table_lang}"

    if table_name not in globals():
        raise ValueError(
            f"No announcement table for game {game_id} and language {language}"
        )

    return globals()[table_name]


def add_announcement(game_id: str, language: str, announcement_data: dict):
    """添加或更新公告到适当的表"""
    model = get_announcement_model(game_id, language)

    # 检查是否已存在相同UUID的公告
    existing = model.query.filter_by(uuid=announcement_data.get("uuid")).first()

    # 处理时间字段转换
    def parse_time(time_str):
        if not time_str:
            return None
        try:
            return datetime.fromisoformat(time_str)
        except (TypeError, ValueError):
            try:
                return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            except:
                return None

    if existing:
        # 如果已存在，更新所有字段
        existing.official_id = announcement_data.get("official_id")
        existing.title = announcement_data.get("title")
        existing.raw_data = json.dumps(announcement_data.get("raw_data", {}))
        existing.content = announcement_data.get("content")
        existing.banner_img = announcement_data.get("banner_img")
        existing.start_time = parse_time(announcement_data.get("start_time"))
        existing.end_time = parse_time(announcement_data.get("end_time"))
        existing.type = announcement_data.get("type")

        db.session.commit()
        return existing
    else:
        # 如果不存在，创建新公告
        announcement = model(
            official_id=announcement_data.get("official_id"),
            uuid=announcement_data.get("uuid"),  # 确保传入uuid
            title=announcement_data.get("title"),
            raw_data=json.dumps(announcement_data.get("raw_data", {})),
            content=announcement_data.get("content"),
            banner_img=announcement_data.get("banner_img"),
            start_time=parse_time(announcement_data.get("start_time")),
            end_time=parse_time(announcement_data.get("end_time")),
            type=announcement_data.get("type"),
        )

        db.session.add(announcement)
        db.session.commit()
        return announcement


def get_announcements(game_id: str, language: str, **filters):
    """Get announcements with optional filters"""
    model = get_announcement_model(game_id, language)
    query = model.query

    if filters.get("type"):
        query = query.filter_by(type=filters["type"])

    if filters.get("active"):
        now = datetime.utcnow()
        query = query.filter(model.start_time <= now).filter(model.end_time >= now)

    return query.order_by(model.start_time.desc()).all()


DYNAMIC_MODELS = {}


def create_refresh_tables(game_ids):
    """
    为每个游戏创建刷新记录表
    """
    for game_id in game_ids:
        if game_id not in current_app.config.get("SQLALCHEMY_BINDS", {}):
            continue

        table_name = f"refresh_records_{game_id}"

        if table_name in list(DYNAMIC_MODELS.keys()):
            print(f"Table {table_name} already exists, skipping...")
            continue

        # 动态创建模型类
        attrs = {
            "__tablename__": table_name,
            "__bind_key__": game_id,
        }
        model_cls = type(table_name, (RefreshRecord,), attrs)
        DYNAMIC_MODELS[table_name] = model_cls  # 存储到字典


def get_refresh_record_model(game_id):
    return DYNAMIC_MODELS.get(f"refresh_records_{game_id}")
