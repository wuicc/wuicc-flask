import os
import json

# 基础配置
INSTANCE_DIR = os.path.join(os.path.dirname(__file__), "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)  # 自动创建目录

# 主数据库配置
SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(INSTANCE_DIR, "wuicc.sqlite3")
SQLALCHEMY_TRACK_MODIFICATIONS = False

# 从JSON文件读取游戏数据库配置
def load_database_binds():
    binds = {}
    try:
        # 假设games.json位于项目根目录的data文件夹下
        games_json_path = os.path.join(os.path.dirname(__file__), "data", "games.json")
        
        with open(games_json_path, "r", encoding="utf-8") as f:
            games_data = json.load(f)
            
            for game in games_data["games"]:
                game_id = game["game_id"]
                db_file = f"{game_id}.sqlite3"
                binds[game_id] = f"sqlite:///{os.path.join(INSTANCE_DIR, db_file)}"
                
    except Exception as e:
        print(f"加载游戏数据库配置失败: {str(e)}")
        # 默认回退配置
        binds = {
            "genshin": f"sqlite:///{os.path.join(INSTANCE_DIR, 'genshin.sqlite3')}",
            "starrail": f"sqlite:///{os.path.join(INSTANCE_DIR, 'starrail.sqlite3')}",
        }
    
    return binds

# 动态生成SQLALCHEMY_BINDS配置
SQLALCHEMY_BINDS = load_database_binds()