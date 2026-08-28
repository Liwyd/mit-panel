from datetime import datetime
import requests

ads_cache = None
ads_cache_time = None


def get_ads_from_github() -> dict:
    global ads_cache, ads_cache_time

    if (
        ads_cache
        and ads_cache_time
        and (datetime.now().timestamp() - ads_cache_time) < 3600
    ):
        return ads_cache

    try:
        url = "https://raw.githubusercontent.com/primeZdev/whale-panel/main/media/ads.json"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        ads_data = response.json()
        ads_cache = ads_data
        ads_cache_time = datetime.now().timestamp()
        return ads_cache

    except (requests.RequestException, ValueError):
        default_ads = {
            "title": "جایگاه آگهی شما",
            "text": "کسب‌وکار خود را به بقیه افراد معرفی کنید! اینجا می‌توانید تبلیغ ویژه خود را قرار دهید",
            "link": "https://t.me/primezdev",
            "button": "رزرو جایگاه آگهی",
        }
        ads_cache = default_ads
        ads_cache_time = datetime.now().timestamp()
        return default_ads
