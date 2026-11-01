"""Audio mix: voice + ducked music bed + SFX at word timestamps -> loudness-normalised master."""
from __future__ import annotations

import hashlib
import math
import wave
from pathlib import Path

from .config import ASSETS
from .ff import duration, loudness, run
from .timing import alignment_to_words

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


def normalize_sfx(path: Path, target: float, peak: float = -1.0) -> float:
    """Bring one SFX file to a common loudness, without pushing its peak over `peak` dBTP.

    Rewrites the file in place; returns the gain applied in dB (0 if it was already close).
    """
    m = loudness(path, target)
    level, tp = float(m["input_i"]), float(m["input_tp"])
    if not (math.isfinite(level) and math.isfinite(tp)):
        return 0.0  # silent file, nothing to measure
    gain = min(target - level, peak - tp)
    if abs(gain) < 1.5:  # inaudible in the mix; skipping it also avoids re-encoding the mp3 on every run
        return 0.0
    tmp = path.with_name(f"{path.stem}_norm{path.suffix}")
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(path), "-af", f"volume={gain:.2f}dB",
         "-q:a", "2", str(tmp)])  # -q:a 2 = high-quality mp3 (ignored for wav)
    tmp.replace(path)
    return gain


def cap_pauses(voice: Path, alignment: dict, max_pause: float, sr: int, out_wav: Path) -> tuple[dict, float]:
    """Shorten every silence between words to `max_pause` seconds.

    Cuts the middle of each long gap (keeps max_pause/2 after the word and before the next one),
    then shifts the alignment so captions and shots stay in sync. Returns (alignment, seconds removed).
    """
    words = alignment_to_words(alignment)
    half = max_pause / 2
    cuts = [(a["end"] + half, b["start"] - half) for a, b in zip(words, words[1:])
            if b["start"] - a["end"] > max_pause]

    run(["ffmpeg", "-y", "-hide_banner", "-i", str(voice), "-ac", "1", "-ar", str(sr),
         "-c:a", "pcm_s16le", str(out_wav)])
    with wave.open(str(out_wav), "rb") as w:
        params = w.getparams()
        pcm = w.readframes(w.getnframes())
    width = params.sampwidth  # bytes per sample (mono)
    kept, pos = [], 0
    for start, end in cuts:
        a, b = int(start * sr) * width, int(end * sr) * width
        kept.append(pcm[pos:a])
        pos = b
    kept.append(pcm[pos:])
    with wave.open(str(out_wav), "wb") as w:
        w.setparams(params)
        w.writeframes(b"".join(kept))

    def shift(t: float) -> float:
        return round(t - sum(min(end, t) - start for start, end in cuts if start < t), 4)

    new = {
        "characters": alignment["characters"],
        "character_start_times_seconds": [shift(t) for t in alignment["character_start_times_seconds"]],
        "character_end_times_seconds": [shift(t) for t in alignment["character_end_times_seconds"]],
    }
    return new, sum(end - start for start, end in cuts)


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
