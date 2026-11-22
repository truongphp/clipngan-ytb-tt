import os
from pathlib import Path
from media_fetcher import fetch_media_assets
from story_engine import generate_episode, save_memory
from telegram_notifier import send_text, send_thumbnail, send_tiktok_video
from thumb_gen import generate_thumbnail
from video_builder import build_videos
from voice_gen import generate_voice_and_subtitles
from youtube_uploader import upload_to_youtube
WORK_DIR = Path("build_output")
ASSETS_DIR = Path("assets_cache")
def main() -> None:
series_key = os.getenv("SERIES_TYPE", "trong_sinh").strip() or "trong_sinh"
custom_topic = os.getenv("CUSTOM_TOPIC", "").strip()
privacy_status = os.getenv("YOUTUBE_PRIVACY", "unlisted").strip() or "unlisted"
WORK_DIR.mkdir(parents=True, exist_ok=True)
# 1. Sinh kịch bản 3 nhịp + đọc/cập nhật trí nhớ dài hạn
episode, updated_memory = generate_episode(series_key=series_key, custom_topic=custom_topic)
ep_num = episode["episode_number"]
title_yt = episode["title_youtube"]
print(f"[Main] Đã tạo kịch bản Tập {ep_num}: {title_yt}")
# 2. Tạo giọng đọc tiếng Việt + phụ đề .srt khớp từng cụm từ
audio_path = WORK_DIR / f"ep{ep_num}_voice.mp3"
srt_path = WORK_DIR / f"ep{ep_num}_sub.srt"
generate_voice_and_subtitles(episode["script_full"], audio_path, srt_path)
# 3. Tải nguyên liệu gameplay & nhạc nền từ Google Drive (nếu có)
gameplay_videos, bgms = fetch_media_assets(ASSETS_DIR)
# 4. Render 2 phiên bản video: YouTube 16:9 full + TikTok 9:16 hook
yt_video, tt_video = build_videos(audio_path, srt_path, gameplay_videos, bgms, WORK_DIR)
# 5. Tạo ảnh bìa YouTube (1280x720) bằng Satori (hoặc Pillow fallback)
thumb_path = WORK_DIR / f"ep{ep_num}_thumb.png"
generate_thumbnail(
badge=episode.get("thumb_badge", f"PHẦN {ep_num}"),
line1=episode.get("thumb_line1", "SỰ THẬT CHẤN ĐỘNG"),
line2=episode.get("thumb_line2", "KHÔNG AI NGỜ TỚI"),
out_path=thumb_path,
)
# 6. Upload bản full 16:9 lên YouTube
yt_channel_note = os.getenv("YOUTUBE_CHANNEL_URL", "https://youtube.com/@truonghoang-om2cf").strip()
yt_desc = (
f"{episode.get('youtube_description', '')}\n\n"
f"Đăng ký kênh để nghe tiếp tập mới mỗi ngày: {yt_channel_note}\n"
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
# 7. Lưu lại trí nhớ cốt truyện sau khi render & upload xong
save_memory(updated_memory)
# 8. Gửi clip dọc TikTok + caption + link YouTube về Telegram
if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
summary_msg = (
f"✅ ĐÃ DỰNG XONG TẬP {ep_num}\n"
f"📌 Tiêu đề YT: {title_yt}\n"
f"🎬 YouTube ({privacy_status}): {youtube_url or 'Chưa upload'}\n\n"
f"📝 Caption TikTok (copy đăng luôn):\n"
f"{episode.get('tiktok_caption', '')}\n"
f"Nghe bản full tại YouTube: {youtube_url or yt_channel_note}\n"
f"{episode.get('tiktok_hashtags', '')}"
)
send_text(summary_msg)
send_thumbnail(thumb_path, caption=f"Ảnh bìa Tập {ep_num}")
send_tiktok_video(
tt_video,
caption=f"Clip TikTok Hook Tập {ep_num} — lưu về máy đăng luôn!",
)
else:
print("[Main] Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID -> bỏ qua gửi Telegram.")
print("[Main] Hoàn tất toàn bộ pipeline!")
if name == "main":
main()
