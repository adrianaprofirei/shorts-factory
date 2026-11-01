"""Audio mix: voice + ducked music bed + SFX at word timestamps -> loudness-normalised master."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .config import ASSETS
from .ff import duration, loudness, run

AUDIO_EXT = (".wav", ".mp3", ".ogg", ".flac", ".m4a")


def pick_music(mood: str, seed: str) -> Path | None:
    folder = ASSETS / "music" / mood
    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in AUDIO_EXT) if folder.exists() else []
    if not files:
        return None
    idx = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(files)
    return files[idx]


def find_sfx(tag: str) -> Path | None:
    for ext in AUDIO_EXT:
        p = ASSETS / "sfx" / f"{tag}{ext}"
        if p.exists():
            return p
    return None


def mix(voice: Path, cues: list[dict], cfg: dict, out_wav: Path, music: Path | None,
        workdir: Path) -> dict:
    """Build master.wav. Returns a report with what was used / skipped."""
    a = cfg["audio"]
    sr = a["sample_rate"]
    total = duration(voice) + a["tail_seconds"]
    report = {"music": str(music) if music else None, "sfx_used": [], "sfx_missing": [],
              "duration": round(total, 3)}

    inputs = ["-i", str(voice)]
    filters = [
        f"[0:a]aresample={sr},aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"volume={a['voice_gain_db']}dB,apad=whole_dur={total:.3f}[voice]"
    ]
    mix_labels = []
    n = 1
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        fade_st = max(0.0, total - 0.8)
        filters.append(
            f"[{n}:a]aresample={sr},aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"atrim=0:{total:.3f},asetpts=N/SR/TB,volume={a['music_gain_db']}dB,"
            f"afade=t=in:d=0.3,afade=t=out:st={fade_st:.3f}:d=0.8[mraw]"
        )
        if a.get("duck_music", True):
            filters.append("[voice]asplit=2[vmix][vkey]")
            filters.append("[mraw][vkey]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=350[music]")
            mix_labels += ["[vmix]", "[music]"]
        else:
            mix_labels += ["[voice]", "[mraw]"]
        n += 1
    else:
        mix_labels.append("[voice]")

    for cue in cues:
        path = find_sfx(cue["tag"])
        if not path:
            report["sfx_missing"].append(cue["tag"])
            continue
        ms = max(0, int(cue["time"] * 1000) - 40)  # 40 ms early feels in-sync
        inputs += ["-i", str(path)]
        filters.append(
            f"[{n}:a]aresample={sr},aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume={a['sfx_gain_db']}dB,adelay={ms}|{ms}[s{n}]"
        )
        mix_labels.append(f"[s{n}]")
        report["sfx_used"].append({"tag": cue["tag"], "time": cue["time"]})
        n += 1

    if len(mix_labels) == 1:
        filters.append(f"{mix_labels[0]}anull[mix]")
    else:
        filters.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:"
                       f"dropout_transition=0:normalize=0[mix]")
    filters.append(f"[mix]atrim=0:{total:.3f},asetpts=N/SR/TB[out]")

    raw = workdir / "_mix_raw.wav"
    run(["ffmpeg", "-y", "-hide_banner", *inputs, "-filter_complex", ";".join(filters),
         "-map", "[out]", "-ar", str(sr), "-c:a", "pcm_s16le", str(raw)])

    # two-pass loudness normalisation
    m = loudness(raw, a["target_lufs"], a["true_peak_db"])
    ln = (f"loudnorm=I={a['target_lufs']}:TP={a['true_peak_db']}:LRA=11:"
          f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(raw), "-af", ln, "-ar", str(sr),
         "-c:a", "pcm_s16le", str(out_wav)])
    raw.unlink(missing_ok=True)
    final = loudness(out_wav, a["target_lufs"], a["true_peak_db"])
    report["lufs"] = float(final["input_i"])
    report["true_peak"] = float(final["input_tp"])
    return report
