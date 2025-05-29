from datetime import datetime
from ann_model import (
    get_announcement_model,
    add_announcement,
    get_announcements
)

def fetch_game_announcements(game_id: str, lang: str):
    """服务层：获取游戏公告"""
    try:
        announcements = get_announcements(game_id, lang, active=True)
        return {
            'code': 200,
            'data': [ann.to_dict() for ann in announcements]
        }
    except Exception as e:
        return {'code': 500, 'error': str(e)}

def create_announcement(game_id: str, lang: str, data: dict):
    """服务层：创建公告"""
    try:
        # 数据预处理（如时间格式转换）
        data['start_time'] = datetime.fromisoformat(data['start_time'])
        data['end_time'] = datetime.fromisoformat(data['end_time'])
        
        announcement = add_announcement(game_id, lang, data)
        return {'code': 200, 'data': announcement.to_dict()}
    except ValueError as e:
        return {'code': 400, 'error': 'Invalid datetime format'}
    except Exception as e:
        return {'code': 500, 'error': str(e)}