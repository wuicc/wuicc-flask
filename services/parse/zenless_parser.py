import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union
from bs4 import BeautifulSoup


class ZenlessParser:
    """绝区零(Zenless Zone Zero)公告解析器（国际化版）"""

    def __init__(self, debug=False):
        self.version_now = "1.0"
        self.version_begin_time = ""
        self.seen_titles = set()
        self.w_engine_gacha_names = ["喧哗奏鸣", "激荡谐振", "灿烂和声", "璀璨韵律"]
        self.ignored_keywords = ["全新放送", "『嗯呢』从天降", "特别访客", "惊喜派送中"]
        self.debug = debug  # 调试模式开关
        self.supported_languages = ["zh-cn", "zh-tw", "en", "ja", "ko"]

    def _debug_print(self, *args, **kwargs):
        """调试输出"""
        if self.debug:
            print("[DEBUG]", *args, **kwargs)

    def _add_to_result_if_unique(
        self, result_list: List[Dict], announcement: Dict
    ) -> bool:
        """检查标题是否唯一，如果是则添加到结果列表"""
        title = announcement.get("title", "")
        if not title:
            return False

        if title in self.seen_titles:
            self._debug_print(f"标题已存在，跳过: {title}")
            return False

        self.seen_titles.add(title)
        result_list.append(announcement)
        return True

    def parse(self, raw_data: Dict, lang: str = "zh-cn") -> List[Dict]:
        """
        解析绝区零公告数据（支持多语言）

        Args:
            raw_data: 从MihoyoFetcher获取的原始数据
                {
                    "list": 公告列表数据,
                    "content_map": 公告内容映射,
                    "pic_content_map": 图片公告内容映射,
                    "zh_list": 中文列表数据,
                    "zh_content_map": 中文内容映射,
                    "zh_pic_content_map": 中文图片内容映射,
                    "lang": 请求的语言代码
                }
            lang: 语言代码 (zh-cn/zh-tw/en/ja/ko)

        Returns:
            解析后的公告列表，每个公告包含:
            {
                "ann_id": 公告ID,
                "title": 标题,
                "start_time": 开始时间,
                "end_time": 结束时间,
                "bannerImage": 横幅图片URL,
                "event_type": 类型(version/event/gacha),
                "content": 原始内容,
                "lang": 语言代码
            }
        """
        lang_mapper = {"zh-Hans": "zh-cn", "zh-Hant": "zh-tw"}
        lang = lang_mapper.get(lang, lang)
        self._debug_print(f"开始解析绝区零公告数据，语言: {lang}")
        self._debug_print(f"原始数据键: {raw_data.keys()}")

        if lang not in self.supported_languages:
            lang = "zh-cn"
            self._debug_print(f"不支持的语言，已重置为默认语言: {lang}")

        filtered_list = []

        # 1. 处理版本公告
        self._debug_print("\n=== 开始解析版本公告 ===")
        self._parse_version_announcements(raw_data, filtered_list, lang)

        # 2. 处理常规活动公告
        self._debug_print("\n=== 开始解析活动公告 ===")
        self._parse_normal_announcements(raw_data, filtered_list, lang)

        # 3. 处理图片列表中的公告
        self._debug_print("\n=== 开始解析图片公告 ===")
        self._parse_pic_announcements(raw_data, filtered_list, lang)

        # 4. 处理限时频段(抽卡)公告
        self._debug_print("\n=== 开始解析限时频段公告 ===")
        self._parse_gacha_announcements(raw_data, filtered_list, lang)

        self._debug_print(f"\n解析完成，共找到 {len(filtered_list)} 条公告")
        return filtered_list

    def _parse_version_announcements(
        self, raw_data: Dict, result_list: List[Dict], lang: str
    ):
        """解析版本更新公告"""
        # 使用中文列表数据进行解析
        zh_list_data = raw_data.get("zh_list", raw_data["list"])
        if "data" not in zh_list_data:
            self._debug_print("警告: 缺少data字段，无法解析版本公告")
            return

        version_list = zh_list_data["data"]["list"]
        self._debug_print(f"找到 {len(version_list)} 个公告类别")

        for item in version_list:
            self._debug_print(f"\n处理公告类别: {item['type_label']}")
            if item["type_label"] == "游戏公告":
                self._debug_print(f"找到游戏公告类别，包含 {len(item['list'])} 条公告")

                for announcement in item["list"]:
                    ann_id = announcement["ann_id"]
                    self._debug_print(f"处理公告 ID: {ann_id}")

                    # 使用中文标题提取版本号
                    zh_title = self._get_zh_title(announcement, raw_data)
                    clean_zh_title = self._remove_html_tags(zh_title)
                    self._debug_print(f"中文标题: {clean_zh_title}")

                    if "更新说明" in clean_zh_title and "版本" in clean_zh_title:
                        self._debug_print("检测到版本更新公告")

                        # 提取版本号
                        version_numbers = self._extract_floats(clean_zh_title)
                        if version_numbers:
                            self.version_now = str(version_numbers[0])
                            self._debug_print(f"提取到版本号: {self.version_now}")
                        else:
                            self._debug_print("警告: 无法从标题中提取版本号")

                        # 获取目标语言的公告数据
                        target_announcement = self._get_target_lang_announcement(
                            announcement, raw_data, lang
                        )
                        if not target_announcement:
                            self._debug_print(f"警告: 找不到 {lang} 语言的公告数据")
                            # continue
                            # 如果找不到目标语言数据，使用中文数据
                            target_announcement = announcement
                        # 获取目标语言的标题
                        title = self._remove_html_tags(target_announcement["title"])
                        self._debug_print(f"目标语言标题: {title}")

                        # 获取横幅图片（优先使用目标语言的图片）
                        banner_image = target_announcement.get(
                            "banner", announcement.get("banner", "")
                        )
                        self._debug_print(f"横幅图片: {banner_image[:50]}...")

                        # 获取时间
                        start_time = self._timestamp_to_datetime(
                            announcement.get("start_time", "")
                        )
                        end_time = self._timestamp_to_datetime(
                            announcement.get("end_time", "")
                        )
                        self._debug_print(f"时间范围: {start_time} 至 {end_time}")

                        parsed = {
                            "ann_id": ann_id,
                            "title": (
                                f"绝区零 {self.version_now} 版本"
                                if lang == "zh-cn"
                                else title
                            ),
                            "start_time": start_time,
                            "end_time": end_time,
                            "bannerImage": banner_image,
                            "event_type": "version",
                            "content": json.dumps(
                                target_announcement, ensure_ascii=False
                            ),
                            "lang": lang,
                        }

                        self.version_begin_time = start_time
                        result_list.append(parsed)
                        self._debug_print("已添加到结果列表")
                        break

    def _parse_normal_announcements(
        self, raw_data: Dict, result_list: List[Dict], lang: str
    ):
        """解析常规活动公告"""
        # 使用中文列表数据进行解析
        zh_list_data = raw_data.get("zh_list", raw_data["list"])
        if "data" not in zh_list_data:
            self._debug_print("警告: 缺少data字段，无法解析活动公告")
            return

        event_list = zh_list_data["data"]["list"]
        self._debug_print(f"找到 {len(event_list)} 个公告类别")

        for item in event_list:
            if item.get("type_id") in [3, 4]:  # 活动类型ID
                self._debug_print(f"找到活动公告类别，包含 {len(item['list'])} 条公告")

                for announcement in item["list"]:
                    ann_id = announcement["ann_id"]
                    self._debug_print(f"\n处理公告 ID: {ann_id}")

                    # 获取中文内容
                    zh_content = raw_data["zh_content_map"].get(ann_id, {})
                    if not zh_content:
                        self._debug_print(f"警告: 公告 {ann_id} 无中文内容数据")
                        continue

                    # 使用中文标题判断是否为有效活动
                    zh_title = self._remove_html_tags(
                        zh_content.get("title", announcement["title"])
                    )
                    self._debug_print(f"中文标题: {zh_title}")

                    if not self._is_valid_event(
                        zh_title
                    ) or "累计登录7天" in zh_content.get("content", ""):
                        self._debug_print("非有效活动公告，跳过")
                        continue

                    # 获取目标语言的公告数据
                    target_announcement = self._get_target_lang_announcement(
                        announcement, raw_data, lang
                    )
                    if not target_announcement:
                        self._debug_print(f"警告: 找不到 {lang} 语言的公告数据")
                        continue

                    # 获取目标语言的标题
                    title = self._remove_html_tags(target_announcement["title"])
                    self._debug_print(f"目标语言标题: {title}")

                    # 获取横幅图片（优先使用目标语言的图片）
                    banner_image = target_announcement.get(
                        "banner", announcement.get("banner", "")
                    )
                    self._debug_print(f"横幅图片: {banner_image[:50]}...")

                    # 获取时间（从中文内容中提取）
                    start_time, end_time = self._get_time_from_zh_content(
                        announcement, zh_content
                    )
                    self._debug_print(
                        f"从中文内容提取的时间: {start_time} 至 {end_time}"
                    )

                    if not start_time:
                        start_time = self._timestamp_to_datetime(
                            announcement.get("start_time", "")
                        )
                        self._debug_print(f"使用公告时间作为开始时间: {start_time}")
                    if not end_time:
                        end_time = self._timestamp_to_datetime(
                            announcement.get("end_time", "")
                        )
                        self._debug_print(f"使用公告时间作为结束时间: {end_time}")

                    parsed = {
                        "ann_id": ann_id,
                        "title": title,
                        "start_time": start_time,
                        "end_time": end_time,
                        "bannerImage": banner_image,
                        "event_type": "event",
                        "content": json.dumps(
                            raw_data["content_map"].get(ann_id, {}), ensure_ascii=False
                        ),
                        "lang": lang,
                    }

                    if self._add_to_result_if_unique(result_list, parsed):
                        self._debug_print("已添加到结果列表")

    def _parse_pic_announcements(
        self, raw_data: Dict, result_list: List[Dict], lang: str
    ):
        """解析图片列表中的公告"""
        # 使用中文列表数据进行解析
        zh_list_data = raw_data.get("zh_list", raw_data["list"])
        if "data" not in zh_list_data:
            self._debug_print("警告: 缺少data字段，无法解析图片公告")
            return

        pic_list = zh_list_data["data"]["pic_list"]
        self._debug_print(f"找到 {len(pic_list)} 个图片公告类别")

        for item in pic_list:
            for type_item in item["type_list"]:
                for announcement in type_item["list"]:
                    ann_id = announcement["ann_id"]
                    self._debug_print(f"\n处理图片公告 ID: {ann_id}")

                    # 获取中文内容
                    zh_content = raw_data["zh_pic_content_map"].get(ann_id, {})
                    if not zh_content:
                        self._debug_print(f"警告: 图片公告 {ann_id} 无中文内容数据")
                        continue

                    # 使用中文标题判断是否为有效活动
                    zh_title = self._remove_html_tags(
                        zh_content.get("title", announcement["title"])
                    )
                    self._debug_print(f"中文标题: {zh_title}")

                    if not self._is_valid_event(zh_title):
                        self._debug_print("非有效活动公告，跳过")
                        continue

                    # 获取目标语言的公告数据
                    target_announcement = self._get_target_lang_pic_announcement(
                        announcement, raw_data, lang
                    )
                    if not target_announcement:
                        self._debug_print(f"警告: 找不到 {lang} 语言的图片公告数据")
                        continue

                    # 获取目标语言的标题
                    title = self._remove_html_tags(target_announcement["title"])
                    self._debug_print(f"目标语言标题: {title}")

                    # 获取横幅图片（优先使用目标语言的图片）
                    banner_image = target_announcement.get(
                        "img", announcement.get("img", "")
                    )
                    self._debug_print(f"横幅图片: {banner_image[:50]}...")

                    # 获取时间（从中文内容中提取）
                    start_time, end_time = self._get_time_from_zh_content(
                        announcement, zh_content
                    )
                    self._debug_print(
                        f"从中文内容提取的时间: {start_time} 至 {end_time}"
                    )

                    if not start_time:
                        start_time = self._timestamp_to_datetime(
                            announcement.get("start_time", "")
                        )
                        self._debug_print(f"使用公告时间作为开始时间: {start_time}")
                    if not end_time:
                        end_time = self._timestamp_to_datetime(
                            announcement.get("end_time", "")
                        )
                        self._debug_print(f"使用公告时间作为结束时间: {end_time}")

                    parsed = {
                        "ann_id": ann_id,
                        "title": title,
                        "start_time": start_time,
                        "end_time": end_time,
                        "bannerImage": banner_image,
                        "event_type": "event",
                        "content": json.dumps(
                            raw_data["pic_content_map"].get(ann_id, {}),
                            ensure_ascii=False,
                        ),
                        "lang": lang,
                    }

                    if self._add_to_result_if_unique(result_list, parsed):
                        self._debug_print("已添加到结果列表")

    def _parse_gacha_announcements(
        self, raw_data: Dict, result_list: List[Dict], lang: str
    ):
        """解析限时频段(抽卡)公告"""
        # 1. 从常规公告中查找
        self._debug_print("从常规公告中查找限时频段公告")
        self._parse_normal_gacha_announcements(raw_data, result_list, lang)

        # 2. 从图片公告中查找
        self._debug_print("从图片公告中查找限时频段公告")
        self._parse_pic_gacha_announcements(raw_data, result_list, lang)

    def _parse_normal_gacha_announcements(
        self, raw_data: Dict, result_list: List[Dict], lang: str
    ):
        """解析常规限时频段公告"""
        # 使用中文列表数据进行解析
        zh_list_data = raw_data.get("zh_list", raw_data["list"])
        if "data" not in zh_list_data:
            self._debug_print("警告: 缺少data字段，无法解析限时频段公告")
            return

        gacha_list = zh_list_data["data"]["list"]
        self._debug_print(f"找到 {len(gacha_list)} 个公告类别")

        for item in gacha_list:
            if item.get("type_id") in [3, 4]:  # 活动类型ID
                self._debug_print(f"找到活动公告类别，包含 {len(item['list'])} 条公告")

                for announcement in item["list"]:
                    ann_id = announcement["ann_id"]
                    self._debug_print(f"\n处理公告 ID: {ann_id}")

                    # 获取中文内容
                    zh_content = raw_data["zh_content_map"].get(ann_id, {})
                    if not zh_content:
                        self._debug_print(f"警告: 公告 {ann_id} 无中文内容数据")
                        continue

                    # 使用中文标题判断是否为限时频段公告
                    zh_title = self._remove_html_tags(
                        zh_content.get("title", announcement["title"])
                    )
                    self._debug_print(f"中文标题: {zh_title}")

                    if "限时频段" not in zh_title and "调频" not in zh_title:
                        self._debug_print("非限时频段公告，跳过")
                        continue

                    # 获取目标语言的公告数据
                    target_announcement = self._get_target_lang_announcement(
                        announcement, raw_data, lang
                    )
                    if not target_announcement:
                        self._debug_print(f"警告: 找不到 {lang} 语言的公告数据")
                        continue

                    # 解析限时频段内容
                    parsed = self._parse_single_gacha(
                        announcement, target_announcement, zh_content, lang
                    )
                    if parsed:
                        result_list.append(parsed)
                        self._debug_print("已添加到结果列表")

    def _parse_pic_gacha_announcements(
        self, raw_data: Dict, result_list: List[Dict], lang: str
    ):
        """解析图片限时频段公告"""
        # 使用中文列表数据进行解析
        zh_list_data = raw_data.get("zh_list", raw_data["list"])
        if "data" not in zh_list_data:
            self._debug_print("警告: 缺少data字段，无法解析图片限时频段公告")
            return

        pic_list = zh_list_data["data"]["pic_list"]
        self._debug_print(f"找到 {len(pic_list)} 个图片公告类别")

        for item in pic_list:
            for type_item in item["type_list"]:
                for announcement in type_item["list"]:
                    ann_id = announcement["ann_id"]
                    self._debug_print(f"\n处理图片公告 ID: {ann_id}")

                    # 获取中文内容
                    zh_content = raw_data["zh_pic_content_map"].get(ann_id, {})
                    if not zh_content:
                        self._debug_print(f"警告: 图片公告 {ann_id} 无中文内容数据")
                        continue

                    # 使用中文标题判断是否为限时频段公告
                    zh_title = self._remove_html_tags(
                        zh_content.get("title", announcement["title"])
                    )
                    self._debug_print(f"中文标题: {zh_title}")

                    if "限时频段" not in zh_title and "调频" not in zh_title:
                        self._debug_print("非限时频段公告，跳过")
                        continue

                    # 获取目标语言的公告数据
                    target_announcement = self._get_target_lang_pic_announcement(
                        announcement, raw_data, lang
                    )
                    if not target_announcement:
                        self._debug_print(f"警告: 找不到 {lang} 语言的图片公告数据")
                        continue

                    # 解析限时频段内容
                    parsed = self._parse_single_pic_gacha(
                        announcement, target_announcement, zh_content, lang
                    )
                    if parsed:
                        result_list.append(parsed)
                        self._debug_print("已添加到结果列表")

    def _parse_single_gacha(
        self, announcement: Dict, target_announcement: Dict, zh_content: Dict, lang: str
    ) -> Optional[Dict]:
        """解析单个常规限时频段公告"""
        content = zh_content.get("content", "")
        zh_title = self._remove_html_tags(
            zh_content.get("title", announcement["title"])
        )

        # 提取调频活动名称
        gacha_names = re.findall(r"「([^」]+)」调频(?:说明|活动)", content)
        gacha_names = [
            name for name in gacha_names if name not in self.w_engine_gacha_names
        ]

        # 提取S级代理人和音擎
        s_agents = re.findall(
            r"限定S级代理人.*?<span[^>]*>\[([^(]+)(?:\([^)]*\))?\]</span>", content
        )
        s_weapons = re.findall(
            r"限定S级音擎.*?<span[^>]*>\[([^(]+)(?:\([^)]*\))?\]</span>", content
        )
        all_names = list(dict.fromkeys(s_agents + s_weapons))

        # 构建标题
        if lang == "zh-cn":
            if gacha_names and all_names:
                title = f"【{', '.join(gacha_names)}】代理人、音擎调频: {', '.join(all_names)}"
            else:
                title = zh_title
                if "限时频段" in title:
                    match = re.search(r"「([^」]+)」", title)
                    gacha_name = match.group(1) if match else "限时频段"
                    title = f"【{gacha_name}】限时频段"
        else:
            title = self._remove_html_tags(target_announcement["title"])

        # 处理时间
        start_time, end_time = self._get_time_from_zh_content(announcement, zh_content)

        # 如果没有从内容中解析到时间，使用公告中的时间
        if not start_time:
            start_time = self._timestamp_to_datetime(announcement.get("start_time", ""))
        if not end_time:
            end_time = self._timestamp_to_datetime(announcement.get("end_time", ""))

        # 获取横幅图片
        banner_image = target_announcement.get("banner", announcement.get("banner", ""))
        if not banner_image:
            soup = BeautifulSoup(content, "html.parser")
            img_tag = soup.find("img")
            if img_tag and "src" in img_tag.attrs:
                banner_image = img_tag["src"]

        return {
            "ann_id": announcement["ann_id"],
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "bannerImage": banner_image,
            "event_type": "gacha",
            "content": json.dumps(target_announcement, ensure_ascii=False),
            "lang": lang,
        }

    def _parse_single_pic_gacha(
        self, announcement: Dict, target_announcement: Dict, zh_content: Dict, lang: str
    ) -> Optional[Dict]:
        """解析单个图片限时频段公告"""
        content = zh_content.get("content", "")
        zh_title = self._remove_html_tags(
            zh_content.get("title", announcement["title"])
        )

        # 提取调频活动名称
        gacha_names = re.findall(r"「([^」]+)」调频(?:说明|活动)", content)
        gacha_names = [
            name for name in gacha_names if name not in self.w_engine_gacha_names
        ]

        # 提取S级代理人和音擎
        s_agents = re.findall(
            r"限定S级代理人.*?<span[^>]*>\[([^(]+)(?:\([^)]*\))?\]</span>", content
        )
        s_weapons = re.findall(
            r"限定S级音擎.*?<span[^>]*>\[([^(]+)(?:\([^)]*\))?\]</span>", content
        )
        all_names = list(dict.fromkeys(s_agents + s_weapons))

        # 构建标题
        if lang == "zh-cn":
            if gacha_names and all_names:
                title = f"【{', '.join(gacha_names)}】代理人、音擎调频: {', '.join(all_names)}"
            else:
                title = zh_title
                if "限时频段" in title:
                    match = re.search(r"「([^」]+)」", title)
                    gacha_name = match.group(1) if match else "限时频段"
                    title = f"【{gacha_name}】限时频段"
        else:
            title = self._remove_html_tags(target_announcement["title"])

        # 处理时间
        start_time, end_time = self._get_time_from_zh_content(announcement, zh_content)

        # 如果没有从内容中解析到时间，使用公告中的时间
        if not start_time:
            start_time = self._timestamp_to_datetime(announcement.get("start_time", ""))
        if not end_time:
            end_time = self._timestamp_to_datetime(announcement.get("end_time", ""))

        return {
            "ann_id": announcement["ann_id"],
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "bannerImage": target_announcement.get("img", announcement.get("img", "")),
            "event_type": "gacha",
            "content": json.dumps(target_announcement, ensure_ascii=False),
            "lang": lang,
        }

    def _get_target_lang_announcement(
        self, zh_announcement: Dict, raw_data: Dict, lang: str
    ) -> Optional[Dict]:
        """获取目标语言的公告数据"""
        if lang == "zh-cn":
            return zh_announcement

        if "list" not in raw_data or "data" not in raw_data["list"]:
            return None

        # 在目标语言列表中查找对应的公告
        ann_id = zh_announcement["ann_id"]
        for item in raw_data["list"]["data"]["list"]:
            for announcement in item["list"]:
                if announcement["ann_id"] == ann_id:
                    return announcement
        return None

    def _get_target_lang_pic_announcement(
        self, zh_announcement: Dict, raw_data: Dict, lang: str
    ) -> Optional[Dict]:
        """获取目标语言的图片公告数据"""
        if lang == "zh-cn":
            return zh_announcement

        if "list" not in raw_data or "data" not in raw_data["list"]:
            return None

        # 在目标语言图片列表中查找对应的公告
        ann_id = zh_announcement["ann_id"]
        for item in raw_data["list"]["data"]["pic_list"]:
            for type_item in item["type_list"]:
                for announcement in type_item["list"]:
                    if announcement["ann_id"] == ann_id:
                        return announcement
        return None

    def _get_time_from_zh_content(
        self, announcement: Dict, zh_content: Dict
    ) -> Tuple[str, str]:
        """从中文公告内容中提取时间信息"""
        if not zh_content or not isinstance(zh_content, dict):
            self._debug_print("无中文内容或内容格式错误")
            return "", ""

        # 获取公告中的默认时间
        start_time = self._timestamp_to_datetime(announcement.get("start_time", ""))
        end_time = self._timestamp_to_datetime(announcement.get("end_time", ""))
        self._debug_print(f"公告原始时间: {start_time} 至 {end_time}")

        # 尝试从中文内容中提取更准确的时间
        if "content" in zh_content:
            self._debug_print("尝试从中文HTML内容中提取时间")
            html_content = zh_content["content"]

            # 判断是活动公告还是抽卡公告
            if "限时频段" in zh_content.get("title", "") or "调频" in zh_content.get(
                "title", ""
            ):
                # 抽卡公告使用表格时间提取
                self._debug_print("检测到抽卡公告，使用表格时间提取")
                try:
                    content_start, content_end = self.extract_zzz_gacha_start_end_time(
                        html_content
                    )
                    content_start = content_start[:-1]
                    self._debug_print(
                        f"从表格中提取的时间: {content_start} - {content_end}"
                    )
                except Exception as e:
                    self._debug_print(f"抽卡时间提取失败: {str(e)}")
                    content_start, content_end = "", ""
            else:
                # 普通活动公告使用活动时间提取
                self._debug_print("检测到普通活动公告，使用活动时间提取")
                content_start, content_end = self.extract_zzz_event_start_end_time(
                    html_content
                )
                self._debug_print(
                    f"从活动中提取的时间: {content_start} ~ {content_end}"
                )

            # 解析提取到的时间
            if content_start:
                # 检查是否包含版本号
                if (
                    f"{self.version_now}版本" in content_start
                    and self.version_begin_time
                ):
                    self._debug_print(
                        f"检测到版本时间引用({self.version_now}版本)，使用版本开始时间"
                    )
                    start_time = self.version_begin_time
                else:
                    parsed_start = self._parse_content_time(content_start)
                    if parsed_start:
                        start_time = parsed_start
                        self._debug_print(f"更新开始时间为: {start_time}")

            if content_end:
                parsed_end = self._parse_content_time(content_end)
                if parsed_end:
                    end_time = parsed_end
                    self._debug_print(f"更新结束时间为: {end_time}")

        return start_time, end_time

    def _parse_content_time(self, time_str: str) -> str:
        """解析中文内容中的时间字符串为标准格式"""
        if not time_str:
            self._debug_print("空时间字符串")
            return ""

        try:
            # 处理中文日期格式
            time_str = (
                time_str.replace("年", "-")
                .replace("月", "-")
                .replace("日", "")
                .replace("/", "-")
                .replace("（服务器时间）", "")
                .strip()
            )

            # 尝试解析格式如 "2023-11-15 10:00" 或 "2023-11-15 10:00:00"
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    date_obj = datetime.strptime(time_str, fmt)
                    return date_obj.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

            # 如果上面都失败，尝试更宽松的解析
            if " " in time_str:
                date_part, time_part = time_str.split(" ", 1)
                date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                return f"{date_obj.strftime('%Y-%m-%d')} {time_part}:00"

            self._debug_print(f"无法解析的时间格式: {time_str}")
            return ""
        except Exception as e:
            self._debug_print(f"解析时间字符串失败: {time_str}, 错误: {str(e)}")
            return ""

    def _is_valid_event(self, zh_title: str) -> bool:
        """使用中文标题判断是否为有效活动公告"""
        invalid_keywords = ["全新放送", "『嗯呢』从天降", "特别访客", "惊喜派送中"]
        is_valid = ("活动说明" in zh_title or "活动公告" in zh_title) and not any(
            kw in zh_title for kw in invalid_keywords
        )
        self._debug_print(f"活动有效性检查: {'有效' if is_valid else '无效'}")
        return is_valid

    @staticmethod
    def _timestamp_to_datetime(timestamp: Union[str, int]) -> str:
        """将时间戳转换为日期时间字符串"""
        if not timestamp:
            return ""

        if isinstance(timestamp, str):
            try:
                # 尝试解析格式如 "2023-11-15 10:00:00"
                dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                return timestamp
            except ValueError:
                return ""
        else:
            try:
                # 处理毫秒时间戳
                dt = datetime.fromtimestamp(timestamp / 1000)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                return ""

    def _get_zh_title(self, announcement: Dict, raw_data: Dict) -> str:
        """获取公告的中文标题"""
        ann_id = announcement["ann_id"]
        zh_content = raw_data["zh_content_map"].get(ann_id, {})
        if zh_content and "title" in zh_content:
            self._debug_print(f"从中文内容映射获取标题: {zh_content['title']}")
            return zh_content["title"]
        self._debug_print(f"使用默认标题: {announcement['title']}")
        return announcement["title"]

    @staticmethod
    def _remove_html_tags(text: str) -> str:
        """移除HTML标签"""
        clean = re.compile("<.*?>")
        return re.sub(clean, "", text).strip()

    @staticmethod
    def _extract_floats(text: str) -> List[float]:
        """从文本中提取浮点数"""
        float_pattern = r"\d+\.\d+"
        floats = re.findall(float_pattern, text)
        return [float(f) for f in floats]

    @staticmethod
    def extract_zzz_event_start_end_time(html_content):
        """从活动公告HTML中提取开始和结束时间"""
        soup = BeautifulSoup(html_content, "html.parser")

        # 尝试第一种情况：【活动时间】在p标签的直接文本中
        activity_time_label = soup.find(
            "p", string=lambda text: text and "【活动时间】" in text
        )

        # 如果第一种情况没找到，尝试第二种情况：【活动时间】在span标签中
        if not activity_time_label:
            activity_time_span = soup.find(
                "span", string=lambda text: text and "【活动时间】" in text
            )
            if activity_time_span:
                activity_time_label = activity_time_span.find_parent("p")

        if activity_time_label:
            # 查找下一个p标签（可能是兄弟节点或下一个节点）
            activity_time_p = activity_time_label.find_next("p")

            if activity_time_p:
                activity_time_text = activity_time_p.get_text(strip=True)

                # 处理分隔符（支持 - 或 ~）
                if "-" in activity_time_text:
                    start, end = activity_time_text.split("-", 1)
                elif "~" in activity_time_text:
                    start, end = activity_time_text.split("~", 1)
                else:
                    return "", ""  # 返回空值

                # 清理时间字符串
                start = start.replace("（服务器时间）", "").strip()
                end = end.replace("（服务器时间）", "").strip()
                return start, end

        return "", ""

    @staticmethod
    def extract_zzz_gacha_start_end_time(html_content):
        """从抽卡公告HTML中提取开始和结束时间"""
        soup = BeautifulSoup(html_content, "html.parser")
        table = soup.find("table")
        if table is None:
            return "", ""

        tbody = table.find("tbody")
        rows = tbody.find_all("tr")

        # 查找包含时间的行（通常是第一个 <tr> 之后的 <tr>）
        time_row = rows[1] if len(rows) > 1 else None
        if not time_row:
            return "", ""

        # 查找包含时间的单元格（通常是带有 rowspan 的 <td>）
        time_cell = time_row.find("td", {"rowspan": True})
        if not time_cell:
            return "", ""

        # 提取所有时间文本（可能包含多个活动的开始和结束时间）
        time_texts = [p.get_text(strip=True) for p in time_cell.find_all("p")]

        # 如果没有足够的时间信息，返回空字符串
        if len(time_texts) < 2:
            return "", ""

        # 提取第一个活动的时间（通常是第一个 <p>）
        start_time = time_texts[0]

        # 尝试提取结束时间（可能是最后一个 <p> 或倒数第二个 <p>）
        end_time = time_texts[-1] if len(time_texts) >= 2 else ""

        # 清理时间格式（去除多余的空格和换行）
        start_time = re.sub(r"\s+", " ", start_time).strip()
        end_time = re.sub(r"\s+", " ", end_time).strip()

        return start_time, end_time


# 使用示例
if __name__ == "__main__":
    with open("mihoyo_all_data.json", "r", encoding="utf-8") as f:
        all_data = json.load(f)

    sample_data = all_data["Zenless"]

    # 初始化解析器（启用调试模式）
    parser = ZenlessParser(debug=True)

    # 获取游戏的语言设置
    lang = sample_data.get("lang", "zh-tw")
    print(f"绝区零公告语言: {lang}")

    # 解析公告数据
    try:
        parsed_announcements = parser.parse(sample_data, lang)

        # 按类型统计公告数量
        type_counts = {"version": 0, "event": 0, "gacha": 0}

        for ann in parsed_announcements:
            type_counts[ann["event_type"]] += 1

        # 打印摘要信息
        print(f"\n解析到 {len(parsed_announcements)} 条绝区零公告:")
        print(f"  • 版本公告: {type_counts['version']} 条")
        print(f"  • 活动公告: {type_counts['event']} 条")
        print(f"  • 限时频段公告: {type_counts['gacha']} 条")

        # 打印版本信息
        if type_counts["version"] > 0:
            print(f"\n当前绝区零版本: {parser.version_now}")
            print(f"版本开始时间: {parser.version_begin_time}")

        # 打印各类公告示例
        print("\n=== 版本公告示例 ===")
        version_anns = [a for a in parsed_announcements if a["event_type"] == "version"]
        for ann in version_anns[:1]:  # 只显示最新版本
            print(f"标题: {ann['title']}")
            print(f"时间: {ann['start_time']} 至 {ann['end_time']}")
            if ann["bannerImage"]:
                print(f"横幅: {ann['bannerImage'][:60]}...")

        print("\n=== 活动公告示例 ===")
        event_anns = [a for a in parsed_announcements if a["event_type"] == "event"]
        for ann in event_anns[:5]:  # 显示5个活动
            print(f"标题: {ann['title']}")
            print(f"时间: {ann['start_time']} 至 {ann['end_time']}")
            if ann["bannerImage"]:
                print(f"横幅: {ann['bannerImage'][:60]}...")
            print()

        print("\n=== 限时频段公告示例 ===")
        gacha_anns = [a for a in parsed_announcements if a["event_type"] == "gacha"]
        for ann in gacha_anns[:5]:  # 显示5个限时频段
            print(f"标题: {ann['title']}")
            print(f"时间: {ann['start_time']} 至 {ann['end_time']}")
            if ann["bannerImage"]:
                print(f"横幅: {ann['bannerImage'][:60]}...")
            print()

    except Exception as e:
        print(f"解析绝区零公告时出错: {str(e)}")
