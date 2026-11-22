# ClipNgan — Hệ thống dựng Audio Drama 0đ (YouTube + TikTok)

Pipeline tự động hóa hoàn toàn trên cloud (chạy 100% từ điện thoại, không cần PC):
- **Gemini API Free Tier** viết kịch bản 3 nhịp (15s hook chấn động -> lật kèo giữa tập -> cliffhanger) và lưu trí nhớ cốt truyện dài hạn vào `data/story_memory.json`.
- **edge-tts** tạo giọng đọc tiếng Việt (`vi-VN-HoaiMyNeural` / `vi-VN-NamMinhNeural`) kèm phụ đề `.srt` khớp từng cụm từ.
- **FFmpeg** trên **GitHub Actions** tự động ghép clip gameplay nền + nhạc nền, xuất 2 bản:
  - **YouTube (`16:9` ngang, bản full 7–10 phút)** + ảnh bìa **Satori** (`1280x720`) -> tự upload qua **YouTube Data API v3**.
  - **TikTok (`9:16` dọc, cắt Hook 75 giây < 50MB)** -> gửi thẳng về **Telegram** kèm caption & hashtag.

## Bước 1: Đẩy code lên repo `truongphp/clipngan-ytb-tt`
1. Mở repo `https://github.com/truongphp/clipngan-ytb-tt` (nên để chế độ **Private**).
2. Giải nén tệp `clipngan-ytb-tt.zip` trên iPhone (ứng dụng **Tệp / Files**), rồi tải lên qua **GitHub Codespaces** (hoặc upload trực tiếp các thư mục lên repo).

## Bước 2: Nạp GitHub Secrets
Vào repo -> **Settings -> Secrets and variables -> Actions -> New repository secret** và thêm đủ 8 biến sau:

| Tên Secret | Giá trị cần điền |
| :--- | :--- |
| `GEMINI_API_KEY` | API key từ Google AI Studio |
| `GROQ_API_KEY` | API key từ Groq Console *(tùy chọn)* |
| `TELEGRAM_BOT_TOKEN` | Token bot từ `@BotFather` |
| `TELEGRAM_CHAT_ID` | `6018196217` |
| `YOUTUBE_CLIENT_ID` | Client ID mới (`891014573162-jll20...`) |
| `YOUTUBE_CLIENT_SECRET` | Client Secret mới (`GOCSPX-3oQBZ...`) |
| `YOUTUBE_REFRESH_TOKEN` | Refresh token vĩnh viễn (`1//04HU2bYX...`) |
| `GDRIVE_FOLDER_URL` | Link thư mục Google Drive chứa clip gameplay & nhạc nền |

*(Nhớ mở bot Telegram của bạn và bấm **Start** ít nhất 1 lần để bot gửi tin được.)*

## Bước 3: Chạy thử ngay trên iPhone
1. Vào tab **Actions** trong repo -> chọn **Daily Audio Drama Pipeline**.
2. Bấm **Run workflow** -> chọn `trong_sinh` hoặc `doi_thuong` -> chọn `unlisted` (để xem trước trên YouTube) -> bấm **Run workflow**.
3. Sau khoảng 3–5 phút, kiểm tra Telegram để nhận **clip dọc TikTok**, **ảnh bìa**, **caption** và **link YouTube**.

## Bước 4 (Tùy chọn): Gắn Cloudflare Worker để điều khiển bằng lệnh `/tao`
1. Dán file `worker/telegram_worker.js` lên một Cloudflare Worker miễn phí.
2. Thêm các biến `TELEGRAM_BOT_TOKEN`, `ALLOWED_CHAT_ID`, `GITHUB_TOKEN`, `GITHUB_REPO` (`truongphp/clipngan-ytb-tt`).
3. Đăng ký Webhook Telegram: mở link sau trên Safari:
   `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<ten-worker>.workers.dev`
