import asyncio
import os
import re
from pathlib import Path
import edge_tts


def _format_srt_time(offset_100ns: int) -> str:
    total_ms = int(offset_100ns / 10_000)
    hours = total_ms // 3_600_000
    minutes = (total_ms % 3_600_000) // 60_000
    seconds = (total_ms % 60_000) // 1_000
    millis = total_ms % 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _clean_text(text: str) -> str:
    text = re.sub(r"[*_#`~]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def _synthesize_async(
    text: str,
    audio_path: Path,
    srt_path: Path,
    voice: str,
    rate: str,
    max_words_per_cue: int = 8,
) -> None:
    try:
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate, boundary="WordBoundary")
    except TypeError:
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate)

    word_events = []
    sentence_events = []

    audio_path.parent.mkdir(parents=True, exist_ok=True)
    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            ctype = chunk.get("type")
            if ctype == "audio":
                audio_file.write(chunk["data"])
            elif ctype == "WordBoundary":
                word_events.append(
                    {
                        "offset": chunk["offset"],
                        "duration": chunk["duration"],
                        "text": chunk["text"],
                    }
                )
            elif ctype == "SentenceBoundary":
                sentence_events.append(
                    {
                        "offset": chunk["offset"],
                        "duration": chunk["duration"],
                        "text": chunk["text"],
                    }
                )

    cues = []
    if word_events:
        buf = []
        for ev in word_events:
            buf.append(ev)
            ends_sentence = ev["text"].endswith((".", "!", "?", ";", ":"))
            if len(buf) >= max_words_per_cue or (ends_sentence and len(buf) >= 3):
                start_ts = buf[0]["offset"]
                end_ts = buf[-1]["offset"] + buf[-1]["duration"]
                cue_text = " ".join(item["text"] for item in buf)
                cues.append((start_ts, end_ts, cue_text))
                buf = []
        if buf:
            start_ts = buf[0]["offset"]
            end_ts = buf[-1]["offset"] + buf[-1]["duration"]
            cue_text = " ".join(item["text"] for item in buf)
            cues.append((start_ts, end_ts, cue_text))
    elif sentence_events:
        for ev in sentence_events:
            cues.append((ev["offset"], ev["offset"] + ev["duration"], ev["text"]))

    srt_lines = []
    for idx, (start_ts, end_ts, cue_text) in enumerate(cues, start=1):
        srt_lines.append(f"{idx}")
        srt_lines.append(f"{_format_srt_time(start_ts)} --> {_format_srt_time(end_ts)}")
        srt_lines.append(cue_text)
        srt_lines.append("")

    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")


def generate_voice_and_subtitles(
    script_text: str,
    audio_path: Path,
    srt_path: Path,
) -> tuple[Path, Path]:
    voice = os.getenv("TTS_VOICE", "vi-VN-HoaiMyNeural").strip()
    rate = os.getenv("TTS_RATE", "+3%").strip()
    clean_script = _clean_text(script_text)

    print(f"[VoiceGen] Đang tạo giọng đọc ({voice}, tốc độ {rate})...")
    asyncio.run(_synthesize_async(clean_script, audio_path, srt_path, voice, rate))
    print(f"[VoiceGen] Đã xuất audio: {audio_path} & phụ đề: {srt_path}")
    return audio_path, srt_path
