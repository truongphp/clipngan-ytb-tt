import asyncio
import re
import subprocess
from pathlib import Path
import edge_tts

VOICE_MAP = {
    "narrator": ("vi-VN-HoaiMyNeural", "+3%", "+0Hz"),
    "female": ("vi-VN-HoaiMyNeural", "+5%", "+2Hz"),
    "male": ("vi-VN-NamMinhNeural", "+2%", "-3Hz"),
}


def _clean_text(text: str) -> str:
    text = re.sub(r"[*_#`~]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _get_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(out)


def _ms_to_ass_time(ms: int) -> str:
    h = ms // 3_600_000
    m = (ms % 3_600_000) // 60_000
    s = (ms % 60_000) // 1_000
    cs = (ms % 1_000) // 10
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


async def _synth_segment(
    sem: asyncio.Semaphore,
    idx: int,
    role: str,
    text: str,
    tmp_dir: Path,
) -> tuple[int, Path, list[dict]]:
    voice, rate, pitch = VOICE_MAP.get(role, VOICE_MAP["narrator"])
    out_mp3 = tmp_dir / f"seg_{idx:03d}.mp3"
    clean = _clean_text(text)

    if not re.search(r"[0-9A-Za-z\u00C0-\u1EF9]", clean):
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.3", "-q:a", "9", str(out_mp3)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return idx, out_mp3, []

    last_exc = None
    for attempt in range(4):
        async with sem:
            try:
                use_voice, use_rate, use_pitch = (
                    (voice, rate, pitch) if attempt < 2 else VOICE_MAP["narrator"]
                )
                try:
                    comm = edge_tts.Communicate(
                        clean, voice=use_voice, rate=use_rate, pitch=use_pitch, boundary="WordBoundary"
                    )
                except TypeError:
                    comm = edge_tts.Communicate(clean, voice=use_voice, rate=use_rate, pitch=use_pitch)

                words = []
                sentences = []
                with open(out_mp3, "wb") as f:
                    async for chunk in comm.stream():
                        ctype = chunk.get("type")
                        if ctype == "audio":
                            f.write(chunk["data"])
                        elif ctype == "WordBoundary":
                            words.append(
                                {
                                    "offset_ms": int(chunk["offset"] / 10_000),
                                    "dur_ms": int(chunk["duration"] / 10_000),
                                    "text": chunk["text"],
                                }
                            )
                        elif ctype == "SentenceBoundary":
                            sentences.append(
                                {
                                    "offset_ms": int(chunk["offset"] / 10_000),
                                    "dur_ms": int(chunk["duration"] / 10_000),
                                    "text": chunk["text"],
                                }
                            )
                if out_mp3.exists() and out_mp3.stat().st_size > 0:
                    events = words if words else sentences
                    return idx, out_mp3, events
            except Exception as exc:
                last_exc = exc
        await asyncio.sleep(1.5 * (attempt + 1))

    raise RuntimeError(f"Đoạn {idx} lỗi Edge-TTS sau 4 lần thử: {last_exc}")


def _write_ass_file(cues: list[tuple[int, int, str]], ass_path: Path, play_res_x: int, play_res_y: int, font_size: int, margin_v: int) -> None:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans,{font_size},&H0000D7FF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,3,6,0,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for start_ms, end_ms, body in cues:
        lines.append(f"Dialogue: 0,{_ms_to_ass_time(start_ms)},{_ms_to_ass_time(end_ms)},Default,,0,0,0,,{body}")
    ass_path.write_text("\n".join(lines), encoding="utf-8")


def generate_multivoice_and_ass(
    segments: list[dict],
    audio_path: Path,
    ass_yt_path: Path,
    ass_tt_path: Path,
    peak_segment_index: int = 0,
) -> tuple[Path, Path, Path, float]:
    """Chạy song song 2 luồng edge-tts đa giọng Nam-Nữ có tự thử lại, chuẩn hóa -14 LUFS và xuất Karaoke .ass."""
    tmp_dir = audio_path.parent / "tts_segments"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    async def _run_all():
        sem = asyncio.Semaphore(2)
        tasks = [
            _synth_segment(sem, i, seg.get("role", "narrator"), seg.get("text", ""), tmp_dir)
            for i, seg in enumerate(segments)
        ]
        return await asyncio.gather(*tasks)

    print(f"[VoiceGen] Đang tổng hợp {len(segments)} đoạn thoại Nam-Nữ...")
    results = sorted(asyncio.run(_run_all()), key=lambda x: x[0])

    # Tạo khoảng nghỉ 0.22s giữa các lượt thoại cho tự nhiên
    pause_mp3 = tmp_dir / "pause.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.22", "-q:a", "9", str(pause_mp3)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    concat_lines = []
    cues = []
    offset_ms = 0
    peak_start_sec = 0.0

    for idx, seg_mp3, events in results:
        if idx == peak_segment_index:
            peak_start_sec = offset_ms / 1000.0

        concat_lines.append(f"file '{seg_mp3.resolve()}'")
        concat_lines.append(f"file '{pause_mp3.resolve()}'")

        # Gom từng cụm 7 từ tạo hiệu ứng tô vàng Karaoke (\kf)
        buf = []
        for ev in events:
            buf.append(ev)
            ends = ev["text"].endswith((".", "!", "?", ";", ":"))
            if len(buf) >= 7 or (ends and len(buf) >= 3):
                s_ms = offset_ms + buf[0]["offset_ms"]
                e_ms = offset_ms + buf[-1]["offset_ms"] + max(buf[-1]["dur_ms"], 150)
                k_body = " ".join(f"{{\\kf{max(int(w['dur_ms'] / 10), 8)}}}{_escape_ass(w['text'])}" for w in buf)
                cues.append((s_ms, e_ms, k_body))
                buf = []
        if buf:
            s_ms = offset_ms + buf[0]["offset_ms"]
            e_ms = offset_ms + buf[-1]["offset_ms"] + max(buf[-1]["dur_ms"], 150)
            k_body = " ".join(f"{{\\kf{max(int(w['dur_ms'] / 10), 8)}}}{_escape_ass(w['text'])}" for w in buf)
            cues.append((s_ms, e_ms, k_body))

        offset_ms += int(_get_duration(seg_mp3) * 1000) + 220

    concat_txt = tmp_dir / "concat.txt"
    concat_txt.write_text("\n".join(concat_lines), encoding="utf-8")

    # Nối audio & chuẩn hóa âm lượng phát sóng -14 LUFS
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt),
            "-af",
            "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(audio_path),
        ],
        check=True,
    )

    _write_ass_file(cues, ass_yt_path, 1280, 720, font_size=40, margin_v=52)
    _write_ass_file(cues, ass_tt_path, 720, 1280, font_size=42, margin_v=230)
    print(f"[VoiceGen] Hoàn tất audio -14 LUFS ({offset_ms/1000:.1f}s) & phụ đề Karaoke .ass")
    return audio_path, ass_yt_path, ass_tt_path, peak_start_sec
