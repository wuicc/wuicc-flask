import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union
from bs4 import BeautifulSoup


class WutheringParser:
    """鸣潮(Wuthering Waves)公告解析器"""

    def __init__(self):
        self.version_now = "1.0"
        self.version_begin_time = ""
        self.supported_languages = [
            "zh-Hans",
            "zh-Hant",
            "en",
            "ja",
        ]

    def _extract_event_time_from_zh_content(self, content: Dict) -> Tuple[str, str]:
        """专门从中文内容中提取活动时间"""
        if not content or not isinstance(content, dict):
            return "", ""

        html_content = content.get("textContent", "")
        if not html_content:
            return "", ""

        soup = BeautifulSoup(html_content, "html.parser")
        activity_time_divs = soup.find_all("div", attrs={"data-line": "true"})
        for div in activity_time_divs:
            if div.find(string=lambda text: text and "✦活动时间✦" in text):
                time_div = div.find_next("div", attrs={"data-line": "true"})
                if time_div:
                    activity_time = time_div.get_text(strip=True)
                    if "~" in activity_time:
                        start_time = (
                            activity_time.split("~")[0]
                            .replace("（服务器时间）", "")
                            .strip()
                        )
                        end_time = (
                            activity_time.split("~")[1]
                            .replace("（服务器时间）", "")
                            .strip()
                        )
                        return start_time, end_time
        return "", ""

    def _parse_content_time(self, time_str: str) -> str:
        """解析内容中的时间字符串为标准格式"""
        if not time_str:
            return ""

        try:
            # 尝试解析格式如 "2023年11月15日10:00"
            time_str = time_str.replace("年", "-").replace("月", "-").replace("日", "")
            date_obj = datetime.strptime(time_str, "%Y-%m-%d%H:%M")
            return date_obj.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ""

    def _get_time_from_zh_content(self, activity: Dict) -> Tuple[str, str]:
        """从中文内容中获取时间信息"""
        zh_content = activity.get("zh_content", {})
        if not zh_content:
            return "", ""

        # 获取公告中的时间戳
        start_time = self._timestamp_to_datetime(activity.get("startTimeMs", 0))
        end_time = self._timestamp_to_datetime(activity.get("endTimeMs", 0))

        # 尝试从中文内容中提取更准确的时间
        content_start, content_end = self._extract_event_time_from_zh_content(
            zh_content
        )
        if content_start and content_end:
            content_start = content_start.replace("（服务器时间）", "").strip()
            content_end = content_end.replace("（服务器时间）", "").strip()

            # 如果内容时间包含版本号，使用版本开始时间
            if f"{self.version_now}版本" in content_start:
                parsed_start = self.version_begin_time
            else:
                parsed_start = self._parse_content_time(content_start)

            parsed_end = self._parse_content_time(content_end)

            if parsed_start:
                start_time = parsed_start
            if parsed_end:
                end_time = parsed_end

        return start_time, end_time

    def parse(self, raw_data: Dict, lang: str = "zh-Hans") -> List[Dict]:
        """
        解析鸣潮公告数据

        Args:
            raw_data: 从KuroFetcher获取的原始数据
                {
                    "game": 游戏版本公告,
                    "activity": 活动公告列表（包含详情内容）
                }
            lang: 语言代码，默认为简体中文(zh-Hans)

        Returns:
            解析后的公告列表，每个公告包含:
            {
                "official_id": 官方ID,
                "title": 标题,
                "start_time": 开始时间,
                "end_time": 结束时间,
                "bannerImage": 横幅图片URL,
                "event_type": 类型(version/event/gacha),
                "content": 原始内容
            }
        """
        if lang not in self.supported_languages:
            lang = "zh-Hans"

        filtered_list = []

        # 1. 处理版本公告
        self._parse_version_announcements(raw_data, filtered_list, lang)

        # 2. 处理活动公告
        self._parse_activity_announcements(raw_data, filtered_list, lang)

        # 3. 处理唤取(抽卡)公告
        self._parse_gacha_announcements(raw_data, filtered_list, lang)

        return filtered_list

    def _parse_version_announcements(
        self, raw_data: Dict, result_list: List[Dict], lang: str
    ):
        """解析版本更新公告"""
        if "game" not in raw_data:
            return

        version_anns = raw_data["game"]
        if isinstance(version_anns, list):
            if not version_anns:
                return
        version_ann = version_anns[0]

        zh_title = version_ann.get("tabTitle", {}).get("zh-Hans", "")
        if not zh_title or "版本内容说明" not in zh_title:
            return

        # 提取版本号
        version_numbers = self._extract_version_number(zh_title)
        if version_numbers:
            self.version_now = str(version_numbers[0])

        # 获取标题和横幅图片（根据语言）
        title = version_ann.get("tabTitle", {}).get(lang, zh_title)
        banner_images = version_ann.get("tabBanner", {}).get(lang, [])
        if not banner_images:
            banner_images = version_ann.get("tabBanner", {}).get("zh-Hans", [])
        banner_image = banner_images[0] if banner_images else ""

        # 转换时间格式
        start_time = self._timestamp_to_datetime(version_ann.get("startTimeMs", 0))
        end_time = self._timestamp_to_datetime(version_ann.get("endTimeMs", 0))

        parsed = {
            "official_id": version_ann.get("id", ""),
            "title": f"{self.version_now}" if lang == "zh-Hans" else title,
            "start_time": start_time,
            "end_time": end_time,
            "bannerImage": banner_image,
            "event_type": "version",
            "content": json.dumps(version_ann, ensure_ascii=False),
        }

        self.version_begin_time = start_time
        result_list.append(parsed)

    def _parse_activity_announcements(
        self, raw_data: Dict, result_list: List[Dict], lang: str
    ):
        """解析活动公告"""
        if "activity" not in raw_data:
            return

        for activity in raw_data["activity"]:
            if not isinstance(activity, dict):
                continue

            zh_title = activity.get("tabTitle", {}).get("zh-Hans", "")
            if not zh_title or not self._is_valid_activity(zh_title):
                continue

            # 获取标题和横幅图片（根据语言）
            title = activity.get("tabTitle", {}).get(lang, zh_title)
            banner_images = activity.get("tabBanner", {}).get(lang, [])
            if not banner_images:
                banner_images = activity.get("tabBanner", {}).get("zh-Hans", [])
            banner_image = banner_images[0] if banner_images else ""

            # 从中文内容获取时间
            start_time, end_time = self._get_time_from_zh_content(activity)

            # 获取对应语言的内容
            content = activity.get(f"{lang}_content", activity.get("zh_content", {}))

            parsed = {
                "official_id": activity.get("id", ""),
                "title": title,
                "start_time": start_time,
                "end_time": end_time,
                "bannerImage": banner_image,
                "event_type": "event",
                "content": json.dumps(content, ensure_ascii=False),
            }

            result_list.append(parsed)

    def _parse_gacha_announcements(
        self, raw_data: Dict, result_list: List[Dict], lang: str
    ):
        """解析唤取(抽卡)公告"""
        if "activity" not in raw_data:
            return

        for activity in raw_data["activity"]:
            if not isinstance(activity, dict):
                continue

            zh_title = activity.get("tabTitle", {}).get("zh-Hans", "")
            if not zh_title or "唤取" not in zh_title:
                continue

            # 获取标题和横幅图片（根据语言）
            title = activity.get("tabTitle", {}).get(lang, zh_title)
            banner_images = activity.get("tabBanner", {}).get(lang, [])
            if not banner_images:
                banner_images = activity.get("tabBanner", {}).get("zh-Hans", [])
            banner_image = banner_images[0] if banner_images else ""

            # 从中文内容获取时间
            start_time, end_time = self._get_time_from_zh_content(activity)

            # 获取对应语言的内容
            content = activity.get(f"{lang}_content", activity.get("zh_content", {}))

            # 解析内容生成标准化标题（仅简体中文）
            clean_title = (
                self._parse_gacha_content(zh_title, content)
                if lang == "zh-Hans"
                else title
            )

            parsed = {
                "official_id": activity.get("id", ""),
                "title": clean_title,
                "start_time": start_time,
                "end_time": end_time,
                "bannerImage": banner_image,
                "event_type": "gacha",
                "content": json.dumps(content, ensure_ascii=False),
            }

            result_list.append(parsed)

    def _is_valid_activity(self, title: str) -> bool:
        """判断是否为有效活动公告"""
        return title.endswith("活动") and all(
            keyword not in title for keyword in ["感恩答谢", "签到", "回归", "数据回顾"]
        )

    def _parse_gacha_content(self, title: str, content: Dict) -> str:
        """解析唤取公告内容并生成标准化标题"""
        if not content or not isinstance(content, dict):
            return self._standardize_gacha_title(title)

        text_content = content.get("textContent", "")
        text_title = content.get("textTitle", "")

        # 确定唤取类型
        gacha_type = "角色"
        if "浮声" in title or "武器" in title or "音感仪" in title:
            gacha_type = "武器"

        # 周年活动特殊处理
        if "周年" in title and text_title:
            try:
                # 提取5星角色/武器名称
                start_marker = f"5星{gacha_type}「"
                end_marker = "」、"

                start_index = text_content.find(start_marker)
                if start_index != -1:
                    start_index += len(start_marker)
                    end_index = text_content.find(end_marker, start_index)
                    if end_index != -1:
                        characters_str = text_content[start_index:end_index]
                        five_star_items = characters_str.split("」「")

                        # 提取活动名称
                        activity_name = (
                            text_title.split("・")[1][:-1] if "・" in text_title else ""
                        )

                        return (
                            f"【周年・{activity_name}】"
                            f"{gacha_type}唤取: {', '.join(five_star_items)}"
                        )
            except Exception:
                pass

        # 常规唤取活动处理
        if text_title:
            # 尝试提取格式如 [活动]「角色名」唤取即将开启
            bracket_match = re.search(r"「([^」]+)」", text_title)
            if bracket_match:
                item_name = bracket_match.group(1)

                # 提取活动类型
                activity_type = ""
                bracket_parts = re.findall(r"\[([^\]]+)\]", text_title)
                if bracket_parts:
                    activity_type = bracket_parts[0]

                return f"【{activity_type}】{gacha_type}唤取: {item_name}"

        # 默认情况使用原标题处理
        return self._standardize_gacha_title(title, content)

    def _standardize_gacha_title(self, title: str, content: Dict = None) -> str:
        """标准化唤取公告标题"""
        if "共鸣者" in title:
            return f"【角色唤取】{title}"
        elif "音感仪" in title:
            return f"【武器唤取】{title}"
        return title

    @staticmethod
    def _extract_version_number(text: str) -> List[float]:
        """从文本中提取版本号"""
        version_pattern = r"(\d+\.\d+)"
        versions = re.findall(version_pattern, text)
        return [float(v) for v in versions] if versions else []

    @staticmethod
    def _timestamp_to_datetime(timestamp_ms: int) -> str:
        """将毫秒时间戳转换为日期时间字符串"""
        if not timestamp_ms:
            return ""
        try:
            dt = datetime.fromtimestamp(timestamp_ms / 1000)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return ""
