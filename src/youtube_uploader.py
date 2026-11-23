import os
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_youtube_service():
    client_id = os.getenv("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip()

    if not all([client_id, client_secret, refresh_token]):
        return None

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload_to_youtube(
    video_path: Path,
    thumbnail_path: Path | None,
    title: str,
    description: str,
    tags: list[str],
    privacy_status: str = "public",
) -> str | None:
    youtube = _get_youtube_service()
    if youtube is None:
        print("[YouTube] Thiếu YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN -> bỏ qua upload YouTube.")
        return None

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags[:15],
            "categoryId": "24",  # Entertainment
            "defaultLanguage": "vi",
            "defaultAudioLanguage": "vi",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"[YouTube] Đang upload '{title}' ({privacy_status})...")
    try:
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"[YouTube] Tiến độ upload: {int(status.progress() * 100)}%")
    except HttpError as exc:
        if "uploadLimitExceeded" in str(exc):
            print("[YouTube] Kênh đã chạm giới hạn đăng video trong 24h (uploadLimitExceeded). Vẫn tiếp tục gửi clip về Telegram.")
            return None
        print(f"[YouTube] Lỗi upload YouTube: {exc}")
        return None
    except Exception as exc:
        print(f"[YouTube] Lỗi upload YouTube: {exc}")
        return None

    video_id = response["id"]
    video_url = f"https://youtu.be/{video_id}"
    print(f"[YouTube] Upload thành công: {video_url}")

    if thumbnail_path and thumbnail_path.exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/png"),
            ).execute()
            print("[YouTube] Đã gắn thumbnail thành công.")
        except Exception as exc:
            print(
                f"[YouTube] Không gắn được custom thumbnail (cần xác minh SĐT kênh YouTube): {exc}"
            )

    return video_url
