from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


def find_ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ytdlp_prefix() -> list[str]:
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    local = Path.home() / ".local" / "bin" / "yt-dlp"
    if local.exists():
        return [str(local)]
    return [sys.executable, "-m", "yt_dlp"]


def _auth_args(cookies: str | None, cookies_from_browser: str | None) -> list[str]:
    args: list[str] = []
    if cookies:
        args += ["--cookies", cookies]
    if cookies_from_browser:
        args += ["--cookies-from-browser", cookies_from_browser]
    return args


@dataclass
class Probe:
    id: str
    title: str
    is_live: bool
    duration: float | None
    resolution: str | None


def probe(
    url: str,
    cookies: str | None = None,
    cookies_from_browser: str | None = None,
    extra_args: list[str] | None = None,
    ipv4: bool = False,
    ipv6: bool = False,
) -> Probe:
    cmd = ytdlp_prefix() + ["-J", "--no-warnings"]
    if ipv4:
        cmd.append("-4")
    if ipv6:
        cmd.append("-6")
    cmd += extra_args or []
    cmd += _auth_args(cookies, cookies_from_browser) + [url]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "yt-dlp probe failed")
    data = json.loads(out.stdout)
    return Probe(
        id=data.get("id", ""),
        title=data.get("title", ""),
        is_live=bool(data.get("is_live")),
        duration=data.get("duration"),
        resolution=data.get("resolution"),
    )


def _record_live(cmd: list[str], seconds: float) -> None:
    proc = subprocess.Popen(cmd)
    deadline = time.time() + seconds
    try:
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.5)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def capture(
    url: str,
    out: str,
    seconds: float | None = None,
    start: float | None = None,
    end: float | None = None,
    quality: int = 720,
    cookies: str | None = None,
    cookies_from_browser: str | None = None,
    ffmpeg: str | None = None,
    fmt: str | None = None,
    no_audio: bool = False,
    extra_args: list[str] | None = None,
    ipv4: bool = False,
    ipv6: bool = False,
) -> Path:
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg or find_ffmpeg()

    info = probe(url, cookies, cookies_from_browser, extra_args, ipv4, ipv6)

    if fmt is None:
        if no_audio:
            fmt = f"bv*[height<={quality}]/b[height<={quality}]/b"
        else:
            fmt = f"bv*[height<={quality}]+ba/b[height<={quality}]/b"

    cmd = ytdlp_prefix() + [url, "-f", fmt, "-o", str(out_path), "--no-part", "--newline"]
    if ipv4:
        cmd.append("-4")
    if ipv6:
        cmd.append("-6")
    cmd += extra_args or []
    cmd += _auth_args(cookies, cookies_from_browser)
    if ff:
        cmd += ["--ffmpeg-location", ff]

    if info.is_live and start is None and end is None:
        cmd.append("--hls-use-mpegts")
        if seconds is None:
            raise RuntimeError("live stream: pass --seconds to bound the recording")
        _record_live(cmd, seconds)
    else:
        if start is not None or end is not None or seconds is not None:
            s = start if start is not None else 0.0
            e = end if end is not None else s + (seconds or 0.0)
            cmd += ["--download-sections", f"*{s}-{e}"]
        subprocess.run(cmd, check=True)

    if not out_path.exists():
        raise RuntimeError(f"expected output not found: {out_path}")
    return out_path
