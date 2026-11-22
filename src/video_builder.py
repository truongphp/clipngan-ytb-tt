import os
import random
import subprocess
from pathlib import Path


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


def _escape_sub_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", "\\:")


def _prepare_mixed_audio(voice_path: Path, bgm_path: Path | None, out_audio: Path, duration: float) -> Path:
    if not bgm_path:
        return voice_path
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(voice_path),
            "-stream_loop",
            "-1",
            "-i",
            str(bgm_path),
            "-t",
            f"{duration:.2f}",
            "-filter_complex",
            "[1:a]volume=0.09[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map",
            "[aout]",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(out_audio),
        ]
    )
    return out_audio


def _build_single_video(
    bg_video: Path | None,
    audio_path: Path,
    srt_path: Path,
    out_path: Path,
    width: int,
    height: int,
    duration: float,
    crf: int,
    sub_font_size: int,
    sub_margin_v: int,
    start_offset: float = 0.0,
) -> Path:
    has_subs = srt_path.exists() and srt_path.stat().st_size > 10
    sub_escaped = _escape_sub_path(srt_path)
    sub_style = (
        f"FontName=Noto Sans,FontSize={sub_font_size},Bold=1,"
        f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        f"BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV={sub_margin_v}"
    )
    sub_filter = f",subtitles='{sub_escaped}':force_style='{sub_style}'" if has_subs else ""

    if bg_video:
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},eq=brightness=-0.06{sub_filter}"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-stream_loop",
            "-1",
            "-ss",
            f"{start_offset:.2f}",
            "-i",
            str(bg_video),
            "-i",
            str(audio_path),
            "-t",
            f"{duration:.2f}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            str(out_path),
        ]
    else:
        vf = (
            f"[1:a]showwaves=s={width}x220:mode=cline:colors=0xF59E0B|0xEF4444:rate=25[waves];"
            f"[0:v][waves]overlay=0:(H-h)/2{sub_filter}[vout]"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=#0B0F19:s={width}x{height}:r=25:d={duration:.2f}",
            "-i",
            str(audio_path),
            "-filter_complex",
            vf,
            "-map",
            "[vout]",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            str(out_path),
        ]

    _run(cmd)
    return out_path


def build_videos(
    voice_path: Path,
    srt_path: Path,
    gameplay_videos: list[Path],
    bgms: list[Path],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    full_duration = get_media_duration(voice_path)
    tiktok_duration = min(float(os.getenv("TIKTOK_DURATION", "75")), full_duration)

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

    mixed_audio = _prepare_mixed_audio(
        voice_path, selected_bgm, output_dir / "mixed_audio.m4a", full_duration
    )

    yt_video = output_dir / "youtube_full.mp4"
    tt_video = output_dir / "tiktok_hook.mp4"

    print(f"[VideoBuilder] Đang render bản YouTube ngang 16:9 ({full_duration:.1f}s)...")
    _build_single_video(
        bg_video=selected_video,
        audio_path=mixed_audio,
        srt_path=srt_path,
        out_path=yt_video,
        width=1280,
        height=720,
        duration=full_duration,
        crf=24,
        sub_font_size=22,
        sub_margin_v=40,
        start_offset=start_offset,
    )

    print(f"[VideoBuilder] Đang render bản TikTok dọc 9:16 ({tiktok_duration:.1f}s)...")
    _build_single_video(
        bg_video=selected_video,
        audio_path=mixed_audio,
        srt_path=srt_path,
        out_path=tt_video,
        width=720,
        height=1280,
        duration=tiktok_duration,
        crf=26,
        sub_font_size=20,
        sub_margin_v=140,
        start_offset=start_offset,
    )

    size_mb = tt_video.stat().st_size / (1024 * 1024)
    if size_mb > 47.0:
        print(f"[VideoBuilder] Bản TikTok nặng {size_mb:.1f}MB -> nén lại cho gọn dưới 45MB...")
        compressed = output_dir / "tiktok_hook_small.mp4"
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(tt_video),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "30",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                str(compressed),
            ]
        )
        compressed.replace(tt_video)

    return yt_video, tt_video
