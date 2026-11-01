"""Video: animatic (timing reference for the animator) and final assembly."""
from __future__ import annotations

import shutil
from pathlib import Path

from .config import ROOT
from .ff import run

PALETTE = ["#2E4057", "#4F6D7A", "#56A3A6", "#7A6C5D", "#5B4E77", "#3F612D", "#8C4A3C", "#2F5D62"]


def _fonts_into(project: Path, cfg: dict) -> str:
    """Copy the caption font next to the .ass file; return the relative fonts dir."""
    src = ROOT / cfg["captions"]["font_file"]
    dst_dir = project / "_fonts"
    dst_dir.mkdir(exist_ok=True)
    if src.exists():
        shutil.copy2(src, dst_dir / src.name)
    return "_fonts"


def _encode_args(cfg: dict) -> list[str]:
    v = cfg["video"]
    return ["-c:v", "libx264", "-preset", v["preset"], "-crf", str(v["crf"]), "-pix_fmt", "yuv420p",
            "-r", str(v["fps"]), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart"]


def build_animatic(project: Path, shots: list[dict], cfg: dict, ass_name: str,
                   audio_name: str, total: float, out_name: str = "animatic.mp4") -> Path:
    v = cfg["video"]
    W, H, fps = v["width"], v["height"], v["fps"]
    inputs, labels = [], []
    for i, s in enumerate(shots):
        color = PALETTE[i % len(PALETTE)].lstrip("#")
        inputs += ["-f", "lavfi", "-i", f"color=c=0x{color}:s={W}x{H}:r={fps}:d={max(0.04, s['duration']):.3f}"]
        labels.append(f"[{i}:v]")
    a_idx = len(shots)
    inputs += ["-i", audio_name]
    fonts = _fonts_into(project, cfg)
    fc = (f"{''.join(labels)}concat=n={len(shots)}:v=1:a=0,setsar=1,"
          f"ass={ass_name}:fontsdir={fonts},format=yuv420p[v]")
    run(["ffmpeg", "-y", "-hide_banner", *inputs, "-filter_complex", fc, "-map", "[v]",
         "-map", f"{a_idx}:a", "-t", f"{total:.3f}", *_encode_args(cfg), out_name], cwd=project)
    return project / out_name


def zoom_expr(windows: list[tuple[float, float]], zoom: float) -> str:
    if not windows:
        return "1"
    cond = "+".join(f"between(it,{s:.3f},{e:.3f})" for s, e in windows)
    return f"if({cond},{zoom},1)"


def build_final(project: Path, render_name: str, audio_name: str, ass_name: str, cfg: dict,
                total: float, punch_windows: list[tuple[float, float]],
                out_name: str = "final.mp4") -> Path:
    v = cfg["video"]
    W, H, fps = v["width"], v["height"], v["fps"]
    if v.get("fit", "cover") == "contain":
        frame = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                 f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black")
    else:
        frame = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    chain = [f"fps={fps}", frame, "setsar=1", "tpad=stop_mode=clone:stop_duration=3"]
    if v.get("punch_in") and punch_windows:
        z = zoom_expr(punch_windows, v.get("punch_in_zoom", 1.1))
        chain.append(f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}")
    fonts = _fonts_into(project, cfg)
    chain += [f"ass={ass_name}:fontsdir={fonts}", "format=yuv420p"]
    fc = f"[0:v]{','.join(chain)}[v]"
    run(["ffmpeg", "-y", "-hide_banner", "-i", render_name, "-i", audio_name, "-filter_complex", fc,
         "-map", "[v]", "-map", "1:a", "-t", f"{total:.3f}", *_encode_args(cfg), out_name], cwd=project)
    return project / out_name
