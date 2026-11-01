"""Automatic checks before upload."""
from __future__ import annotations

import re
from pathlib import Path

from .ff import duration, fps_of, loudness, run, video_stream


def black_segments(path: Path, min_dur: float = 0.4) -> list[tuple[float, float]]:
    err = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-an", "-vf",
               f"blackdetect=d={min_dur}:pix_th=0.08", "-f", "null", "-"])
    return [(float(a), float(b)) for a, b in
            re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]


def silent_segments(path: Path, min_dur: float = 0.7) -> list[tuple[float, float]]:
    err = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
               f"silencedetect=noise=-45dB:d={min_dur}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    return list(zip(starts, ends + [None] * (len(starts) - len(ends))))


def check_render(render: Path, audio_total: float, cfg: dict) -> list[str]:
    """Problems with the animator's delivery (run before assembling)."""
    issues = []
    vs = video_stream(render)
    if not vs:
        return ["Fisierul de la animator nu are pista video."]
    d = duration(render)
    tol = 0.5
    if d < audio_total - tol:
        issues.append(f"Render-ul are {d:.2f}s, audio-ul {audio_total:.2f}s: lipsesc {audio_total - d:.2f}s "
                      "(ultimul cadru va fi inghetat).")
    if d > audio_total + 2:
        issues.append(f"Render-ul e mai lung cu {d - audio_total:.2f}s; se taie automat la final.")
    w, h = int(vs.get("width", 0)), int(vs.get("height", 0))
    v = cfg["video"]
    if (w, h) != (v["width"], v["height"]):
        issues.append(f"Rezolutie livrata {w}x{h}, ceruta {v['width']}x{v['height']} (se adapteaza automat).")
    if fps_of(vs) + 0.5 < v["fps"]:
        issues.append(f"Render la {fps_of(vs):.1f} fps, sub {v['fps']} fps cerut.")
    return issues


def check_final(final: Path, expected_total: float, script: dict, cfg: dict) -> dict:
    q, v, a = cfg["qa"], cfg["video"], cfg["audio"]
    errors, warnings = [], []
    vs = video_stream(final)
    d = duration(final)
    if not vs:
        errors.append("Video-ul final nu are pista video.")
    else:
        if (int(vs["width"]), int(vs["height"])) != (v["width"], v["height"]):
            errors.append(f"Rezolutie {vs['width']}x{vs['height']}, trebuie {v['width']}x{v['height']}.")
        if abs(fps_of(vs) - v["fps"]) > 0.5:
            errors.append(f"FPS {fps_of(vs):.2f}, trebuie {v['fps']}.")
    if abs(d - expected_total) > q["duration_tolerance_s"]:
        errors.append(f"Durata {d:.2f}s difera de audio ({expected_total:.2f}s).")
    if d > q["max_duration_s"]:
        errors.append(f"Durata {d:.1f}s peste maximul de {q['max_duration_s']}s.")
    if d < q["min_duration_s"]:
        warnings.append(f"Durata {d:.1f}s e foarte scurta.")

    blacks = black_segments(final)
    if any(s < 0.2 for s, _ in blacks):
        errors.append("Video-ul incepe cu negru (pierzi hook-ul).")
    if blacks:
        warnings.append(f"Segmente negre: {[(round(s, 2), round(e, 2)) for s, e in blacks]}")
    silences = [(s, e) for s, e in silent_segments(final) if e is None or e < d - 0.3]
    if silences:
        warnings.append(f"Pauze de liniste in mijloc: {[(round(s, 2), e and round(e, 2)) for s, e in silences]}")

    m = loudness(final, a["target_lufs"], a["true_peak_db"])
    lufs, tp = float(m["input_i"]), float(m["input_tp"])
    if abs(lufs - a["target_lufs"]) > q["lufs_tolerance"]:
        warnings.append(f"Loudness {lufs:.1f} LUFS (tinta {a['target_lufs']}).")
    if tp > a["true_peak_db"] + 0.5:
        warnings.append(f"True peak {tp:.1f} dB peste {a['true_peak_db']} dB.")

    title = script.get("title", "")
    if len(title) > 100:
        errors.append("Titlul depaseste 100 de caractere (limita YouTube).")
    errors += [f"Script: {e}" for e in script.get("_validation", {}).get("errors", [])]

    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "duration": round(d, 3), "lufs": round(lufs, 2), "true_peak": round(tp, 2)}
