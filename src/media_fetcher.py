import os
from pathlib import Path
import gdown

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}


def fetch_media_assets(assets_dir: Path) -> tuple[list[Path], list[Path]]:
    """Tải clip gameplay nền và nhạc nền từ link thư mục Google Drive công khai."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    folder_url = os.getenv("GDRIVE_FOLDER_URL", "").strip()

    if folder_url:
        print(f"[MediaFetcher] Đang tải nguyên liệu từ Google Drive...")
        try:
            gdown.download_folder(
                url=folder_url,
                output=str(assets_dir),
                quiet=False,
                use_cookies=False,
                remaining_ok=True,
            )
        except Exception as exc:
            print(f"[MediaFetcher] Cảnh báo tải Drive lỗi ({exc}), sẽ kiểm tra file sẵn có.")
    else:
        print("[MediaFetcher] Chưa cấu hình GDRIVE_FOLDER_URL -> dùng nền tối giản tự tạo.")

    videos = sorted(
        p for p in assets_dir.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )
    bgms = sorted(
        p for p in assets_dir.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    )
    print(f"[MediaFetcher] Tìm thấy {len(videos)} clip nền và {len(bgms)} file nhạc nền.")
    return videos, bgms
