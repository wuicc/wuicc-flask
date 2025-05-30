import re
import json
from datetime import datetime
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Tuple, Union


class StarRailParser:
    """崩坏：星穹铁道(Star Rail)公告解析器（国际化版）"""

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
        解析星穹铁道公告数据（支持多语言）

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
        self._debug_print(f"开始解析星穹铁道公告数据，语言: {lang}")
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

        # 3. 处理图片列表中的活动公告
        self._debug_print("\n=== 开始解析图片活动公告 ===")
        self._parse_pic_announcements(raw_data, filtered_list, lang)

        # 4. 处理跃迁(抽卡)公告
        self._debug_print("\n=== 开始解析跃迁公告 ===")
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
            if item["type_label"] == "公告":
                self._debug_print(f"找到公告类别，包含 {len(item['list'])} 条公告")

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
            if item["type_label"] == "公告":
                self._debug_print(f"找到公告类别，包含 {len(item['list'])} 条公告")

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

    def _parse_pic_announcements(
        self, raw_data: Dict, result_list: List[Dict], lang: str
    ):
        """解析图片列表中的活动公告"""
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

                    result_list.append(parsed)
                    self._debug_print("已添加到结果列表")

    def _parse_gacha_announcements(
        self, raw_data: Dict, result_list: List[Dict], lang: str
    ):
        """解析跃迁(抽卡)公告"""
        # 使用中文列表数据进行解析
        zh_list_data = raw_data.get("zh_list", raw_data["list"])
        if "data" not in zh_list_data:
            self._debug_print("警告: 缺少data字段，无法解析跃迁公告")
            return

        # 1. 从图片公告中查找
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

                    # 使用中文标题判断是否为跃迁公告
                    zh_title = self._remove_html_tags(
                        zh_content.get("title", announcement["title"])
                    )
                    self._debug_print(f"中文标题: {zh_title}")

                    if "跃迁" not in zh_title:
                        self._debug_print("非跃迁公告，跳过")
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

                    # 如果是中文，使用专门解析的标题
                    if lang in ["zh-cn"]:
                        title = self._parse_gacha_content(zh_title, zh_content)
                        self._debug_print(f"中文跃迁公告，使用解析后的标题: {title}")
                    else:
                        self._debug_print(f"非中文跃迁公告，保持原标题: {title}")

                    # 获取横幅图片（优先使用目标语言的图片）
                    banner_image = target_announcement.get(
                        "img", announcement.get("img", "")
                    )
                    if not banner_image and "img" in zh_content:
                        banner_image = zh_content["img"]
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
                            raw_data["pic_content_map"].get(ann_id, {}),
                            ensure_ascii=False,
                        ),
                        "lang": lang,
                    }

                    result_list.append(parsed)
                    self._debug_print("已添加到结果列表")

    def _parse_gacha_content(self, zh_title: str, zh_content: Dict) -> str:
        """使用中文内容解析跃迁公告并生成标准化标题"""
        if not zh_content or not isinstance(zh_content, dict):
            self._debug_print("无中文内容或内容格式错误，使用基本标准化标题")
            return self._standardize_gacha_title(zh_title)

        html_content = zh_content.get("content", "")
        if not html_content:
            self._debug_print("无中文HTML内容，使用基本标准化标题")
            return self._standardize_gacha_title(zh_title)

        self._debug_print("使用中文内容解析跃迁信息...")

        # 提取跃迁名称
        gacha_names = re.findall(
            r"<h1[^>]*>「([^」]+)」[^<]*活动跃迁</h1>", html_content
        )
        self._debug_print(f"从HTML提取的跃迁名称: {gacha_names}")

        # 过滤角色跃迁名称
        role_gacha_names = []
        for name in gacha_names:
            if "•" not in name:  # 排除光锥跃迁名称
                role_gacha_names.append(name)
            elif "铭心之萃" in name:  # 特殊情况处理
                role_gacha_names.append(name.split("•")[0])
        role_gacha_names = list(dict.fromkeys(role_gacha_names))
        self._debug_print(f"过滤后的角色跃迁名称: {role_gacha_names}")

        # 提取角色和光锥
        five_star_characters = re.findall(r"限定5星角色「([^（」]+)", html_content)
        five_star_characters = list(dict.fromkeys(five_star_characters))
        self._debug_print(f"提取的5星角色: {five_star_characters}")

        five_star_light_cones = re.findall(r"限定5星光锥「([^（」]+)", html_content)
        five_star_light_cones = list(dict.fromkeys(five_star_light_cones))
        self._debug_print(f"提取的5星光锥: {five_star_light_cones}")

        # 构建标题
        if role_gacha_names:
            title = f"【{', '.join(role_gacha_names)}】"
        else:
            title = "【跃迁】"

        if five_star_characters or five_star_light_cones:
            title += f"角色、光锥跃迁: {', '.join(five_star_characters + five_star_light_cones)}"
        else:
            title += "跃迁活动"

        self._debug_print(f"最终生成的标题: {title}")
        return title

    def _standardize_gacha_title(self, zh_title: str) -> str:
        """标准化中文跃迁公告标题"""
        if "限定" in zh_title and ("角色" in zh_title or "光锥" in zh_title):
            self._debug_print("标准化为限定跃迁标题")
            return f"【限定跃迁】{zh_title}"
        self._debug_print("标准化为普通跃迁标题")
        return f"【跃迁】{zh_title}"

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

        # 在目标语言列表中查找对应的图片公告
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
        """从中文公告内容中提取时间信息（改进版）"""
        if not zh_content or not isinstance(zh_content, dict):
            self._debug_print("无中文内容或内容格式错误")
            return "", ""

        # 获取公告中的原始时间
        start_time = self._timestamp_to_datetime(announcement.get("start_time", ""))
        end_time = self._timestamp_to_datetime(announcement.get("end_time", ""))
        self._debug_print(f"公告原始时间: {start_time} 至 {end_time}")

        # 判断是否是跃迁公告
        is_gacha = "跃迁" in zh_content.get("title", "")

        # 从HTML内容中提取更准确的时间
        if "content" in zh_content:
            html_content = zh_content["content"]

            if is_gacha:
                # 跃迁公告时间提取
                extracted_time = self._extract_sr_gacha_time(html_content)
            else:
                # 活动公告时间提取
                extracted_time = self._extract_sr_event_time(html_content)

            if extracted_time:
                start_time = extracted_time

                # 对于活动公告，尝试提取结束时间
                if not is_gacha:
                    end_time_part = self._extract_sr_event_end_time(html_content)
                    if end_time_part:
                        end_time = self._format_extracted_time(end_time_part)

        # 处理版本更新后的特殊情况
        if f"{self.version_now}版本" in start_time or "版本更新后" in start_time:
            start_time = self.version_begin_time
            self._debug_print("检测到版本时间引用，使用版本开始时间")

        return start_time, end_time

    def _extract_sr_event_time(self, html_content: str) -> str:
        """从活动公告HTML内容中提取开始时间"""
        pattern = r"<h1[^>]*>(?:活动时间|限时活动期)</h1>\s*<p[^>]*>(.*?)</p>"
        match = re.search(pattern, html_content, re.DOTALL)
        self._debug_print(f"活动时间提取结果: {match}")

        if match:
            time_info = match.group(1)
            cleaned_time_info = re.sub("&lt;.*?&gt;", "", time_info)
            if "-" in cleaned_time_info:
                return cleaned_time_info.split("-")[0].strip()
            return cleaned_time_info
        return ""

    def _extract_sr_event_end_time(self, html_content: str) -> str:
        """从活动公告HTML内容中提取结束时间"""
        pattern = r"<h1[^>]*>(?:活动时间|限时活动期)</h1>\s*<p[^>]*>(.*?)</p>"
        match = re.search(pattern, html_content, re.DOTALL)

        if match:
            time_info = match.group(1)
            cleaned_time_info = re.sub("&lt;.*?&gt;", "", time_info)
            if "-" in cleaned_time_info:
                return cleaned_time_info.split("-")[1].strip()
        return ""

    def _extract_sr_gacha_time(self, html_content: str) -> str:
        """从跃迁公告HTML内容中提取时间"""
        pattern = r"时间为(.*?)，包含如下内容"
        matches = re.findall(pattern, html_content)
        self._debug_print(f"跃迁时间提取结果: {matches}")

        if matches:
            time_range = re.sub("&lt;.*?&gt;", "", matches[0].strip())
            if "-" in time_range:
                return time_range.split("-")[0].strip()
            return time_range
        return ""

    def _format_extracted_time(self, time_str: str) -> str:
        """格式化提取到的时间字符串"""
        if not time_str:
            return ""

        # 处理特殊时间格式
        time_str = time_str.replace("年", "/").replace("月", "/").replace("日", "")
        time_str = re.sub(r"[^\d/ :]", "", time_str).strip()

        try:
            # 尝试解析格式 "2023/11/15 10:00:00"
            date_obj = datetime.strptime(time_str, "%Y/%m/%d %H:%M:%S")
            return date_obj.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                # 尝试解析没有秒数的格式 "2023/11/15 10:00"
                date_obj = datetime.strptime(time_str, "%Y/%m/%d %H:%M")
                return date_obj.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                self._debug_print(f"时间格式解析失败: {time_str}")
                return ""

    def _is_valid_event(self, title: str) -> bool:
        """使用中文标题判断是否为有效活动公告"""
        invalid_keywords = [
            "跃迁",
            "模拟宇宙",
            "礼包",
            "纪行",
            "限时折扣",
            "任务",
            "音乐",
        ]
        is_valid = ("等奖励" in title) and not any(
            kw in title for kw in invalid_keywords
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


# 使用示例
def main():
    # 读取包含所有游戏数据的JSON文件
    with open("mihoyo_all_data.json", "r", encoding="utf-8") as f:
        all_data = json.load(f)

    # 只获取星穹铁道(sr)的数据
    if "sr" not in all_data:
        print("错误：未找到星穹铁道(sr)的公告数据")
        return

    sr_data = all_data["sr"]

    # 初始化星穹铁道解析器（启用调试模式）
    parser = StarRailParser(debug=True)

    # 获取游戏的语言设置
    lang = sr_data.get("lang", "zh-tw")
    print(f"星穹铁道公告语言: {lang}")

    # 解析星穹铁道公告数据
    try:
        parsed_announcements = parser.parse(sr_data, lang)

        # 按类型统计公告数量
        type_counts = {"version": 0, "event": 0, "gacha": 0}

        for ann in parsed_announcements:
            type_counts[ann["event_type"]] += 1

        # 打印摘要信息
        print(f"\n解析到 {len(parsed_announcements)} 条星穹铁道公告:")
        print(f"  • 版本公告: {type_counts['version']} 条")
        print(f"  • 活动公告: {type_counts['event']} 条")
        print(f"  • 跃迁公告: {type_counts['gacha']} 条")

        # 打印版本信息
        if type_counts["version"] > 0:
            print(f"\n当前星穹铁道版本: {parser.version_now}")
            print(f"版本开始时间: {parser.version_begin_time}")

        # 打印各类公告示例
        print("\n=== 版本公告示例 ===")
        version_anns = [a for a in parsed_announcements if a["event_type"] == "version"]
        for ann in version_anns[:1]:  # 只显示最新版本
            print(f"标题: {ann['title']}")
            print(f"时间: {ann['start_time']} 至 {ann['end_time']}")
            if ann["bannerImage"]:
                print(f"横幅: {ann['bannerImage'][:600]}...")

        print("\n=== 活动公告示例 ===")
        event_anns = [a for a in parsed_announcements if a["event_type"] == "event"]
        for ann in event_anns[:5]:  # 显示2个活动
            print(f"标题: {ann['title']}")
            print(f"时间: {ann['start_time']} 至 {ann['end_time']}")
            if ann["bannerImage"]:
                print(f"横幅: {ann['bannerImage'][:600]}...")
            print()

        print("\n=== 跃迁公告示例 ===")
        gacha_anns = [a for a in parsed_announcements if a["event_type"] == "gacha"]
        for ann in gacha_anns[:5]:  # 显示2个跃迁
            print(f"标题: {ann['title']}")
            print(f"时间: {ann['start_time']} 至 {ann['end_time']}")
            if ann["bannerImage"]:
                print(f"横幅: {ann['bannerImage'][:600]}...")
            print()

    except Exception as e:
        print(f"解析星穹铁道公告时出错: {str(e)}")


if __name__ == "__main__":
    main()
