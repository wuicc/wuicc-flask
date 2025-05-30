import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import logging
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

    def __init__(self, debug: bool = True):
        # 缓存结构: {cache_key: (data, expiration_time)}
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._cache_ttl = timedelta(hours=1)  # 默认缓存1小时
        self._debug = debug

        # 缓存统计
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_expirations = 0

        # 初始化各组件
        self._mihoyo_fetcher = MihoyoFetcher()
        self._kuro_fetcher = KuroFetcher()
        self._genshin_parser = GenshinParser()
        self._starrail_parser = StarRailParser()
        self._zenless_parser = ZenlessParser()
        self._wuthering_parser = WutheringParser()

        # 配置日志
        self._setup_logging()
        self._log("AnnouncementService initialized", level="info")
        self._cache = {}  # 内存缓存
        self._debug = debug  # 调试开关
        self._mihoyo_fetcher = MihoyoFetcher()
        self._kuro_fetcher = KuroFetcher()
        self._genshin_parser = GenshinParser()
        self._starrail_parser = StarRailParser()
        self._zenless_parser = ZenlessParser()
        self._wuthering_parser = WutheringParser()

        # 配置日志
        self._setup_logging()
        self._log("AnnouncementService initialized", level="info")

    def _setup_logging(self):
        """配置日志系统"""
        self.logger = logging.getLogger(__name__)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        if self._debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

    def _log(self, message: str, level: str = "debug"):
        """统一的日志记录方法"""
        if not self._debug and level == "debug":
            return

        log_method = getattr(self.logger, level, self.logger.info)
        log_method(message)

    def _load_announcement_links(self) -> Dict:
        """从ann_link.json加载公告链接"""
        try:
            with open("data/ann_link.json", "r", encoding="utf-8") as f:
                self._log("Successfully loaded announcement links", "info")
                return json.load(f)
        except Exception as e:
            self._log(f"Error loading announcement links: {e}", "error")
            return {}

    def _should_refresh(self, game_id: str, lang: str) -> bool:
        """检查是否需要刷新特定语言的公告"""
        try:
            self._log(f"Checking if refresh is needed for {game_id} {lang}", "debug")
            model = get_refresh_record_model(game_id)
            if not model:
                self._log(f"RefreshRecord model for {game_id} not found", "error")
                raise ValueError(f"RefreshRecord model for {game_id} not found")

            record = model.query.filter_by(language=lang).first()

            if not record:
                self._log(
                    f"No refresh record found for {game_id} {lang}, will refresh",
                    "debug",
                )
                return True

            if record.last_refresh is None:
                self._log(
                    f"Refresh record exists but no last_refresh time for {game_id} {lang}, will refresh",
                    "debug",
                )
                return True

            game = Game.query.filter_by(game_id=game_id).first()
            if game and game.force_refresh == 1:
                self._log(
                    f"Force refresh flag set for {game_id}, will refresh", "debug"
                )
                game.force_refresh = 0
                db.session.commit()
                return True

            refresh_needed = datetime.utcnow() - record.last_refresh > timedelta(
                hours=12
            )
            self._log(
                f"Refresh check for {game_id} {lang}: {refresh_needed} (last refresh: {record.last_refresh})",
                "debug",
            )
            return refresh_needed

        except Exception as e:
            self._log(f"[ERROR in _should_refresh] {repr(e)}", "error")
            return True

    def _update_refresh_time(self, game_id: str, lang: str, success: bool = True):
        """更新刷新记录"""
        try:
            self._log(
                f"Updating refresh time for {game_id} {lang}, success: {success}",
                "debug",
            )
            model = get_refresh_record_model(game_id)
            if not model:
                self._log(f"RefreshRecord model for {game_id} not found", "error")
                raise ValueError(f"RefreshRecord model for {game_id} not found")

            record = model.query.filter_by(language=lang).first()
            if not record:
                record = model(language=lang)
                db.session.add(record)
                self._log(f"Created new refresh record for {game_id} {lang}", "debug")

            record.last_refresh = datetime.utcnow()
            record.success = success
            db.session.commit()
            self._log(
                f"Successfully updated refresh time for {game_id} {lang}", "debug"
            )

        except Exception as e:
            self._log(f"[ERROR in _update_refresh_time] {repr(e)}", "error")
            db.session.rollback()

    def _store_announcements(self, game_id: str, lang: str, announcements: List[Dict]):
        """存储公告到数据库（更新已存在的公告）"""
        self._log(
            f"Storing announcements for {game_id} {lang}, count: {len(announcements)}",
            "debug",
        )
        model = get_announcement_model(game_id, lang)

        # 获取所有现有公告的ID映射 {official_id: announcement_object}
        existing_announcements = {
            str(ann.official_id): ann for ann in model.query.all()
        }
        self._log(
            f"Found {len(existing_announcements)} existing announcements in DB for {game_id} {lang}",
            "debug",
        )

        new_announcements = []
        updated_count = 0

        for ann in announcements:
            ann_id = str(ann.get("ann_id"))
            existing_ann = existing_announcements.get(ann_id)

            # 转换时间格式
            def parse_time(time_str):
                if not time_str:
                    return None
                if isinstance(time_str, datetime):  # 已经是日期对象
                    return time_str
                try:
                    return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError) as e:
                    self._log(f"Error parsing time {time_str}: {e}", "warning")
                    return None

            announcement_data = {
                "official_id": ann.get("ann_id", ""),
                "title": ann.get("title", ""),
                "content": ann.get("content", ""),
                "banner_img": ann.get("bannerImage", ""),
                "start_time": parse_time(ann.get("start_time")),
                "end_time": parse_time(ann.get("end_time")),
                "type": ann.get("event_type", "event"),
                "raw_data": json.dumps(ann, ensure_ascii=False),
            }

            if existing_ann:
                # 更新现有公告
                existing_ann.title = announcement_data["title"]
                existing_ann.content = announcement_data["content"]
                existing_ann.banner_img = announcement_data["banner_img"]
                existing_ann.start_time = announcement_data["start_time"]
                existing_ann.end_time = announcement_data["end_time"]
                existing_ann.type = announcement_data["type"]
                existing_ann.raw_data = announcement_data["raw_data"]
                updated_count += 1
                self._log(f"Updated existing announcement: {ann_id}", "debug")
            else:
                # 添加新公告
                announcement = model(**announcement_data)
                new_announcements.append(announcement)
                self._log(
                    f"Prepared new announcement for storage: {ann_id}",
                    "debug",
                )

        try:
            if new_announcements:
                db.session.bulk_save_objects(new_announcements)
            db.session.commit()
            self._log(
                f"Added {len(new_announcements)} new and updated {updated_count} existing announcements for {game_id} {lang}",
                "info",
            )
        except Exception as e:
            db.session.rollback()
            self._log(f"Error saving announcements for {game_id} {lang}: {e}", "error")

    def _fetch_genshin_announcements(self, lang: str) -> List[Dict]:
        """获取原神公告数据"""
        try:
            self._log(f"Fetching Genshin announcements for {lang}", "debug")
            raw_data = self._mihoyo_fetcher.fetch_game_announcements("genshin", lang)
            if not raw_data:
                self._log("No data fetched from Genshin API", "warning")
                raise ValueError("No data fetched from Genshin API")

            parsed_data = self._genshin_parser.parse(raw_data, lang)
            self._log(
                f"Successfully parsed {len(parsed_data)} Genshin announcements for {lang}",
                "debug",
            )
            return parsed_data
        except Exception as e:
            self._log(f"Error fetching Genshin announcements: {e}", "error")
            return []

    def get_announcements(
        self, game_id: str, lang: str, force_refresh: bool = False
    ) -> List[Dict]:
        """
        获取游戏公告数据（带智能缓存机制）

        Args:
            game_id: 游戏ID（如 'genshin'/'starrail'）
            lang: 语言代码（如 'zh-Hans'/'en'）
            force_refresh: 是否强制跳过缓存刷新数据

        Returns:
            公告数据列表，格式示例：
            [{
                "id": 123,
                "official_id": "123456",
                "title": "活动公告",
                "banner_img": "http://...",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-01-31 23:59:59",
                "type": "event"
            }]
        """
        cache_key = f"{game_id}_{lang}"

        # === 1. 调试日志：记录请求开始 ===
        self._log(
            f"▶ 开始获取公告 [游戏: {game_id}, 语言: {lang}, 强制刷新: {force_refresh}]",
            "debug",
        )
        if self._debug:
            self._log_cache_stats()  # 输出当前缓存状态

        # === 2. 强制刷新处理 ===
        if force_refresh:
            self.clear_cache(game_id, lang)
            self._log("🗑️ 已清除缓存（强制刷新模式）", "debug")

        # === 3. 尝试从缓存获取 ===
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None and not force_refresh:
            self._log(f"💾 使用缓存数据（{len(cached_data)}条公告）", "debug")
            self._log_cache_stats()  # 调试统计
            return cached_data

        # === 4. 检查是否需要刷新 ===
        need_refresh = force_refresh or self._should_refresh(game_id, lang)
        self._log(
            f"🔄 刷新检查结果: {'需要刷新' if need_refresh else '使用现有数据'}",
            "debug",
        )

        # === 5. 需要刷新时的处理 ===
        announcements = []
        if need_refresh:
            try:
                self._log("⏳ 正在从API获取最新公告...", "info")

                # 根据游戏类型调用不同的获取方法
                if game_id == "genshin":
                    announcements = self._fetch_genshin_announcements(lang)
                elif game_id == "starrail":
                    announcements = self._fetch_starrail_announcements(lang)
                elif game_id == "zenless":
                    announcements = self._fetch_zenless_announcements(lang)
                elif game_id == "wuthering":
                    announcements = self._fetch_wuthering_announcements(lang)
                else:
                    raise ValueError(f"未知游戏ID: {game_id}")

                if announcements:
                    self._log(f"✅ 获取到 {len(announcements)} 条新公告", "info")
                    # 存储到数据库
                    self._store_announcements(game_id, lang, announcements)
                    self._update_refresh_time(game_id, lang, True)
                    # 更新缓存
                    self._set_to_cache(cache_key, announcements)
                else:
                    self._log("⚠️ 从API获取到空公告列表", "warning")

            except Exception as e:
                self._log(f"❌ API刷新失败: {str(e)}", "error")
                need_refresh = False  # 失败时降级使用现有数据

        # === 6. 从数据库获取数据（刷新失败或不需要刷新时） ===
        if not need_refresh or not announcements:
            self._log("⏳ 从数据库加载公告...", "debug")
            announcements = self._get_from_database(game_id, lang)
            if announcements:
                self._set_to_cache(cache_key, announcements)  # 缓存数据库查询结果

        # === 7. 最终处理 ===
        if not announcements:
            self._log("⚠️ 未获取到任何公告数据", "warning")
            return []

        # === 8. 调试日志：记录请求结束 ===
        self._log(f"✔️ 返回 {len(announcements)} 条公告", "debug")
        if self._debug:
            self._log_cache_stats()  # 输出最终缓存状态
            self._log("════════════════════════════════", "debug")

        return announcements

    def refresh_all_games(self):
        """刷新所有游戏的公告数据"""
        self._log("Starting refresh_all_games operation", "info")
        games = Game.query.filter_by(enabled=1).all()
        self._log(f"Found {len(games)} enabled games to refresh", "debug")

        for game in games:
            for lang in ["zh-Hans", "en", "ja", "zh-Hant"]:
                try:
                    self._log(f"Refreshing {game.game_id} {lang}", "debug")
                    self.get_announcements(game.game_id, lang, force_refresh=True)
                except Exception as e:
                    self._log(f"Error refreshing {game.game_id} {lang}: {e}", "error")

    def _get_from_database(self, game_id: str, lang: str) -> List[Dict]:
        """从数据库获取格式化后的公告数据（不返回已结束的活动）"""
        self._log(f"Getting announcements from DB for {game_id} {lang}", "debug")
        model = get_announcement_model(game_id, lang)

        # 获取当前时间
        now = datetime.utcnow()

        # 只查询未结束的公告（end_time > now）
        announcements = (
            model.query.filter(model.end_time > now)
            .order_by(model.start_time.desc())
            .all()
        )

        self._log(
            f"Found {len(announcements)} active announcements in DB for {game_id} {lang}",
            "debug",
        )

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
                    ann.end_time.strftime("%Y-%m-%d %H:%M:%S") if ann.end_time else None
                ),
                "type": ann.type,
            }
            for ann in announcements
        ]

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

    def _get_cache_stats(self) -> Dict[str, int]:
        """获取当前缓存统计信息"""
        return {
            "total_entries": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_expirations": self._cache_expirations,
        }

    def _log_cache_stats(self):
        """记录缓存统计信息"""
        if self._debug:
            stats = self._get_cache_stats()
            self._log(
                f"Cache Stats - Entries: {stats['total_entries']}, "
                f"Hits: {stats['cache_hits']}, Misses: {stats['cache_misses']}, "
                f"Expirations: {stats['cache_expirations']}",
                "debug",
            )

    def clear_cache(self, game_id: Optional[str] = None, lang: Optional[str] = None):
        """清除指定或全部缓存"""
        if game_id and lang:
            cache_key = f"{game_id}_{lang}"
            self._cache.pop(cache_key, None)
            self._log(f"Cleared cache for {cache_key}", "debug")
        elif game_id:
            # 清除该游戏所有语言的缓存
            keys = [k for k in self._cache.keys() if k.startswith(f"{game_id}_")]
            for k in keys:
                self._cache.pop(k, None)
            self._log(
                f"Cleared all cache for game {game_id} ({len(keys)} entries)", "debug"
            )
        else:
            self._cache.clear()
            self._log("Cleared all cache entries", "debug")

    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """从缓存获取数据，检查过期时间"""
        if cache_key not in self._cache:
            self._cache_misses += 1
            return None

        data, expiration_time = self._cache[cache_key]
        if datetime.now() >= expiration_time:
            self._cache.pop(cache_key, None)
            self._cache_expirations += 1
            self._cache_misses += 1
            self._log(f"Cache expired for {cache_key}", "debug")
            return None

        self._cache_hits += 1
        return data

    def _set_to_cache(self, cache_key: str, data: Any):
        """将数据存入缓存，设置过期时间"""
        expiration_time = datetime.now() + self._cache_ttl
        self._cache[cache_key] = (data, expiration_time)
        self._log(f"Data cached for {cache_key} until {expiration_time}", "debug")
