import re
import json
from datetime import datetime
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Tuple, Union


class GenshinParser:
    """原神(Genshin Impact)公告解析器（优化版）"""

    def __init__(self, debug=True):
        self.version_now = "1.0"
        self.version_begin_time = ""
        self.supported_languages = ["zh-cn", "zh-tw", "en", "ja", "ko"]
        self.debug = debug  # 调试模式开关

    def _debug_print(self, *args, **kwargs):
        """调试输出"""
        if self.debug:
            print("[DEBUG]", *args, **kwargs)

    def parse(self, raw_data: Dict, lang: str = "zh-cn") -> List[Dict]:
        """
        解析原神公告数据（支持多语言）

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
        self._debug_print(f"开始解析原神公告数据，语言: {lang}")
        self._debug_print(f"原始数据键: {raw_data.keys()}")

        if lang not in self.supported_languages:
            lang = "zh-cn"
            self._debug_print(f"不支持的语言，已重置为默认语言: {lang}")

        filtered_list = []

        # 1. 处理版本公告
        self._debug_print("\n=== 开始解析版本公告 ===")
        self._parse_version_announcements(raw_data, filtered_list, lang)

        # 2. 处理活动公告
        self._debug_print("\n=== 开始解析活动公告 ===")
        self._parse_event_announcements(raw_data, filtered_list, lang)

        # 3. 处理祈愿(抽卡)公告
        self._debug_print("\n=== 开始解析祈愿公告 ===")
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

                    if "版本更新说明" in clean_zh_title:
                        self._debug_print("检测到版本更新公告")

                        # 提取版本号
                        version_numbers = self._extract_version_number(clean_zh_title)
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
                            continue

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
                                f"{self.version_now}" if lang == "zh-cn" else title
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

    def _parse_event_announcements(
        self, raw_data: Dict, result_list: List[Dict], lang: str
    ):
        """解析活动公告"""
        # 使用中文列表数据进行解析
        zh_list_data = raw_data.get("zh_list", raw_data["list"])
        if "data" not in zh_list_data:
            self._debug_print("警告: 缺少data字段，无法解析活动公告")
            return

        event_list = zh_list_data["data"]["list"]
        self._debug_print(f"找到 {len(event_list)} 个公告类别")

        for item in event_list:
            if item["type_label"] == "活动公告":
                self._debug_print(f"找到活动公告类别，包含 {len(item['list'])} 条公告")

                for announcement in item["list"]:
                    ann_id = announcement["ann_id"]
                    self._debug_print(f"\n处理公告 ID: {ann_id}")

                    # 获取中文内容
                    # print(
                    #     list(raw_data["zh_content_map"].keys())[2],
                    #     type(list(raw_data["zh_content_map"].keys())[2]),
                    #     type(ann_id),
                    # )
                    zh_content = raw_data["zh_content_map"].get(ann_id, {})
                    if not zh_content:
                        self._debug_print(f"警告: 公告 {ann_id} 无中文内容数据")
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

                    result_list.append(parsed)
                    self._debug_print("已添加到结果列表")

    def _parse_gacha_announcements(
        self, raw_data: Dict, result_list: List[Dict], lang: str
    ):
        """解析祈愿(抽卡)公告"""
        # 使用中文列表数据进行解析
        zh_list_data = raw_data.get("zh_list", raw_data["list"])
        if "data" not in zh_list_data:
            self._debug_print("警告: 缺少data字段，无法解析祈愿公告")
            return

        gacha_list = zh_list_data["data"]["list"]
        self._debug_print(f"找到 {len(gacha_list)} 个公告类别")

        for item in gacha_list:
            if item["type_label"] == "活动公告":
                self._debug_print(f"找到活动公告类别，包含 {len(item['list'])} 条公告")

                for announcement in item["list"]:
                    ann_id = announcement["ann_id"]
                    self._debug_print(f"\n处理公告 ID: {ann_id}")

                    # 获取中文内容
                    zh_content = raw_data["zh_content_map"].get(ann_id, {})
                    if not zh_content:
                        self._debug_print(f"警告: 公告 {ann_id} 无中文内容数据")
                        continue

                    # 使用中文标题判断是否为祈愿公告
                    zh_title = self._remove_html_tags(
                        zh_content.get("title", announcement["title"])
                    )
                    self._debug_print(f"中文标题: {zh_title}")

                    if (
                        announcement.get("tag_label") != "扭蛋"
                        and "祈愿" not in zh_title
                    ):
                        self._debug_print("非祈愿公告，跳过")
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

                    # 如果是中文，使用专门解析的标题
                    if lang in ["zh-cn"]:
                        title = self._parse_gacha_content(zh_title, zh_content)
                        self._debug_print(f"中文祈愿公告，使用解析后的标题: {title}")
                    else:
                        self._debug_print(f"非中文祈愿公告，保持原标题: {title}")

                    # 获取横幅图片（优先使用目标语言的图片）
                    banner_image = target_announcement.get(
                        "banner", announcement.get("banner", "")
                    )
                    if not banner_image and "banner" in zh_content:
                        banner_image = zh_content["banner"]
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
                        "event_type": "gacha",
                        "content": json.dumps(
                            raw_data["content_map"].get(ann_id, {}), ensure_ascii=False
                        ),
                        "lang": lang,
                    }

                    result_list.append(parsed)
                    self._debug_print("已添加到结果列表")

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

    def _parse_gacha_content(self, zh_title: str, zh_content: Dict) -> str:
        """使用中文内容解析祈愿公告并生成标准化标题"""
        if not zh_content or not isinstance(zh_content, dict):
            self._debug_print("无中文内容或内容格式错误，使用基本标准化标题")
            return self._standardize_gacha_title(zh_title)

        html_content = zh_content.get("content", "")
        if not html_content:
            self._debug_print("无中文HTML内容，使用基本标准化标题")
            return self._standardize_gacha_title(zh_title)

        self._debug_print("使用中文内容解析祈愿信息...")

        # 处理不同类型的祈愿
        if "神铸赋形" in zh_title:  # 武器祈愿
            self._debug_print("检测到武器祈愿")
            weapon_names = re.findall(r"「[^」]*·([^」]*)」", zh_title)
            result = f"【神铸赋形】武器祈愿: {', '.join(weapon_names)}"
            self._debug_print(f"武器名称提取结果: {weapon_names}")
            return result
        elif "集录" in zh_title:  # 集录祈愿
            self._debug_print("检测到集录祈愿")
            match = re.search(r"「([^」]+)」祈愿", zh_title)
            gacha_name = match.group(1) if match else "集录祈愿"
            result = f"【{gacha_name}】集录祈愿"
            self._debug_print(f"集录祈愿名称: {gacha_name}")
            return result
        else:  # 角色祈愿
            self._debug_print("检测到角色祈愿")
            # 尝试从中文内容中提取角色名
            soup = BeautifulSoup(html_content, "html.parser")
            character_name = ""

            # 查找包含角色名的段落
            for p in soup.find_all("p"):
                text = p.get_text(strip=True)
                if "·" in text and "(" in text:
                    char_match = re.search(r"·(.*?)\(", text)
                    if char_match:
                        character_name = char_match.group(1).strip()
                        self._debug_print(f"从段落中提取角色名: {character_name}")
                        break

            # 从中文标题中提取祈愿名称
            gacha_match = re.search(r"「([^」]+)」祈愿", zh_title)
            gacha_name = gacha_match.group(1) if gacha_match else "角色祈愿"
            self._debug_print(f"祈愿名称: {gacha_name}")

            return (
                f"【{gacha_name}】角色祈愿: {character_name}"
                if character_name
                else zh_title
            )

    def _standardize_gacha_title(self, zh_title: str) -> str:
        """标准化中文祈愿公告标题"""
        if "神铸赋形" in zh_title:
            self._debug_print("标准化为武器祈愿标题")
            return f"【神铸赋形】{zh_title}"
        elif "集录" in zh_title:
            self._debug_print("标准化为集录祈愿标题")
            return f"【集录祈愿】{zh_title}"
        self._debug_print("标准化为角色祈愿标题")
        return f"【角色祈愿】{zh_title}"

    def _is_valid_event(self, zh_title: str) -> bool:
        """使用中文标题判断是否为有效活动公告"""
        invalid_keywords = [
            "祈愿",
            "魔神任务",
            "礼包",
            "纪行",
            "铸境研炼",
            "七圣召唤",
            "限时折扣",
        ]
        is_valid = ("时限内" in zh_title or "活动" in zh_title) and not any(
            kw in zh_title for kw in invalid_keywords
        )
        self._debug_print(f"活动有效性检查: {'有效' if is_valid else '无效'}")
        return is_valid

    def _parse_content_time(self, time_str: str) -> str:
        """解析中文内容中的时间字符串为标准格式"""
        if not time_str:
            self._debug_print("空时间字符串")
            return ""

        try:
            # 尝试解析格式如 "2023年11月15日10:00"
            time_str = time_str.replace("年", "-").replace("月", "-").replace("日", "")
            date_obj = datetime.strptime(time_str, "%Y-%m-%d%H:%M")
            result = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            self._debug_print(f"解析时间字符串成功: {time_str} -> {result}")
            return result
        except ValueError as e:
            self._debug_print(f"解析时间字符串失败: {time_str}, 错误: {str(e)}")
            return ""

    @staticmethod
    def _extract_version_number(text: str) -> List[float]:
        """从中文文本中提取版本号"""
        version_pattern = r"(\d+\.\d+)"
        versions = re.findall(version_pattern, text)
        return [float(v) for v in versions] if versions else []

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

    def _extract_event_start_time(self, html_content: str) -> str:
        """从活动公告HTML内容中提取开始时间"""
        if not html_content:
            return ""

        # 检查是否有"版本更新后"的特殊情况
        if "版本更新后" in html_content:
            return self.version_begin_time

        # 尝试直接匹配时间格式 "2023/11/15 10:00"
        time_pattern = r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}"
        match = re.search(time_pattern, html_content)
        if match:
            return self._format_extracted_time(match.group())

        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(html_content, "html.parser")

        # 查找包含"〓获取奖励时限〓"或"〓活动时间〓"的标签
        time_title = soup.find(string="〓获取奖励时限〓") or soup.find(
            string="〓活动时间〓"
        )
        if time_title:
            time_paragraph = time_title.find_next("p")
            if time_paragraph:
                time_range = time_paragraph.get_text()
                if "~" in time_range:
                    start_time = time_range.split("~")[0].strip()
                    return self._format_extracted_time(
                        self._remove_html_tags(start_time)
                    )
                return self._format_extracted_time(self._remove_html_tags(time_range))

        return ""

    def _extract_gacha_start_time(
        self, html_content: str, is_collection: bool = False
    ) -> str:
        """从祈愿公告HTML内容中提取开始时间"""
        if not html_content:
            return ""

        soup = BeautifulSoup(html_content, "html.parser")

        if is_collection:
            # 集录祈愿的特殊处理
            time_td = soup.find("td", {"rowspan": lambda x: x and int(x) >= 3})
            if time_td:
                time_tag = time_td.find("t", {"class": "t_lc"})
                if time_tag:
                    return self._format_extracted_time(time_tag.text)

                time_text = time_td.get_text()
                time_match = re.search(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}", time_text)
                if time_match:
                    return self._format_extracted_time(time_match.group())
        else:
            # 常规祈愿处理
            for rowspan in ["3", "5", "9"]:
                td_element = soup.find("td", {"rowspan": rowspan})
                if td_element:
                    time_texts = []
                    for child in td_element.children:
                        if child.name in ["p", "t"]:
                            span = child.find("span")
                            time_texts.append(
                                span.get_text() if span else child.get_text()
                            )

                    if time_texts:
                        time_range = " ".join(time_texts)
                        if "~" in time_range:
                            return self._format_extracted_time(
                                time_range.split("~")[0].strip()
                            )
                        return self._format_extracted_time(time_range)

        return ""

    def _format_extracted_time(self, time_str: str) -> str:
        """格式化提取到的时间字符串"""
        if not time_str:
            return ""

        # 处理"版本更新后"的特殊情况
        if f"{self.version_now}版本" in time_str or "版本更新后" in time_str:
            return self.version_begin_time

        try:
            # 统一处理各种时间格式
            time_str = time_str.replace("年", "/").replace("月", "/").replace("日", "")
            time_str = re.sub(r"[^\d/ :]", "", time_str).strip()

            # 尝试解析格式 "2023/11/15 10:00"
            if time_str[-1:] == "/":
                time_str = time_str[:-1]
            date_obj = datetime.strptime(time_str, "%Y/%m/%d %H:%M")
            return date_obj.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            self._debug_print(f"时间格式解析失败: {time_str}")
            return ""

    def _get_time_from_zh_content(
        self, announcement: Dict, zh_content: Dict
    ) -> Tuple[str, str]:
        """从中文公告内容中提取时间信息"""
        if not zh_content or not isinstance(zh_content, dict):
            return "", ""

        # 获取公告中的原始时间
        start_time = self._timestamp_to_datetime(announcement.get("start_time", ""))
        end_time = self._timestamp_to_datetime(announcement.get("end_time", ""))

        # 从HTML内容中提取更准确的时间
        if "content" in zh_content:
            html_content = zh_content["content"]

            # 判断是否是祈愿公告
            is_gacha = announcement.get(
                "tag_label"
            ) == "扭蛋" or "祈愿" in zh_content.get("title", "")
            is_collection = "集录" in zh_content.get("title", "")

            if is_gacha:
                extracted_time = self._extract_gacha_start_time(
                    html_content, is_collection
                )
            else:
                extracted_time = self._extract_event_start_time(html_content)

            if extracted_time:
                start_time = extracted_time

                # 对于活动公告，尝试提取结束时间
                if not is_gacha:
                    soup = BeautifulSoup(html_content, "html.parser")
                    time_title = soup.find(string="〓获取奖励时限〓") or soup.find(
                        string="〓活动时间〓"
                    )
                    if time_title:
                        time_paragraph = time_title.find_next("p")
                        if time_paragraph and "~" in time_paragraph.get_text():
                            end_time_part = (
                                time_paragraph.get_text().split("~")[1].strip()
                            )
                            end_time = self._format_extracted_time(
                                self._remove_html_tags(end_time_part)
                            )

        return start_time, end_time


# 使用示例
def main():
    # 读取包含所有游戏数据的JSON文件
    with open("mihoyo_all_data.json", "r", encoding="utf-8") as f:
        all_data = json.load(f)

    # 只获取原神(ys)的数据
    if "ys" not in all_data:
        print("错误：未找到原神(ys)的公告数据")
        return

    ys_data = all_data["ys"]

    # 初始化原神解析器（启用调试模式）
    parser = GenshinParser(debug=True)

    # 获取游戏的语言设置
    lang = ys_data.get("lang", "zh-tw")
    print(f"原神公告语言: {lang}")

    # 解析原神公告数据
    try:
        parsed_announcements = parser.parse(ys_data, lang)

        # 按类型统计公告数量
        type_counts = {"version": 0, "event": 0, "gacha": 0}

        for ann in parsed_announcements:
            type_counts[ann["event_type"]] += 1

        # 打印摘要信息
        print(f"\n解析到 {len(parsed_announcements)} 条原神公告:")
        print(f"  • 版本公告: {type_counts['version']} 条")
        print(f"  • 活动公告: {type_counts['event']} 条")
        print(f"  • 祈愿公告: {type_counts['gacha']} 条")

        # 打印版本信息
        if type_counts["version"] > 0:
            print(f"\n当前原神版本: {parser.version_now}")
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
        for ann in event_anns[:5]:  # 显示2个活动
            print(f"标题: {ann['title']}")
            print(f"时间: {ann['start_time']} 至 {ann['end_time']}")
            if ann["bannerImage"]:
                print(f"横幅: {ann['bannerImage'][:60]}...")
            print()

        print("\n=== 祈愿公告示例 ===")
        gacha_anns = [a for a in parsed_announcements if a["event_type"] == "gacha"]
        for ann in gacha_anns[:5]:  # 显示2个祈愿
            print(f"标题: {ann['title']}")
            print(f"时间: {ann['start_time']} 至 {ann['end_time']}")
            if ann["bannerImage"]:
                print(f"横幅: {ann['bannerImage'][:60]}...")
            print()

    except Exception as e:
        print(f"解析原神公告时出错: {str(e)}")


if __name__ == "__main__":
    main()
