import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from models import db, Game, RefreshLog
from services.fetch.mihoyo_fetcher import MihoyoFetcher
from services.fetch.kuro_fetcher import KuroFetcher
from services.parse.genshin_parser import GenshinParser
from services.parse.starrail_parser import StarRailParser
from services.parse.zenless_parser import ZenlessParser
from services.parse.wuthering_parser import WutheringParser
from ann_model import get_announcement_model, get_refresh_record_model


class AnnouncementService:
    """公告服务类，负责获取、解析和存储公告数据"""

    def __init__(self):
        self._cache = {}  # 内存缓存
        self._mihoyo_fetcher = MihoyoFetcher()
        self._kuro_fetcher = KuroFetcher()
        self._genshin_parser = GenshinParser()
        self._starrail_parser = StarRailParser()
        self._zenless_parser = ZenlessParser()
        self._wuthering_parser = WutheringParser()

    def _load_announcement_links(self) -> Dict:
        """从ann_link.json加载公告链接"""
        try:
            with open("data/ann_link.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading announcement links: {e}")
            return {}

    def _should_refresh(self, game_id: str, lang: str) -> bool:
        """检查是否需要刷新特定语言的公告"""
        try:
            model = get_refresh_record_model(game_id)
            if not model:
                raise ValueError(f"RefreshRecord model for {game_id} not found")

            record = model.query.filter_by(language=lang).first()

            if not record:
                return True

            if record.last_refresh is None:
                return True

            game = Game.query.filter_by(game_id=game_id).first()
            if game and game.force_refresh == 1:
                game.force_refresh = 0
                db.session.commit()
                return True

            return datetime.utcnow() - record.last_refresh > timedelta(hours=12)

        except Exception as e:
            print(f"[ERROR in _should_refresh] {repr(e)}")
            return True

    def _update_refresh_time(self, game_id: str, lang: str, success: bool = True):
        """更新刷新记录"""
        try:
            model = get_refresh_record_model(game_id)
            if not model:
                raise ValueError(f"RefreshRecord model for {game_id} not found")

            record = model.query.filter_by(language=lang).first()
            if not record:
                record = model(language=lang)
                db.session.add(record)

            record.last_refresh = datetime.utcnow()
            record.success = success
            db.session.commit()

        except Exception as e:
            print(f"[ERROR in _update_refresh_time] {repr(e)}")
            db.session.rollback()

    def _store_announcements(self, game_id: str, lang: str, announcements: List[Dict]):
        """存储公告到数据库（不重复添加已存在的公告）"""
        model = get_announcement_model(game_id, lang)

        existing_ids = {
            ann.official_id
            for ann in model.query.with_entities(model.official_id).all()
        }

        new_announcements = []
        for ann in announcements:
            if ann.get("official_id") in existing_ids:
                continue

            # 转换时间格式
            def parse_time(time_str):
                if not time_str:
                    return None
                if isinstance(time_str, datetime):  # 已经是日期对象
                    return time_str
                try:
                    return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError):
                    return None

            announcement_data = {
                "official_id": ann.get("official_id", ""),
                "title": ann.get("title", ""),
                "content": ann.get("content", ""),
                "banner_img": ann.get("bannerImage", ""),
                "start_time": parse_time(ann.get("start_time")),
                "end_time": parse_time(ann.get("end_time")),
                "type": ann.get("event_type", "event"),
                "raw_data": json.dumps(ann, ensure_ascii=False),
            }

            announcement = model(**announcement_data)
            new_announcements.append(announcement)

        if new_announcements:
            try:
                db.session.bulk_save_objects(new_announcements)
                db.session.commit()
                print(
                    f"Added {len(new_announcements)} new announcements for {game_id} {lang}"
                )
            except Exception as e:
                db.session.rollback()
                print(f"Error saving announcements for {game_id} {lang}: {e}")

    def _fetch_genshin_announcements(self, lang: str) -> List[Dict]:
        """获取原神公告数据"""
        try:
            raw_data = self._mihoyo_fetcher.fetch_game_announcements("genshin", lang)
            if not raw_data:
                raise ValueError("No data fetched from Genshin API")

            parsed_data = self._genshin_parser.parse(raw_data, lang)
            return parsed_data
        except Exception as e:
            print(f"Error fetching Genshin announcements: {e}")
            return []

    def _fetch_starrail_announcements(self, lang: str) -> List[Dict]:
        """获取星穹铁道公告数据"""
        try:
            raw_data = self._mihoyo_fetcher.fetch_game_announcements("starrail", lang)
            if not raw_data:
                raise ValueError("No data fetched from Star Rail API")

            parsed_data = self._starrail_parser.parse(raw_data, lang)
            return parsed_data
        except Exception as e:
            print(f"Error fetching Star Rail announcements: {e}")
            return []
    
    def _fetch_zenless_announcements(self, lang: str) -> List[Dict]:
        """获取绝区零公告数据"""
        try:
            raw_data = self._mihoyo_fetcher.fetch_game_announcements("zenless", lang)
            if not raw_data:
                raise ValueError("No data fetched from zenless API")
            
            parsed_data = self._zenless_parser.parse(raw_data, lang)
            return parsed_data
        except Exception as e:
            print(f"Error fetching zenless announcements: {e}")
            return []

    def _fetch_wuthering_announcements(self, lang: str) -> List[Dict]:
        """获取鸣潮公告数据"""
        try:
            raw_data = self._kuro_fetcher.fetch_all_announcements()
            if not raw_data:
                raise ValueError("No data fetched from Kuro API")

            parsed_data = self._wuthering_parser.parse(raw_data, lang)
            return parsed_data
        except Exception as e:
            print(f"Error fetching Wuthering announcements: {e}")
            return []

    def get_announcements(
        self, game_id: str, lang: str, force_refresh: bool = False
    ) -> List[Dict]:
        """获取公告数据"""
        cache_key = f"{game_id}_{lang}"

        if not force_refresh and cache_key in self._cache:
            return self._cache[cache_key]

        need_refresh = force_refresh or self._should_refresh(game_id, lang)

        if not need_refresh:
            return self._get_from_database(game_id, lang)

        try:
            if game_id == "genshin":
                announcements = self._fetch_genshin_announcements(lang)
            elif game_id == "starrail":
                announcements = self._fetch_starrail_announcements(lang)
            elif game_id == "zenless":
                announcements = self._fetch_zenless_announcements(lang)
            elif game_id == "wuthering":
                announcements = self._fetch_wuthering_announcements(lang)
            else:
                return self._get_from_database(game_id, lang)

            if announcements:
                self._store_announcements(game_id, lang, announcements)
                self._update_refresh_time(game_id, lang, True)
                self._cache[cache_key] = announcements

            return self._get_from_database(game_id, lang)

        except Exception as e:
            print(f"Error fetching announcements for {game_id} {lang}: {repr(e)}")
            return self._get_from_database(game_id, lang)

    def refresh_all_games(self):
        """刷新所有游戏的公告数据"""
        games = Game.query.filter_by(enabled=1).all()
        for game in games:
            for lang in ["zh-Hans", "en", "ja", "zh-Hant"]:
                try:
                    self.get_announcements(game.game_id, lang, force_refresh=True)
                except Exception as e:
                    print(f"Error refreshing {game.game_id} {lang}: {e}")

    def _get_from_database(self, game_id: str, lang: str) -> List[Dict]:
        """从数据库获取格式化后的公告数据（不返回已结束的活动）"""
        model = get_announcement_model(game_id, lang)
        
        # 获取当前时间
        now = datetime.utcnow()
        
        # 只查询未结束的公告（end_time > now）
        announcements = model.query.filter(model.end_time > now)\
                                .order_by(model.start_time.desc())\
                                .all()

        return [
            {
                "id": ann.id,
                "official_id": ann.official_id,
                "title": ann.title,
                "banner_img": ann.banner_img,
                "start_time": (
                    ann.start_time.strftime("%Y-%m-%d %H:%M:%S")
                    if ann.start_time
                    else None
                ),
                "end_time": (
                    ann.end_time.strftime("%Y-%m-%d %H:%M:%S") 
                    if ann.end_time 
                    else None
                ),
                "type": ann.type,
            }
            for ann in announcements
        ]