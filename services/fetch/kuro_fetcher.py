import requests, json
from typing import Dict, List, Optional


class KuroFetcher:
    """库洛游戏公告抓取器（鸣潮）"""

    def __init__(self):
        self.session = requests.Session()
        self._setup_session()
        self._load_announcement_links()

    def _load_announcement_links(self):
        """从ann_link.json加载公告链接"""
        try:
            with open("data/ann_link.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                self.list_url = data.get("wuthering", {}).get("annListApi")
        except Exception as e:
            print(f"Error loading announcement links: {e}")

    def _setup_session(self):
        """配置请求会话"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        self.session.headers.update(headers)
        self.session.timeout = 10

    def fetch_announcement_list(self) -> Optional[Dict]:
        """抓取公告总列表"""
        try:
            response = self.session.get(self.list_url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching announcement list: {e}")
            return None
        except ValueError as e:
            print(f"Error parsing announcement list: {e}")
            return None

    def fetch_announcement_content(self, content_url: str) -> Optional[Dict]:
        """抓取单个公告内容"""
        try:
            response = self.session.get(content_url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching announcement content: {e}")
            return None
        except ValueError as e:
            print(f"Error parsing announcement content: {e}")
            return None

    def fetch_zh_content(self, content_prefix: str) -> Optional[Dict]:
        """专门获取中文内容用于时间解析"""
        zh_content_url = content_prefix + "zh-Hans.json"
        return self.fetch_announcement_content(zh_content_url)

    def fetch_all_announcements(self) -> Optional[Dict]:
        """
        抓取所有鸣潮公告数据

        Returns:
            {
                "game": 游戏版本公告,
                "activity": 活动公告列表（包含详情内容）
            }
            或 None（如果抓取失败）
        """
        list_data = self.fetch_announcement_list()
        if not list_data:
            return None

        results = {"game": list_data["game"], "activity": []}

        # 处理活动公告
        for item in list_data.get("activity", []):
            if not item.get("contentPrefix"):
                continue

            content_url = item["contentPrefix"][0] + "zh-Hans.json"
            content_data = self.fetch_announcement_content(content_url)

            if content_data:
                # 保存中文内容用于时间解析
                item["zh_content"] = content_data

                # 获取其他语言内容
                for lang in ["zh-Hant", "en", "ja"]:
                    lang_url = item["contentPrefix"][0] + f"{lang}.json"
                    lang_content = self.fetch_announcement_content(lang_url)
                    if lang_content:
                        item[f"{lang}_content"] = lang_content

                results["activity"].append(item)

        return results
