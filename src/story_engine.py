import json
import os
import re
from pathlib import Path
from google import genai
from google.genai import types

MEMORY_PATH = Path("data/story_memory.json")


def _default_series_state(name: str, genre: str = "trong_sinh") -> dict:
    return {
        "name": name,
        "genre": genre,
        "book_number": 1,
        "book_title": name,
        "current_episode": 0,
        "characters": [],
        "plot_summary": "",
        "last_cliffhanger": "",
        "history": [],
    }


def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return {
            "active_series": "trong_sinh",
            "series": {
                "trong_sinh": _default_series_state("Trọng Sinh Báo Thù & Tiểu Tam", "trong_sinh"),
                "doi_thuong": _default_series_state("Chuyện Đời Thường Ngỡ Ngàng", "doi_thuong"),
            },
        }
    data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    for key, st in data.get("series", {}).items():
        st.setdefault("book_number", 1)
        st.setdefault("book_title", st.get("name", key))
        st.setdefault("genre", "doi_thuong" if key == "doi_thuong" else "trong_sinh")
        st.setdefault("history", [])
    return data


def save_memory(memory: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_series_for_next_book(memory: dict, series_key: str) -> dict:
    st = memory["series"][series_key]
    st["book_number"] = int(st.get("book_number", 1)) + 1
    st["book_title"] = st.get("name", series_key)
    st["current_episode"] = 0
    st["characters"] = []
    st["plot_summary"] = ""
    st["last_cliffhanger"] = ""
    return memory


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


def _build_prompt(
    series_key: str,
    series_state: dict,
    episodes_per_book: int,
    custom_topic: str = "",
) -> str:
    next_ep = series_state["current_episode"] + 1
    book_num = int(series_state.get("book_number", 1))
    is_continuing = next_ep > 1 and bool(series_state.get("plot_summary"))
    is_finale = next_ep >= episodes_per_book
    series_name = series_state.get("name", series_key)

    genre_guide = (
        f"Chủ đề bộ truyện: {series_name}. Phong cách: Drama gia đình, trọng sinh, tiểu tam, báo thù hoặc câu chuyện đời thường có cú lật kèo chấn động ở Việt Nam."
    )

    if is_continuing:
        continuity_block = f"""
BỐI CẢNH CÁC TẬP TRƯỚC (BẮT BUỘC NỐI TIẾP LIỀN MẠCH):
- Bộ {book_num} — Tập {next_ep}/{episodes_per_book}.
- Nhân vật hiện có: {json.dumps(series_state.get("characters", []), ensure_ascii=False)}
- Tóm tắt đến hết Tập {next_ep - 1}: {series_state.get("plot_summary", "")}
- Nút thắt cuối tập trước cần giải quyết ngay đầu tập này: {series_state.get("last_cliffhanger", "")}
"""
    else:
        continuity_block = f"- Bộ {book_num} — Tập 1/{episodes_per_book} (mở màn câu chuyện mới theo chủ đề '{series_name}', đặt tên nhân vật Việt Nam tự nhiên)."

    ending_rule = (
        f"- ĐÂY LÀ TẬP CUỐI (Tập {next_ep}/{episodes_per_book}): Đẩy đại cao trào, lật ngửa toàn bộ sự thật, cho kẻ xấu nhận quả báo đích đáng và khép lại CÁI KẾT TRỌN VẸN, HẢ DẠ."
        if is_finale
        else "- Cuối tập (Cliffhanger): Giải quyết gọn 1 mâu thuẫn nhỏ cho hả dạ, rồi cài ngay một bí mật lớn hơn để người nghe hóng tập tiếp theo."
    )
    topic_block = f"\n- Gợi ý riêng cho tập này: {custom_topic}" if custom_topic else ""

    return f"""Bạn là biên kịch audio drama tiếng Việt chuyên nghiệp cho kênh "Audio Đi Ngủ".
{genre_guide}
{continuity_block}{topic_block}

YÊU CẦU BẮT BUỘC:
1. Viết kịch bản phân vai thành mảng "segments" gồm 16 đến 26 đoạn, tổng cộng khoảng 1.300 đến 1.550 từ tiếng Việt (7–10 phút đọc audio).
2. Mỗi phần tử trong "segments" có:
   - "role": chọn 1 trong 3 giá trị: "narrator" (người kể ngôi thứ nhất "tôi"), "female" (lời thoại nhân vật nữ), "male" (lời thoại nhân vật nam).
   - "text": lời đọc tiếng Việt thuần (KHÔNG dấu sao *, KHÔNG ngoặc ghi chú cảm xúc, KHÔNG ghi tên nhân vật trước câu thoại).
3. Công thức giữ chân 3 nhịp:
   - Segment 0 (Hook 15 giây đầu): CẤM chào hỏi. Vào thẳng khoảnh khắc sốc nhất hoặc câu thoại chí mạng.
   - Segment 1 (Micro-Intro): Bắt đầu bằng đúng 1 câu ngắn "Bạn đang nghe truyện tại kênh Audio Đi Ngủ." rồi dẫn tiếp vào mạch truyện.
   - Giữa tập (~50%): Cú lật kèo (Midpoint Twist) làm đảo ngược cục diện.
   {ending_rule}
4. Chỉ định "peak_segment_index": số thứ tự (0-based) của đoạn bắt đầu phần cao trào kịch tính nhất để cắt clip TikTok 75 giây.

TRẢ VỀ DUY NHẤT 1 OBJECT JSON HỢP LỆ:
{{
  "episode_number": {next_ep},
  "is_finale": {str(is_finale).lower()},
  "book_title": "{series_name[:55]}",
  "title_youtube": "Tiêu đề YouTube kịch tính, tối đa 85 ký tự, có chữ Tập {next_ep}",
  "thumb_badge": "{'TẬP CUỐI' if is_finale else f'TẬP {next_ep}'}",
  "thumb_line1": "3 đến 5 chữ viết hoa cực gắt",
  "thumb_line2": "3 đến 6 chữ viết hoa gây tò mò",
  "peak_segment_index": 0,
  "segments": [
    {{"role": "narrator", "text": "..."}},
    {{"role": "male", "text": "..."}},
    {{"role": "female", "text": "..."}}
  ],
  "tiktok_caption": "Caption 2 dòng kích thích tò mò + kêu gọi sang YouTube Audio Đi Ngủ nghe bản full",
  "tiktok_hashtags": "#truyenaudio #audiodingu #dramagiadinh #trongsinh #ngontinh",
  "youtube_description": "Mô tả 3 dòng hấp dẫn không spoil kết",
  "youtube_tags": ["truyện audio", "audio đi ngủ", "drama gia đình", "trọng sinh", "ngôn tình"],
  "characters": ["Tên - vai trò ngắn"],
  "plot_summary_update": "Tóm tắt mạch truyện đến hết Tập {next_ep} trong 4-6 câu",
  "last_cliffhanger": "Nút thắt cuối Tập {next_ep}"
}}
"""


def _call_groq_fallback(prompt: str) -> dict:
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_key:
        raise RuntimeError("Không có GROQ_API_KEY để dự phòng.")
    from groq import Groq

    client = Groq(api_key=groq_key, timeout=45.0)
    candidates = [
        "openai/gpt-oss-120b",
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-20b",
        "llama-3.1-8b-instant",
    ]
    try:
        available = [
            m.id
            for m in client.models.list().data
            if not any(x in m.id.lower() for x in ["whisper", "guard", "tts", "playai"])
        ]
        for mid in available:
            if mid not in candidates:
                candidates.append(mid)
    except Exception:
        pass

    last_groq_err = None
    for model_id in candidates:
        try:
            print(f"[StoryEngine] Thử phao dự phòng Groq ({model_id})...")
            resp = client.chat.completions.create(
                model=model_id,
                temperature=0.8,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Bạn là biên kịch audio drama tiếng Việt, luôn trả về JSON hợp lệ."},
                    {"role": "user", "content": prompt},
                ],
            )
            return _extract_json(resp.choices[0].message.content or "")
        except Exception as exc:
            print(f"[StoryEngine] Groq {model_id} lỗi: {exc}")
            last_groq_err = exc
    raise RuntimeError(last_groq_err or "Không gọi được model Groq nào.")


def generate_episode(
    series_key: str = "trong_sinh",
    custom_topic: str = "",
    series_name: str = "",
    start_new_book: bool = False,
) -> tuple[dict, dict]:
    episodes_per_book = int(os.getenv("EPISODES_PER_BOOK", "5"))
    memory = load_memory()

    if series_key not in memory["series"]:
        display_name = series_name or custom_topic or series_key.replace("_", " ").title()
        memory["series"][series_key] = _default_series_state(display_name, series_key)
    elif start_new_book:
        memory = reset_series_for_next_book(memory, series_key)
        if series_name:
            memory["series"][series_key]["name"] = series_name
            memory["series"][series_key]["book_title"] = series_name

    series_state = memory["series"][series_key]
    prompt = _build_prompt(series_key, series_state, episodes_per_book, custom_topic)

    episode = None
    last_error = None
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if gemini_key:
        client = genai.Client(api_key=gemini_key, http_options=types.HttpOptions(timeout=45000))
        for model_name in [
            "gemini-3.8-flash",
            "gemini-3.6-flash",
            "gemini-3.1-flash-lite",
            "gemini-flash-latest",
        ]:
            try:
                print(f"[StoryEngine] Đang tạo kịch bản đa vai bằng {model_name}...")
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
                print(f"[StoryEngine] Lỗi {model_name}: {exc}")
                last_error = exc

    if episode is None:
        try:
            episode = _call_groq_fallback(prompt)
        except Exception as groq_exc:
            raise RuntimeError(f"Cả Gemini ({last_error}) và Groq ({groq_exc}) đều lỗi.")

    # Chuẩn hóa segments nếu model trả về script_full thay vì segments
    segments = episode.get("segments")
    if not segments or not isinstance(segments, list):
        fallback_text = episode.get("script_full", "")
        segments = [{"role": "narrator", "text": fallback_text}]
    episode["segments"] = [
        {"role": s.get("role", "narrator"), "text": str(s.get("text", "")).strip()}
        for s in segments
        if str(s.get("text", "")).strip()
    ]

    episode["series_key"] = series_key
    episode["book_number"] = int(series_state.get("book_number", 1))
    episode["episodes_per_book"] = episodes_per_book

    next_ep = int(episode.get("episode_number", series_state["current_episode"] + 1))
    episode["episode_number"] = next_ep
    episode["is_finale"] = bool(next_ep >= episodes_per_book)

    series_state["current_episode"] = next_ep
    if not series_state.get("book_title"):
        series_state["book_title"] = episode.get("book_title") or series_state["name"]
    episode["book_title"] = series_state["book_title"]
    series_state["characters"] = episode.get("characters", series_state.get("characters", []))
    series_state["plot_summary"] = episode.get("plot_summary_update", series_state.get("plot_summary", ""))
    series_state["last_cliffhanger"] = episode.get("last_cliffhanger", "")
    series_state.setdefault("history", []).append(
        {"book": episode["book_number"], "episode": next_ep, "title": episode.get("title_youtube", "")}
    )
    memory["active_series"] = series_key
    return episode, memory
