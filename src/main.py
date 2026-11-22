import os
import re
from pathlib import Path

from media_fetcher import fetch_media_assets
from release_store import download_release_assets, upload_release_asset
from story_engine import generate_episode, reset_series_for_next_book, save_memory
from telegram_notifier import send_text, send_thumbnail, send_tiktok_video
from thumb_gen import generate_thumbnail
from video_builder import build_full_book_video, build_videos
from voice_gen import generate_voice_and_subtitles
from youtube_uploader import upload_to_youtube

WORK_DIR = Path("build_output")
ASSETS_DIR = Path("assets_cache")
BOOK_CACHE_DIR = Path("book_archive")


def main() -> None:
    series_key = os.getenv("SERIES_TYPE", "trong_sinh").strip() or "trong_sinh"
    custom_topic = os.getenv("CUSTOM_TOPIC", "").strip()
    privacy_status = os.getenv("YOUTUBE_PRIVACY", "unlisted").strip() or "unlisted"

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Sinh kịch bản 3 nhịp + đọc/cập nhật trí nhớ dài hạn
    episode, updated_memory = generate_episode(series_key=series_key, custom_topic=custom_topic)
    ep_num = episode["episode_number"]
    book_num = episode["book_number"]
    book_title = episode["book_title"]
    is_finale = episode["is_finale"]
    title_yt = episode["title_youtube"]
    print(f"[Main] Đã tạo Bộ {book_num} - Tập {ep_num}: {title_yt}")

    # 2. Tạo giọng đọc tiếng Việt + phụ đề .srt
    audio_path = WORK_DIR / f"ep{ep_num:02d}_voice.mp3"
    srt_path = WORK_DIR / f"ep{ep_num:02d}_sub.srt"
    generate_voice_and_subtitles(episode["script_full"], audio_path, srt_path)

    # Lưu bản audio + srt tập này vào GitHub Release của bộ truyện để ghép Full Trọn Bộ
    book_tag = f"book-{series_key}-{book_num}"
    try:
        upload_release_asset(book_tag, audio_path)
        upload_release_asset(book_tag, srt_path)
    except Exception as exc:
        print(f"[Main] Cảnh báo chưa lưu được tập vào Release ({exc}).")

    # 3. Tải clip gameplay & nhạc nền từ GitHub Release 'assets'
    gameplay_videos, bgms = fetch_media_assets(ASSETS_DIR)

    # 4. Render 2 phiên bản video cho tập lẻ
    yt_video, tt_video = build_videos(audio_path, srt_path, gameplay_videos, bgms, WORK_DIR)

    # 5. Tạo ảnh bìa YouTube (1280x720)
    thumb_path = WORK_DIR / f"ep{ep_num:02d}_thumb.png"
    generate_thumbnail(
        badge=episode.get("thumb_badge", f"TẬP {ep_num}"),
        line1=episode.get("thumb_line1", "SỰ THẬT CHẤN ĐỘNG"),
        line2=episode.get("thumb_line2", "KHÔNG AI NGỜ TỚI"),
        out_path=thumb_path,
    )

    # 6. Upload tập lẻ 16:9 lên YouTube
    yt_channel_note = os.getenv("YOUTUBE_CHANNEL_URL", "https://youtube.com/@truonghoang-om2cf").strip()
    yt_desc = (
        f"{episode.get('youtube_description', '')}\n\n"
        f"Đăng ký kênh Audio Đi Ngủ để nghe tiếp tập mới mỗi ngày: {yt_channel_note}\n"
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

    # 7. Gửi tập lẻ về Telegram
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        summary_msg = (
            f"DA DUNG XONG BO {book_num} - TAP {ep_num}\n"
            f"Tieu de YT: {title_yt}\n"
            f"YouTube ({privacy_status}): {youtube_url or 'Chua upload'}\n\n"
            f"Caption TikTok (copy dang luon):\n"
            f"{episode.get('tiktok_caption', '')}\n"
            f"Nghe ban full tai YouTube: {youtube_url or yt_channel_note}\n"
            f"{episode.get('tiktok_hashtags', '')}"
        )
        send_text(summary_msg)
        send_thumbnail(thumb_path, caption=f"Anh bia Bo {book_num} - Tap {ep_num}")
        send_tiktok_video(tt_video, caption=f"Clip TikTok Hook Tap {ep_num} - luu ve may dang luon!")

    # 8. Nếu đây là TẬP CUỐI của bộ -> Tự động gộp & đăng bản FULL TRỌN BỘ
    if is_finale:
        print(f"[Main] Đã đủ {ep_num} tập -> bắt đầu gộp bản FULL TRỌN BỘ ({book_tag})...")
        archived_files = download_release_assets(book_tag, BOOK_CACHE_DIR, allowed_exts={".mp3", ".srt"})
        mp3_map = {}
        srt_map = {}
        for f in archived_files:
            m = re.match(r"ep(\d+)_(voice\.mp3|sub\.srt)$", f.name)
            if m:
                idx = int(m.group(1))
                if m.group(2) == "voice.mp3":
                    mp3_map[idx] = f
                else:
                    srt_map[idx] = f

        pairs = [(mp3_map[i], srt_map.get(i, BOOK_CACHE_DIR / f"missing_{i}.srt")) for i in sorted(mp3_map)]
        if len(pairs) >= 2:
            full_video = build_full_book_video(pairs, gameplay_videos, bgms, WORK_DIR)
            full_thumb = WORK_DIR / f"book{book_num}_full_thumb.png"
            generate_thumbnail(
                badge="TRỌN BỘ FULL",
                line1=book_title[:28],
                line2=f"TẬP 1 ĐẾN TẬP {ep_num} KHÔNG CẮT",
                out_path=full_thumb,
            )
            full_title = f"[TRỌN BỘ FULL] {book_title} (Tập 1 - Tập {ep_num}) | Audio Đi Ngủ"
            full_desc = (
                f"Tổng hợp trọn bộ {ep_num} tập {book_title} nghe liền mạch trước khi đi ngủ.\n\n"
                f"Đăng ký kênh để đón nghe bộ truyện mới mỗi ngày: {yt_channel_note}\n"
                f"#truyenaudio #audiodingu #tronbo #dramagiadinh #trongsinh"
            )
            full_yt_url = upload_to_youtube(
                video_path=full_video,
                thumbnail_path=full_thumb,
                title=full_title,
                description=full_desc,
                tags=["truyện audio", "trọn bộ full", "audio đi ngủ", "drama gia đình", "trọng sinh"],
                privacy_status=privacy_status,
            )
            if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
                send_text(
                    f"🔥 DA GOP & DANG XONG BAN FULL TRON BO (Bo {book_num}: Tap 1-{ep_num})\n"
                    f"🎬 YouTube ({privacy_status}): {full_yt_url or 'Chua upload'}\n"
                    f"👉 Bo truyen da tu dong reset sang Bo {book_num + 1} - Tap 1 cho lan chay toi!"
                )
                send_thumbnail(full_thumb, caption=f"Anh bia Full Tron Bo {book_num}")
        else:
            print(f"[Main] Chỉ tìm thấy {len(pairs)} tập trong Release -> bỏ qua gộp bản Full.")

        # Reset sang Bộ mới cho lần chạy sau
        updated_memory = reset_series_for_next_book(updated_memory, series_key)

    save_memory(updated_memory)
    print("[Main] Hoàn tất toàn bộ pipeline!")


if __name__ == "__main__":
    main()
