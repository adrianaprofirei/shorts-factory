"""Job card for the animator: everything needed to animate without asking questions."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def build_shots(script: dict, timings: list[dict], chunks: list[dict]) -> list[dict]:
    shots = []
    for t in timings:
        b = script["beats"][t["beat"]]
        emph_times = [ch["start"] for ch in chunks if ch["beat"] == t["beat"]
                      and any(w["emphasis"] for w in ch["words"])]
        shots.append({
            "shot": t["beat"] + 1,
            "start": t["start"],
            "end": t["end"],
            "duration": t["duration"],
            "role": b["role"],
            "narration": b["narration"],
            "set": b["shot"]["set"],
            "lighting": b["shot"]["lighting"],
            "cast": b["shot"]["cast"],
            "expression": b["shot"]["expression"],
            "camera": b["shot"]["camera"],
            "action": b["shot"]["action"],
            "vfx": b["shot"]["vfx"],
            "emphasis_at": round(emph_times[0], 2) if emph_times else None,
        })
    return shots


def fmt_time(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:05.2f}"


def write_job_card(script: dict, shots: list[dict], cfg: dict, out_dir: Path, slug: str,
                   audio_duration: float) -> Path:
    v = cfg["video"]
    sets = sorted({s["set"] for s in shots})
    cast = sorted({c for s in shots for c in s["cast"]})
    lines = [
        f"# Job: {script['title']}",
        "",
        f"- Cod job: `{slug}`",
        f"- Durata exacta: **{audio_duration:.2f} s** (egala cu master.wav)",
        f"- Cadre: {len(shots)}",
        f"- Decoruri: {', '.join(sets)}",
        f"- Personaje: {', '.join(cast)}",
        "",
        "## Fisiere primite",
        "- `master.wav`: audio final (voce + muzica + efecte). Animezi exact pe el.",
        "- `animatic.mp4`: referinta de timp: fiecare cadru, cu textul pe ecran.",
        "- `shots.csv`: aceeasi lista de cadre, pentru import in tabel.",
        "",
        "## Ce livrezi",
        f"- Un singur fisier video, **{v['width']}x{v['height']}** (vertical), **{v['fps']} fps**, "
        "H.264 sau ProRes, bitrate mare (minim 20 Mbps).",
        f"- Durata exact {audio_duration:.2f} s, primul cadru sincron cu inceputul lui master.wav.",
        "- FARA subtitrari, text, logo, watermark sau muzica: le adaugam noi automat.",
        "- Poti livra cu sau fara sunet; noi folosim master.wav.",
        "- Fara cadre negre la inceput sau la final.",
        "",
        "## Reguli de imagine",
        "- Fetele si actiunea importanta in mijlocul ecranului, intre 15% si 75% din inaltime.",
        "- Zona de sus 25-40% din inaltime are subtitrarile: nu pune acolo detalii care trebuie citite.",
        "- Jos (ultimele 20%) si dreapta (ultimele 12%) sunt acoperite de butoanele aplicatiei.",
        "- Schimba unghiul la fiecare cadru; misca usor camera in fiecare cadru (push-in, pan, tracking).",
        "- Cuvintele marcate cu rosu (coloana 'Rosu la') primesc un moment vizual clar exact atunci.",
        "",
        "## Lista de cadre",
        "",
        "| # | Timp | Durata | Naratiune | Decor / lumina | Camera | Personaje (fata eroului) | Actiune | VFX | Rosu la |",
        "|---|------|--------|-----------|----------------|--------|--------------------------|---------|-----|---------|",
    ]
    for s in shots:
        emph = fmt_time(s["emphasis_at"]) if s["emphasis_at"] is not None else ""
        lines.append(
            f"| {s['shot']} | {fmt_time(s['start'])}-{fmt_time(s['end'])} | {s['duration']:.2f}s | "
            f"{s['narration']} | {s['set']} / {s['lighting']} | {s['camera']} | "
            f"{', '.join(s['cast'])} ({s['expression']}) | {s['action']} | {s['vfx']} | {emph} |"
        )
    lines += ["", "## Naratiunea completa", "", " ".join(b["narration"] for b in script["beats"]), ""]
    path = out_dir / "job_card.md"
    path.write_text("\n".join(lines), encoding="utf-8")

    with open(out_dir / "shots.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(shots[0].keys()))
        w.writeheader()
        for s in shots:
            w.writerow({**s, "cast": ", ".join(s["cast"])})
    (out_dir / "shots.json").write_text(json.dumps(shots, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
