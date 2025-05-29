from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    game_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    enabled = db.Column(db.Integer, default=1)  # 1 enabled, 0 disabled
    force_refresh = db.Column(db.Integer, default=0)  # 1 force, 0 normal


class RefreshLog(db.Model):
    __tablename__ = "refresh_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    game_id = db.Column(db.String(50), nullable=False)
    language = db.Column(db.String(10), nullable=False)
    refresh_time = db.Column(db.DateTime, default=datetime.utcnow)
    success = db.Column(db.Integer, default=1)  # 1 success, 0 failure

    def __repr__(self):
        return f"<RefreshLog {self.game_id} {self.language}>"


class RefreshRecord(db.Model):
    """各游戏各语言的刷新记录表"""

    __abstract__ = True  # 声明为抽象基类，实际表将动态创建

    id = db.Column(db.Integer, primary_key=True)
    language = db.Column(db.String(10), nullable=False)  # 语言代码
    last_refresh = db.Column(db.DateTime)  # 最后刷新时间
    success = db.Column(db.Boolean, default=True)  # 是否成功

    def __repr__(self):
        return f"<RefreshRecord {self.language}: {self.last_refresh}>"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_name = db.Column(db.String(80), unique=True, nullable=False)
    user_nickname = db.Column(db.String(80))
    password_hash = db.Column(db.String(128))
    email = db.Column(db.String(120), unique=True)
    is_active = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_banned = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class UserData(db.Model):
    __tablename__ = "user_data"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    config_json = db.Column(db.Text)

    user = db.relationship("User", backref="data")


class UserToken(db.Model):
    __tablename__ = "user_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token = db.Column(db.String(16), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="tokens")

    def __repr__(self):
        return f"<UserToken {self.token[:4]}...>"
