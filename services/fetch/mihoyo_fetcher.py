# mihoyo_fetcher.py
import requests
from typing import Dict, Optional, Tuple, List


class MihoyoFetcher:
    """米哈游系游戏公告抓取器（原神、星穹铁道、绝区零）"""

    def __init__(self, debug=False):
        self.session = requests.Session()
        self.debug = debug  # 调试模式开关
        self._setup_session()

        # 游戏API配置
        self.game_config = {
            "genshin": {
                "list_url": "https://hk4e-ann-api.mihoyo.com/common/hk4e_cn/announcement/api/getAnnList",
                "content_url": "https://hk4e-ann-api.mihoyo.com/common/hk4e_cn/announcement/api/getAnnContent",
                "base_params": {
                    "game": "hk4e",
                    "game_biz": "hk4e_cn",
                    "bundle_id": "hk4e_cn",
                    "level": "1",
                    "platform": "pc",
                    "region": "cn_gf01",
                    "uid": "1",
                },
            },
            "starrail": {
                "list_url": "https://hkrpg-ann-api.mihoyo.com/common/hkrpg_cn/announcement/api/getAnnList",
                "content_url": "https://hkrpg-ann-api.mihoyo.com/common/hkrpg_cn/announcement/api/getAnnContent",
                "base_params": {
                    "game": "hkrpg",
                    "game_biz": "hkrpg_cn",
                    "bundle_id": "hkrpg_cn",
                    "level": "1",
                    "platform": "pc",
                    "region": "prod_gf_cn",
                    "uid": "1",
                },
            },
            "zenless": {
                "list_url": "https://announcement-api.mihoyo.com/common/nap_cn/announcement/api/getAnnList",
                "content_url": "https://announcement-api.mihoyo.com/common/nap_cn/announcement/api/getAnnContent",
                "base_params": {
                    "game": "nap",
                    "game_biz": "nap_cn",
                    "bundle_id": "nap_cn",
                    "level": "1",
                    "platform": "pc",
                    "region": "prod_gf_cn",
                    "uid": "1",
                },
            },
        }
        if self.debug:
            print("[DEBUG] MihoyoFetcher 初始化完成，已配置以下游戏:")
            for game in self.game_config:
                print(f"  - {game}: {self.game_config[game]['list_url']}")

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

        if self.debug:
            print("[DEBUG] 会话配置完成，headers:")
            for k, v in headers.items():
                print(f"  {k}: {v}")

    def _fetch_announcement_data(
        self, game: str, lang: str
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """获取指定语言的公告数据"""
        if game not in self.game_config:
            if self.debug:
                print(f"[DEBUG] 无效的游戏标识: {game}")
            return None, None

        config = self.game_config[game]
        params = {**config["base_params"], "lang": lang}

        if self.debug:
            print(f"[DEBUG] 开始获取 {game} {lang} 公告数据")
            print(f"[DEBUG] 请求参数: {params}")

        try:
            # 获取列表数据
            if self.debug:
                print(
                    f"[DEBUG] 正在请求列表数据: {config['list_url']}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
                )
            list_resp = self.session.get(config["list_url"], params=params)
            list_resp.raise_for_status()
            list_data = list_resp.json()

            if self.debug:
                print(f"[DEBUG] 列表数据获取成功，状态码: {list_resp.status_code}")
                print(f"[DEBUG] 返回的公告数量: {len(list_data['data']['list'])}")

            # 获取内容数据
            if self.debug:
                print(
                    f"[DEBUG] 正在请求内容数据: {config['content_url']}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
                )
            content_resp = self.session.get(config["content_url"], params=params)
            content_resp.raise_for_status()
            content_data = content_resp.json()

            if self.debug:
                print(f"[DEBUG] 内容数据获取成功，状态码: {content_resp.status_code}")
                print(f"[DEBUG] 返回的内容数量: {len(content_data['data']['list'])}")

            # 构建内容映射
            content_map = {
                item["ann_id"]: item for item in content_data["data"]["list"]
            }
            pic_content_map = {
                item["ann_id"]: item for item in content_data["data"]["pic_list"]
            }

            if self.debug:
                print(f"[DEBUG] 构建完成的内容映射: {len(content_map)} 条")
                print(f"[DEBUG] 构建完成的图片内容映射: {len(pic_content_map)} 条")

            return list_data, {
                "content_map": content_map,
                "pic_content_map": pic_content_map,
            }
        except requests.exceptions.RequestException as e:
            if self.debug:
                print(f"[DEBUG] 请求失败: {type(e).__name__}: {e}")
            return None, None
        except Exception as e:
            if self.debug:
                print(f"[DEBUG] 处理数据时发生错误: {type(e).__name__}: {e}")
            return None, None

    def fetch_game_announcements(self, game: str, lang: str) -> Optional[Dict]:
        """
        抓取米哈游游戏的公告数据

        参数:
            game: 游戏标识 (genshin: 原神, starrail: 星穹铁道, zenless: 绝区零)
            lang: 语言代码 (如zh-cn, zh-tw)

        返回:
            {
                "list": 指定语言的公告列表数据,
                "content_map": 指定语言的内容映射,
                "pic_content_map": 指定语言的图片内容映射,
                "zh_list": 中文列表数据,
                "zh_content_map": 中文内容映射,
                "zh_pic_content_map": 中文图片内容映射,
                "lang": 请求的语言代码
            }
            或 None (如果获取失败)
        """
        lang_mapper = {"zh-Hans": "zh-cn", "zh-Hant": "zh-tw"}
        lang = lang_mapper.get(lang, lang)
        if self.debug:
            print(f"[DEBUG] 开始抓取 {game} 游戏的 {lang} 公告数据")

        # 1. 获取请求语言的列表和内容数据
        if self.debug:
            print(f"[DEBUG] 第一步: 获取 {lang} 语言的数据")
        lang_list_data, lang_content_data = self._fetch_announcement_data(game, lang)
        if not lang_list_data or not lang_content_data:
            if self.debug:
                print(f"[DEBUG] 获取 {lang} 语言数据失败，终止处理")
            return None

        # 2. 获取中文数据
        if lang == "zh-cn":
            if self.debug:
                print("[DEBUG] 请求语言为中文，无需额外获取中文数据")
            zh_list_data = lang_list_data
            zh_content_map = lang_content_data["content_map"]
            zh_pic_content_map = lang_content_data["pic_content_map"]
        else:
            if self.debug:
                print("[DEBUG] 第二步: 获取中文数据")
            zh_list_data, zh_content_data = self._fetch_announcement_data(game, "zh-cn")
            if not zh_content_data:
                if self.debug:
                    print("[DEBUG] 获取中文内容失败，但仍返回已获取的数据")
                zh_content_map = {}
                zh_pic_content_map = {}
            else:
                zh_content_map = zh_content_data["content_map"]
                zh_pic_content_map = zh_content_data["pic_content_map"]

            if not zh_list_data:
                if self.debug:
                    print("[DEBUG] 获取中文列表失败，但仍返回已获取的数据")
                zh_list_data = None

        result = {
            "list": lang_list_data,
            "content_map": lang_content_data["content_map"],
            "pic_content_map": lang_content_data["pic_content_map"],
            "zh_list": zh_list_data,
            "zh_content_map": zh_content_map,
            "zh_pic_content_map": zh_pic_content_map,
            "lang": lang,
        }

        if self.debug:
            print(f"[DEBUG] 数据抓取完成，返回结果包含:")
            print(f"  - {lang}列表数据: {len(lang_list_data['data']['list'])} 条")
            print(f"  - {lang}内容映射: {len(lang_content_data['content_map'])} 条")
            print(
                f"  - {lang}图片内容映射: {len(lang_content_data['pic_content_map'])} 条"
            )
            if zh_list_data:
                print(f"  - 中文列表数据: {len(zh_list_data['data']['list'])} 条")
            else:
                print("  - 中文列表数据: 无")
            print(f"  - 中文内容映射: {len(zh_content_map)} 条")
            print(f"  - 中文图片内容映射: {len(zh_pic_content_map)} 条")

        return result

    def fetch_all_mihoyo_games(self, lang: str = "en") -> Dict[str, Optional[Dict]]:
        """抓取所有米哈游游戏的公告数据"""
        if self.debug:
            print(f"[DEBUG] 开始抓取所有米哈游游戏公告，语言: {lang}")

        results = {}
        for game in self.game_config.keys():
            if self.debug:
                print(f"[DEBUG] 正在处理游戏: {game}")
            results[game] = self.fetch_game_announcements(game, lang)

        if self.debug:
            print("[DEBUG] 所有游戏处理完成")
            for game, data in results.items():
                if data:
                    print(f"  {game}: 成功获取 {len(data['content_map'])} 条公告")
                else:
                    print(f"  {game}: 获取失败")

        return results


# 使用示例
if __name__ == "__main__":
    fetcher = MihoyoFetcher(debug=True)

    # 抓取所有米哈游游戏(繁体中文)
    all_data = fetcher.fetch_all_mihoyo_games("en")
    with open("mihoyo_all_data.json", "w", encoding="utf-8") as f:
        import json

        json.dump(all_data, f, ensure_ascii=False, indent=2)
    # print(all_data)
    for game, data in all_data.items():
        if data:
            print(f"{game} 公告数量: {len(data['content_map'])}")
