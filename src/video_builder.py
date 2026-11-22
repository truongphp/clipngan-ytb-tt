import asyncio
import os
import random
import subprocess
from pathlib import Path
import edge_tts
import requests
from PIL import Image, ImageDraw


def _run(cmd: list[str]) -> None:
    print("[FFmpeg]", " ".join(cmd))
    subprocess.run(cmd, check=True)


def get_media_duration(file_path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ],
        text=True,
    ).strip()
    return float(out)


def _escape_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", "\\:")


def _prepare_watermark(output_dir: Path, size: int = 84) -> Path | None:
    wm_url = os.getenv("WATERMARK_URL", "https://i.ibb.co/s91HtYWs/IMG-2119.jpg").strip()
    if not wm_url:
        return None
    raw_path = output_dir / "wm_raw.jpg"
    png_path = output_dir / f"wm_{size}.png"
    try:
        if not raw_path.exists():
            r = requests.get(wm_url, timeout=20)
            r.raise_for_status()
            raw_path.write_bytes(r.content)

        img = Image.open(raw_path).convert("RGBA")
        w, h = img.size
        side = min(w, h)
        left, top = (w - side) // 2, (h - side) // 2
        img = img.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)

        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([0, 0, size, size], radius=size // 4, fill=145)
        img.putalpha(mask)
        img.save(png_path, "PNG")
        return png_path
    except Exception as exc:
        print(f"[VideoBuilder] Bỏ qua watermark ({exc}).")
        return None


def _make_outro_audio(text: str, out_path: Path) -> Path | None:
    try:
        async def _gen():
            comm = edge_tts.Communicate(text, voice="vi-VN-HoaiMyNeural", rate="+3%")
            await comm.save(str(out_path))

        asyncio.run(_gen())
        return out_path
    except Exception as exc:
        print(f"[VideoBuilder] Bỏ qua outro ({exc}).")
        return None


def _append_outro(main_audio: Path, outro_audio: Path | None, out_path: Path) -> Path:
    if not outro_audio or not outro_audio.exists():
        return main_audio
    _run(
        [
            "ffmpeg", "-y", "-i", str(main_audio), "-i", str(outro_audio),
            "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[aout]",
            "-map", "[aout]", "-c:a", "aac", "-b:a", "128k", str(out_path),
        ]
    )
    return out_path


def _prepare_ducked_audio(voice_path: Path, bgm_path: Path | None, out_audio: Path, duration: float) -> Path:
    if not bgm_path:
        return voice_path
    _run(
        [
            "ffmpeg", "-y",
            "-i", str(voice_path),
            "-stream_loop", "-1", "-i", str(bgm_path),
            "-t", f"{duration:.2f}",
            "-filter_complex",
            "[0:a]asplit=2[v_sc][v_mix];"
            "[1:a]volume=0.14[bg_raw];"
            "[bg_raw][v_sc]sidechaincompress=threshold=0.02:ratio=6:attack=80:release=400[bg_duck];"
            "[v_mix][bg_duck]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "[aout]", "-c:a", "aac", "-b:a", "128k", str(out_audio),
        ]
    )
    return out_audio


def _build_studio_video(
    bg_video: Path | None,
    audio_path: Path,
    ass_path: Path,
    out_path: Path,
    width: int,
    height: int,
    duration: float,
    crf: int,
    wm_path: Path | None = None,
    start_offset: float = 0.0,
) -> Path:
    has_ass = ass_path.exists() and ass_path.stat().st_size > 50
    ass_filter = f",ass='{_escape_filter_path(ass_path)}'" if has_ass else ""
    progress_bar = f",drawbox=x=0:y=ih-8:w='iw*t/{max(duration, 1.0):.2f}':h=8:color=0xEF4444@0.9:t=fill"

    if bg_video:
        base_chain = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},eq=brightness=-0.07,vignette=PI/5"
            f"{ass_filter}{progress_bar}[vbase]"
        )
        inputs = [
            "-stream_loop", "-1", "-ss", f"{start_offset:.2f}", "-i", str(bg_video),
            "-i", str(audio_path),
        ]
    else:
        base_chain = (
            f"[1:a]showwaves=s={width}x200:mode=cline:colors=0xF59E0B|0xEF4444:rate=25[waves];"
            f"[0:v][waves]overlay=0:(H-h)/2{ass_filter}{progress_bar}[vbase]"
        )
        inputs = [
            "-f", "lavfi", "-i", f"color=c=#0B0F19:s={width}x{height}:r=25:d={duration:.2f}",
            "-i", str(audio_path),
        ]

    if wm_path and wm_path.exists():
        inputs.extend(["-i", str(wm_path)])
        filter_complex = f"{base_chain};[vbase][2:v]overlay=W-w-24:24[vout]"
    else:
        filter_complex = f"{base_chain};[vbase]null[vout]"

    _run(
        [
            "ffmpeg", "-y", *inputs, "-t", f"{duration:.2f}",
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-r", "25", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-shortest", str(out_path),
        ]
    )
    return out_path


def _shift_ass_for_clip(src_ass: Path, dst_ass: Path, start_sec: float, duration_sec: float) -> None:
    if not src_ass.exists():
        return
    start_cs = int(start_sec * 100)
    end_cs = int((start_sec + duration_sec) * 100)

    def to_cs(ts: str) -> int:
        h, m, s_cs = ts.split(":")
        s, cs = s_cs.split(".")
        return ((int(h) * 3600 + int(m) * 60 + int(s)) * 100) + int(cs)

    def from_cs(cs_val: int) -> str:
        cs_val = max(0, cs_val)
        h = cs_val // 360000
        m = (cs_val % 360000) // 6000
        s = (cs_val % 6000) // 100
        cs = cs_val % 100
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    out_lines = []
    for line in src_ass.read_text(encoding="utf-8").splitlines():
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            if len(parts) == 10:
                s_c = to_cs(parts[1])
                e_c = to_cs(parts[2])
                if e_c > start_cs and s_c < end_cs:
                    parts[1] = from_cs(s_c - start_cs)
                    parts[2] = from_cs(min(e_c, end_cs) - start_cs)
                    out_lines.append(",".join(parts))
        else:
            out_lines.append(line)
    dst_ass.write_text("\n".join(out_lines), encoding="utf-8")


def build_videos(
    voice_path: Path,
    ass_yt_path: Path,
    ass_tt_path: Path,
    gameplay_videos: list[Path],
    bgms: list[Path],
    output_dir: Path,
    peak_start_sec: float = 0.0,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    full_duration = get_media_duration(voice_path)
    tiktok_sec = min(float(os.getenv("TIKTOK_DURATION", "75")), full_duration)

    selected_video = random.choice(gameplay_videos) if gameplay_videos else None
    selected_bgm = random.choice(bgms) if bgms else None

    start_offset = 0.0
    if selected_video:
        try:
            vid_dur = get_media_duration(selected_video)
            if vid_dur > 30:
                start_offset = random.uniform(0, max(1.0, vid_dur - 20))
        except Exception:
            start_offset = 0.0

    mixed_audio = _prepare_ducked_audio(voice_path, selected_bgm, output_dir / "mixed_audio.m4a", full_duration)

    yt_outro = _make_outro_audio(
        "Cảm ơn bạn đã lắng nghe. Cho mình xin một like và một đăng ký kênh để có thêm động lực ra tập sau nhé!",
        output_dir / "yt_outro.mp3",
    )
    yt_final_audio = _append_outro(mixed_audio, yt_outro, output_dir / "yt_final_audio.m4a")
    yt_total_dur = get_media_duration(yt_final_audio)

    clip_start = min(max(0.0, peak_start_sec), max(0.0, full_duration - tiktok_sec))
    tt_hook_cut = output_dir / "tt_hook_cut.m4a"
    _run(
        [
            "ffmpeg", "-y", "-ss", f"{clip_start:.2f}", "-i", str(mixed_audio),
            "-t", f"{tiktok_sec:.2f}", "-c:a", "aac", "-b:a", "128k", str(tt_hook_cut),
        ]
    )
    tt_outro = _make_outro_audio(
        "Cho mình xin một like và một follow để có thêm động lực ra tập sau, hoặc sang YouTube Audio Đi Ngủ nghe trọn bộ nhé!",
        output_dir / "tt_outro.mp3",
    )
    tt_final_audio = _append_outro(tt_hook_cut, tt_outro, output_dir / "tt_final_audio.m4a")
    tt_total_dur = get_media_duration(tt_final_audio)

    tt_shifted_ass = output_dir / "tt_shifted.ass"
    _shift_ass_for_clip(ass_tt_path, tt_shifted_ass, clip_start, tiktok_sec)

    wm_yt = _prepare_watermark(output_dir, size=82)
    wm_tt = _prepare_watermark(output_dir, size=70)

    yt_video = output_dir / "youtube_full.mp4"
    tt_video = output_dir / "tiktok_hook.mp4"

    print(f"[VideoBuilder] Đang render YouTube 16:9 Studio HUD ({yt_total_dur:.1f}s)...")
    _build_studio_video(selected_video, yt_final_audio, ass_yt_path, yt_video, 1280, 720, yt_total_dur, 24, wm_yt, start_offset)

    print(f"[VideoBuilder] Đang render TikTok 9:16 Đỉnh Cao Trào ({tt_total_dur:.1f}s, bắt đầu @{clip_start:.1f}s)...")
    _build_studio_video(selected_video, tt_final_audio, tt_shifted_ass, tt_video, 720, 1280, tt_total_dur, 26, wm_tt, start_offset)

    if tt_video.stat().st_size / (1024 * 1024) > 47.0:
        compressed = output_dir / "tiktok_hook_small.mp4"
        _run(["ffmpeg", "-y", "-i", str(tt_video), "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-b:a", "96k", str(compressed)])
        compressed.replace(tt_video)

    return yt_video, tt_video


def merge_full_book_stream_copy(ep_videos: list[tuple[int, Path]], output_dir: Path) -> tuple[Path, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    concat_txt = output_dir / "concat_full_book.txt"
    out_video = output_dir / "youtube_full_book.mp4"

    lines = []
    chapters = []
    elapsed = 0
    for ep_num, vpath in ep_videos:
        mins, secs = divmod(int(elapsed), 60)
        hrs, mins = divmod(mins, 60)
        ts = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs else f"{mins:02d}:{secs:02d}"
        chapters.append(f"{ts} Tập {ep_num}")
        lines.append(f"file '{vpath.resolve()}'")
        elapsed += int(get_media_duration(vpath))

    concat_txt.write_text("\n".join(lines), encoding="utf-8")
    print(f"[VideoBuilder] Đang gộp {len(ep_videos)} tập bằng Stream Copy (-c copy)...")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c", "copy", str(out_video)])
    return out_video, "\n".join(chapters)
