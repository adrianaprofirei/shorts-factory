"""Thin ffmpeg / ffprobe helpers."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path


class FFError(RuntimeError):
    pass


def check_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"Nu gasesc '{tool}'. Instaleaza ffmpeg (versiunea 6 sau mai noua) si pune-l in PATH.")


def run(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a command, return stderr (ffmpeg logs there). Raise with a useful tail on error."""
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-25:])
        raise FFError(f"Comanda a esuat: {' '.join(cmd[:6])} ...\n{tail}")
    return proc.stderr


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height,r_frame_rate,sample_rate,channels",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def duration(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def video_stream(path: Path) -> dict | None:
    return next((s for s in probe(path)["streams"] if s["codec_type"] == "video"), None)


def fps_of(stream: dict) -> float:
    num, _, den = stream.get("r_frame_rate", "0/1").partition("/")
    return float(num) / float(den or 1) if float(den or 1) else 0.0


def loudness(path: Path, target: float = -14.0, tp: float = -1.5) -> dict:
    """Measure integrated loudness / true peak with loudnorm's analysis pass."""
    err = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
               f"loudnorm=I={target}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-"])
    match = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", err, flags=re.S)
    if not match:
        raise FFError("Nu am putut masura loudness-ul.")
    return json.loads(match[-1])
