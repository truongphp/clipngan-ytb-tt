import os
from pathlib import Path
import gdown
from release_store import download_release_assets

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}


def fetch_media_assets(assets_dir: Path) -> tuple[list[Path], list[Path]]:
    """Ưu tiên tải clip gameplay & nhạc nền từ GitHub Release 'assets', fallback sang Google Drive."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    release_tag = os.getenv("ASSETS_RELEASE_TAG", "assets").strip() or "assets"

    print(f"[MediaFetcher] Đang kiểm tra GitHub Release '{release_tag}'...")
    try:
        download_release_assets(release_tag, assets_dir, allowed_exts=VIDEO_EXTS | AUDIO_EXTS)
    except Exception as exc:
        print(f"[MediaFetcher] Cảnh báo lỗi tải Release ({exc}).")

    videos = sorted(p for p in assets_dir.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
    bgms = sorted(p for p in assets_dir.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTS)

    if not videos:
        folder_url = os.getenv("GDRIVE_FOLDER_URL", "").strip()
        if folder_url:
            print("[MediaFetcher] Release chưa có clip -> thử tải dự phòng từ Google Drive...")
            try:
                gdown.download_folder(
                    url=folder_url,
                    output=str(assets_dir),
                    quiet=False,
                    use_cookies=False,
                    remaining_ok=True,
                )
                videos = sorted(p for p in assets_dir.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
                bgms = sorted(p for p in assets_dir.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTS)
            except Exception as exc:
                print(f"[MediaFetcher] Tải Drive lỗi ({exc}).")

    print(f"[MediaFetcher] Tìm thấy {len(videos)} clip nền và {len(bgms)} file nhạc nền.")
    return videos, bgms
