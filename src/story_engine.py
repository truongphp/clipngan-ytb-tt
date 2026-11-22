import json
import os
import re
from pathlib import Path
from google import genai
from google.genai import types

MEMORY_PATH = Path("data/story_memory.json")


def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return {
            "active_series": "trong_sinh",
            "series": {
                "trong_sinh": {
                    "name": "Trọng Sinh Báo Thù & Tiểu Tam",
                    "current_episode": 0,
                    "characters": [],
                    "plot_summary": "",
                    "last_cliffhanger": "",
                    "history": [],
                },
                "doi_thuong": {
                    "name": "Chuyện Đời Thường Ngỡ Ngàng",
                    "current_episode": 0,
                    "characters": [],
                    "plot_summary": "",
                    "last_cliffhanger": "",
                    "history": [],
                },
            },
        }
    return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))


def save_memory(memory: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(
        json.dumps(memory, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _extract_json(raw_text: str) -> dict:
    text = raw_text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def _build_prompt(series_key: str, series_state: dict, custom_topic: str = "") -> str:
    next_ep = series_state["current_episode"] + 1
    is_continuing = next_ep > 1 and bool(series_state.get("plot_summary"))

    genre_guide = (
        "Thể loại: Drama gia đình, trọng sinh, tiểu tam, báo thù, ngôn tình hiện đại Việt Nam."
        if series_key == "trong_sinh"
        else "Thể loại: Những câu chuyện đời thường rất thật ở Việt Nam (bữa cơm gia đình, chia tài sản, tin nhắn gửi nhầm, người thân vay tiền...) nhưng có cú lật kèo khiến người nghe rùng mình không ngờ tới."
    )

    continuity_block = ""
    if is_continuing:
        continuity_block = f"""
BỐI CẢNH CÁC TẬP TRƯỚC (BẮT BUỘC NỐI TIẾP LIỀN MẠCH):
- Đây là Tập {next_ep}.
- Nhân vật hiện có: {json.dumps(series_state.get("characters", []), ensure_ascii=False)}
- Tóm tắt diễn biến đến hết Tập {next_ep - 1}: {series_state.get("plot_summary", "")}
- Nút thắt cuối tập trước cần giải quyết ngay đầu tập này: {series_state.get("last_cliffhanger", "")}
"""
    else:
        continuity_block = f"- Đây là Tập {next_ep} (mở màn một câu chuyện hoàn toàn mới, đặt tên nhân vật Việt Nam tự nhiên, gần gũi)."

    topic_block = f"\n- Gợi ý chủ đề riêng từ người dùng: {custom_topic}" if custom_topic else ""

    return f"""Bạn là biên kịch audio drama tiếng Việt chuyên viết truyện giữ chân người nghe YouTube & TikTok.
{genre_guide}
{continuity_block}{topic_block}

YÊU CẦU CẤU TRÚC KỊCH BẢN (BẮT BUỘC):
1. Kể ở ngôi thứ nhất ("tôi"), giọng kể đời thường, sắc bén, giàu cảm xúc, câu ngắn dễ đọc thành tiếng.
2. Độ dài phần "script_full": khoảng 1.300 đến 1.550 từ tiếng Việt (tương đương 7–10 phút đọc audio).
3. Công thức 3 nhịp giữ chân tuyệt đối:
   - 15 giây đầu (Hook chấn động): CẤM chào hỏi, CẤM giới thiệu lan man. Vào thẳng một câu thoại chí mạng hoặc khoảnh khắc sốc nhất.
   - Nửa đầu (~40%): Đẩy mâu thuẫn lên cao, để người nghe tức thay nhân vật chính.
   - Giữa truyện (~50% - Midpoint Twist): Tung ra một chi tiết lật kèo hoặc bằng chứng bất ngờ khiến cục diện đảo ngược hoàn toàn.
   - Cuối tập (Cliffhanger): Giải quyết gọn 1 mâu thuẫn nhỏ cho hả dạ, rồi cài ngay một bí mật lớn hơn để người nghe phải bấm theo dõi chờ tập sau.
4. "script_full" là VĂN BẢN THUẦN ĐỂ ĐỌC AUDIO: KHÔNG dùng dấu sao (*), KHÔNG dùng tiêu đề chương, KHÔNG dùng ngoặc đơn ghi chú cảm xúc như (cười nhạt) hay [nhạc nổi lên]. Chỉ dùng dấu phẩy, dấu chấm, dấu chấm hỏi, dấu chấm than để giọng đọc tự ngắt nghỉ tự nhiên.

TRẢ VỀ DUY NHẤT MỘT OBJECT JSON HỢP LỆ theo đúng schema sau:
{{
  "episode_number": {next_ep},
  "title_youtube": "Tiêu đề YouTube kịch tính, tối đa 85 ký tự, có chữ Phần {next_ep}",
  "thumb_badge": "PHẦN {next_ep}",
  "thumb_line1": "3 đến 5 chữ viết hoa cực gắt cho dòng 1 thumbnail",
  "thumb_line2": "3 đến 6 chữ viết hoa gây tò mò cho dòng 2 thumbnail",
  "script_full": "Toàn bộ nội dung truyện 1.300 - 1.550 từ tiếng Việt thuần để đọc TTS...",
  "tiktok_caption": "Caption ngắn 2 dòng kích thích tò mò kèm lời kêu gọi sang YouTube nghe bản full",
  "tiktok_hashtags": "#truyenaudio #dramagiadinh #trongsinh #kectruyen #ngontinh",
  "youtube_description": "Mô tả YouTube 3-4 dòng tóm tắt không spoil kết + lời mời đăng ký kênh đón xem phần tiếp theo",
  "youtube_tags": ["truyện audio", "drama gia đình", "trọng sinh", "ngôn tình", "kể chuyện đêm khuya"],
  "characters": ["Tên - vai trò ngắn gọn"],
  "plot_summary_update": "Tóm tắt gộp toàn bộ mạch truyện tính đến hết Tập {next_ep} trong 4-6 câu",
  "last_cliffhanger": "Mô tả ngắn nút thắt cuối Tập {next_ep} để tập sau nối tiếp"
}}
"""


def _polish_with_groq(script_text: str) -> str:
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_key or os.getenv("USE_GROQ_POLISH", "false").lower() != "true":
        return script_text
    try:
        from groq import Groq

        client = Groq(api_key=groq_key)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Bạn là biên tập viên lời thoại audio drama tiếng Việt. "
                        "Hãy chuốt lại đoạn truyện sau để lời thoại sắc sảo, tự nhiên, kịch tính hơn "
                        "nhưng GIỮ NGUYÊN cốt truyện, độ dài và KHÔNG thêm ký tự đặc biệt hay tiêu đề."
                    ),
                },
                {"role": "user", "content": script_text},
            ],
        )
        polished = (resp.choices[0].message.content or "").strip()
        if len(polished.split()) >= len(script_text.split()) * 0.75:
            print("[StoryEngine] Đã chuốt lời thoại bằng Groq.")
            return polished
    except Exception as exc:
        print(f"[StoryEngine] Bỏ qua bước chuốt Groq ({exc}), dùng bản Gemini.")
    return script_text


def generate_episode(series_key: str = "trong_sinh", custom_topic: str = "") -> tuple[dict, dict]:
    api_key = os.environ["GEMINI_API_KEY"]
    memory = load_memory()
    if series_key not in memory["series"]:
        series_key = "trong_sinh"
    series_state = memory["series"][series_key]

    prompt = _build_prompt(series_key, series_state, custom_topic)
    client = genai.Client(api_key=api_key)

    models_to_try = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
    last_error = None
    episode = None

    for model_name in models_to_try:
        try:
            print(f"[StoryEngine] Đang tạo kịch bản bằng {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.85,
                    response_mime_type="application/json",
                ),
            )
            episode = _extract_json(response.text)
            break
        except Exception as exc:
            print(f"[StoryEngine] Lỗi với {model_name}: {exc}")
            last_error = exc

    if episode is None:
        raise RuntimeError(f"Không tạo được kịch bản từ Gemini: {last_error}")

    episode["script_full"] = _polish_with_groq(episode["script_full"])
    episode["series_key"] = series_key

    series_state["current_episode"] = int(episode.get("episode_number", series_state["current_episode"] + 1))
    series_state["characters"] = episode.get("characters", series_state.get("characters", []))
    series_state["plot_summary"] = episode.get("plot_summary_update", series_state.get("plot_summary", ""))
    series_state["last_cliffhanger"] = episode.get("last_cliffhanger", "")
    series_state.setdefault("history", []).append(
        {
            "episode": series_state["current_episode"],
            "title": episode.get("title_youtube", ""),
        }
    )
    memory["active_series"] = series_key
    return episode, memory
