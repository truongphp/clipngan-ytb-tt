import os
import re
from pathlib import Path
import requests

from media_fetcher import fetch_media_assets
from release_store import download_release_assets, upload_release_asset
from story_engine import generate_episode, reset_series_for_next_book, save_memory
from telegram_notifier import send_text, send_thumbnail, send_tiktok_video
from thumb_gen import generate_thumbnail
from trend_radar import get_trend_context
from video_builder import build_videos, merge_full_book_stream_copy
from voice_gen import generate_multivoice_and_ass
from youtube_uploader import upload_to_youtube

WORK_DIR = Path("build_output")
ASSETS_DIR = Path("assets_cache")
BOOK_CACHE_DIR = Path("book_archive")


def _sync_worker_d1(payload: dict) -> None:
    worker_url = os.getenv("WORKER_SYNC_URL", "").strip()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not worker_url or not bot_token:
        return
    try:
        resp = requests.post(
            f"{worker_url.rstrip('/')}/api/sync-series",
            headers={"X-Sync-Secret": bot_token},
            json=payload,
            timeout=20,
        )
        print(f"[Main] Đồng bộ D1 Worker: HTTP {resp.status_code}")
    except Exception as exc:
        print(f"[Main] Cảnh báo đồng bộ D1 lỗi ({exc}).")


def main() -> None:
    series_key = os.getenv("SERIES_TYPE", "trong_sinh").strip() or "trong_sinh"
    series_name = os.getenv("SERIES_NAME", "").strip()
    custom_topic = os.getenv("CUSTOM_TOPIC", "").strip()
    start_new_book = os.getenv("START_NEW_BOOK", "false").lower() == "true"
    privacy_status = os.getenv("YOUTUBE_PRIVACY", "public").strip() or "public"

    yt_channel = os.getenv("YOUTUBE_CHANNEL_URL", "https://youtube.com/@truonghoang-om2cf").strip()
    tt_channel = os.getenv("TIKTOK_CHANNEL_URL", "https://www.tiktok.com/@scvpro11").strip()

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # 0. Nếu không nhập chủ đề tay, tự quét Radar Trend VN làm chất liệu bắt trend
    if not custom_topic:
        trend_hint = get_trend_context()
        if trend_hint:
            custom_topic = trend_hint
            print(f"[Main] Đã nạp Radar Trend: {trend_hint[:120]}...")

    # 1. Sinh kịch bản đa vai Nam-Nữ + phao dự phòng Groq
    episode, updated_memory = generate_episode(
        series_key=series_key,
        custom_topic=custom_topic,
        series_name=series_name,
        start_new_book=start_new_book,
    )
    ep_num = episode["episode_number"]
    book_num = episode["book_number"]
    book_title = episode["book_title"]
    is_finale = episode["is_finale"]
    title_yt = episode["title_youtube"]
    print(f"[Main] Bộ {book_num} ({series_key}) - Tập {ep_num}: {title_yt}")

    # 2. Tạo giọng đọc đa vai song song (-14 LUFS) + phụ đề Karaoke .ass
    audio_path = WORK_DIR / f"ep{ep_num:02d}_voice.mp3"
    ass_yt = WORK_DIR / f"ep{ep_num:02d}_yt.ass"
    ass_tt = WORK_DIR / f"ep{ep_num:02d}_tt.ass"
    _, _, _, peak_sec = generate_multivoice_and_ass(
        episode["segments"],
        audio_path,
        ass_yt,
        ass_tt,
        peak_segment_index=int(episode.get("peak_segment_index", 0)),
    )

    # 3. Tải clip gameplay & nhạc nền từ GitHub Release 'assets'
    gameplay_videos, bgms = fetch_media_assets(ASSETS_DIR)

    # 4. Render 2 phiên bản video Studio HUD (YouTube 16:9 + TikTok 9:16 Đỉnh Cao Trào)
    yt_video, tt_video = build_videos(audio_path, ass_yt, ass_tt, gameplay_videos, bgms, WORK_DIR, peak_sec)

    # Lưu bản video tập lẻ (đã chuẩn hóa codec) vào Release để cuối bộ gộp -c copy trong 5 giây
    book_tag = f"book-{series_key}-{book_num}"
    ep_archive_mp4 = WORK_DIR / f"ep{ep_num:02d}_yt.mp4"
    ep_archive_mp4.write_bytes(yt_video.read_bytes())
    try:
        upload_release_asset(book_tag, ep_archive_mp4)
    except Exception as exc:
        print(f"[Main] Cảnh báo lưu tập vào Release lỗi ({exc}).")

    # 5. Tạo ảnh bìa YouTube bằng Satori
    thumb_path = WORK_DIR / f"ep{ep_num:02d}_thumb.png"
    generate_thumbnail(
        badge=episode.get("thumb_badge", f"TẬP {ep_num}"),
        line1=episode.get("thumb_line1", "SỰ THẬT CHẤN ĐỘNG"),
        line2=episode.get("thumb_line2", "KHÔNG AI NGỜ TỚI"),
        out_path=thumb_path,
    )

    # 6. Upload tập lẻ lên YouTube (công khai + gắn chéo link TikTok)
    yt_desc = (
        f"{episode.get('youtube_description', '')}\n\n"
        f"🎧 Đăng ký kênh Audio Đi Ngủ: {yt_channel}\n"
        f"🎵 Xem trích đoạn ngắn trên TikTok: {tt_channel}\n"
        f"{episode.get('tiktok_hashtags', '')}"
    )
    youtube_url = upload_to_youtube(
        video_path=yt_video,
        thumbnail_path=thumb_path,
        title=title_yt,
        description=yt_desc,
        tags=episode.get("youtube_tags", []),
        privacy_status=privacy_status,
    )

    # 7. Gửi báo cáo + ảnh bìa + clip TikTok về Telegram
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        send_text(
            f"✅ ĐÃ LÊN SÓNG {book_title} — TẬP {ep_num}\n"
            f"📌 Tiêu đề YT: {title_yt}\n"
            f"🎬 YouTube ({privacy_status}): {youtube_url or 'Chưa upload'}\n\n"
            f"📝 Caption TikTok (copy đăng luôn):\n"
            f"{episode.get('tiktok_caption', '')}\n"
            f"Nghe bản full tại YouTube: {youtube_url or yt_channel}\n"
            f"{episode.get('tiktok_hashtags', '')}"
        )
        send_thumbnail(thumb_path, caption=f"Ảnh bìa {book_title} - Tập {ep_num}")
        send_tiktok_video(tt_video, caption=f"Clip TikTok Đỉnh Cao Trào Tập {ep_num}")

    # 8. Nếu là TẬP CUỐI -> Gộp Full Trọn Bộ trong 5 giây bằng -c copy + YouTube Chapters
    full_yt_url = ""
    if is_finale:
        print(f"[Main] Đủ {ep_num} tập -> gộp bản FULL TRỌN BỘ bằng Stream Copy...")
        archived = download_release_assets(book_tag, BOOK_CACHE_DIR, allowed_exts={".mp4"})
        ep_map = {}
        for f in archived:
            m = re.match(r"ep(\d+)_yt\.mp4$", f.name)
            if m:
                ep_map[int(m.group(1))] = f
        ep_list = [(k, ep_map[k]) for k in sorted(ep_map)]

        if len(ep_list) >= 2:
            full_video, chapters_txt = merge_full_book_stream_copy(ep_list, WORK_DIR)
            full_thumb = WORK_DIR / f"book{book_num}_full_thumb.png"
            generate_thumbnail(
                badge="TRỌN BỘ FULL",
                line1=book_title[:28],
                line2=f"TẬP {ep_list[0][0]} ĐẾN TẬP {ep_list[-1][0]}",
                out_path=full_thumb,
            )
            full_title = f"[TRỌN BỘ FULL] {book_title} (Tập {ep_list[0][0]} - Tập {ep_list[-1][0]}) | Audio Đi Ngủ"
            full_desc = (
                f"Tổng hợp trọn bộ {book_title} nghe liền mạch trước khi đi ngủ.\n\n"
                f"⏱️ MỤC LỤC CHƯƠNG:\n{chapters_txt}\n\n"
                f"🎧 Kênh YouTube: {yt_channel}\n"
                f"🎵 Kênh TikTok: {tt_channel}\n"
                f"#truyenaudio #audiodingu #tronbo #dramagiadinh"
            )
            full_yt_url = upload_to_youtube(
                video_path=full_video,
                thumbnail_path=full_thumb,
                title=full_title,
                description=full_desc,
                tags=["truyện audio", "trọn bộ full", "audio đi ngủ", "drama gia đình"],
                privacy_status=privacy_status,
            ) or ""
            if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
                send_text(
                    f"🔥 ĐÃ GỘP & LÊN SÓNG FULL TRỌN BỘ: {book_title}\n"
                    f"🎬 YouTube ({privacy_status}): {full_yt_url}\n"
                    f"📚 Bộ truyện đã tự động chuyển vào mục Lịch Sử Full Bộ trên Telegram!"
                )
                send_thumbnail(full_thumb, caption=f"Ảnh bìa Full Trọn Bộ: {book_title}")

        # Đồng bộ sang D1: đánh dấu hoàn thành & chuyển vào Lịch Sử Full Bộ
        _sync_worker_d1(
            {
                "slug": series_key,
                "name": book_title,
                "book_number": book_num,
                "current_episode": ep_num,
                "status": "completed",
                "full_youtube_url": full_yt_url or youtube_url or yt_channel,
            }
        )
        updated_memory = reset_series_for_next_book(updated_memory, series_key)
    else:
        _sync_worker_d1(
            {
                "slug": series_key,
                "name": book_title,
                "book_number": book_num,
                "current_episode": ep_num,
                "status": "active",
                "full_youtube_url": "",
            }
        )

    save_memory(updated_memory)
    print("[Main] Hoàn tất chu trình v3 Studio Pro + Trend Radar!")


if __name__ == "__main__":
    main()
