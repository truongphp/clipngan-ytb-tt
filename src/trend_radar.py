import random
import xml.etree.ElementTree as ET
import requests

TREND_RSS_URL = "https://trends.google.com/trending/rss?geo=VN"
YT_SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
YT_SEEDS = [
    "truyện audio ",
    "trọng sinh báo thù ",
    "drama gia đình ",
    "tiểu tam ",
    "chuyện đời thường ",
]


def fetch_google_trends_vn(limit: int = 8) -> list[str]:
    try:
        resp = requests.get(
            TREND_RSS_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        titles = []
        for item in root.findall(".//item/title"):
            text = (item.text or "").strip()
            if text and text not in titles:
                titles.append(text)
            if len(titles) >= limit:
                break
        return titles
    except Exception as exc:
        print(f"[TrendRadar] Cảnh báo lỗi đọc Google Trends RSS ({exc}).")
        return []


def fetch_youtube_suggestions_vn(limit: int = 6) -> list[str]:
    seed = random.choice(YT_SEEDS)
    try:
        resp = requests.get(
            YT_SUGGEST_URL,
            params={"client": "firefox", "ds": "yt", "hl": "vi", "gl": "VN", "q": seed},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        resp.raise_for_status()
        data = resp.json()
        suggestions = data[1] if isinstance(data, list) and len(data) > 1 else []
        cleaned = [str(s).strip() for s in suggestions if str(s).strip()]
        return cleaned[:limit]
    except Exception as exc:
        print(f"[TrendRadar] Cảnh báo lỗi đọc YouTube Suggest ({exc}).")
        return []


def get_trend_context() -> str:
    yt_hot = fetch_youtube_suggestions_vn(limit=4)
    gg_hot = fetch_google_trends_vn(limit=4)
    parts = []
    if yt_hot:
        parts.append("Từ khóa YouTube VN đang tìm nhiều: " + ", ".join(yt_hot))
    if gg_hot:
        parts.append("Chủ đề nóng 24h tại VN: " + ", ".join(gg_hot))
    if not parts:
        return ""
    return (
        "Tham khảo khéo léo xu hướng đang hot để đặt tình huống đời thực và tiêu đề bắt mắt "
        "(KHÔNG nhắc tên người thật/chính trị/tin nhạy cảm): " + " | ".join(parts)
    )
