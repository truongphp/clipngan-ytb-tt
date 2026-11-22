import os
from pathlib import Path
import requests


def _api_url(method: str) -> str:
    token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
    return f"https://api.telegram.org/bot{token}/{method}"


def send_text(text: str) -> None:
    chat_id = os.environ["TELEGRAM_CHAT_ID"].strip()
    resp = requests.post(
        _api_url("sendMessage"),
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": False},
        timeout=30,
    )
    resp.raise_for_status()


def send_tiktok_video(video_path: Path, caption: str) -> None:
    chat_id = os.environ["TELEGRAM_CHAT_ID"].strip()
    size_mb = video_path.stat().st_size / (1024 * 1024)
    print(f"[Telegram] Đang gửi clip TikTok ({size_mb:.1f}MB)...")

    with open(video_path, "rb") as f:
        resp = requests.post(
            _api_url("sendVideo"),
            data={
                "chat_id": chat_id,
                "caption": caption[:1024],
                "supports_streaming": True,
            },
            files={"video": (video_path.name, f, "video/mp4")},
            timeout=180,
        )
    resp.raise_for_status()
    print("[Telegram] Đã gửi clip TikTok thành công.")


def send_thumbnail(thumb_path: Path, caption: str = "") -> None:
    if not thumb_path.exists():
        return
    chat_id = os.environ["TELEGRAM_CHAT_ID"].strip()
    with open(thumb_path, "rb") as f:
        resp = requests.post(
            _api_url("sendPhoto"),
            data={"chat_id": chat_id, "caption": caption[:1024]},
            files={"photo": (thumb_path.name, f, "image/png")},
            timeout=60,
        )
    resp.raise_for_status()
