import random
import string
from datetime import datetime
from functools import wraps
from flask import request
from models import User, UserToken, db
from utils import make_json_response  # Assuming this is now in utils.py


def generate_token(length=16):
    """生成随机 token (小写字母+数字)"""
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return make_json_response(
                code=401,
                message="Token is missing or invalid format"
            )

        token = auth_header.split()[1]
        user_token = UserToken.query.filter_by(token=token).first()

        if not user_token:
            return make_json_response(
                code=401,
                message="Invalid token"
            )

        # 更新最后使用时间
        user_token.last_used = datetime.utcnow()
        db.session.commit()

        # 将用户对象传递给路由
        return f(user_token.user, *args, **kwargs)

    return decorated


def login():
    """用户登录，创建新 token (使用 x-www-form-urlencoded 数据)"""
    if not request.form or not request.form.get('username') or not request.form.get('password'):
        return make_json_response(
            code=401,
            message="Missing credentials"
        )

    username = request.form.get('username')
    password = request.form.get('password')

    user = User.query.filter_by(user_name=username).first()
    if not user or not user.check_password(password):
        return make_json_response(
            code=401,
            message="Invalid credentials"
        )

    # 检查用户已有 token 数量
    tokens = user.tokens
    if len(tokens) >= 10:
        # 删除最早创建的 token
        oldest_token = sorted(tokens, key=lambda t: t.created_at)[0]
        db.session.delete(oldest_token)

    # 创建新 token
    new_token = UserToken(
        user_id=user.id,
        token=generate_token(),
        created_at=datetime.utcnow(),
        last_used=datetime.utcnow(),
    )
    db.session.add(new_token)
    db.session.commit()

    return make_json_response(
        data={
            "token": new_token.token,
            "created_at": new_token.created_at.isoformat()
        }
    )


def logout(token):
    """注销特定 token"""
    user_token = UserToken.query.filter_by(token=token).first()
    if user_token:
        db.session.delete(user_token)
        db.session.commit()
        return True
    return False


def logout_all(user):
    """注销用户所有 token"""
    UserToken.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    return True