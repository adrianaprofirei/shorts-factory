"""Shot sheet for making the animation ourselves: per-shot image + video prompts and the files to produce.

Semi-manual mode: you paste the prompts into an image tool (keyframes/shot_XX.png) and a video tool
(clips/shot_XX.mp4); `assemble` turns those files into render.mp4. Later an API can fill the same folders.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from .config import ASSETS, PROMPTS

LIBRARY = ASSETS / "library"


def _readable(id_: str) -> str:
    return id_.replace("_", " ")


def references(shot: dict) -> list[Path]:
    """Reference images to attach: one per character in the shot, plus the set in its lighting."""
    return [LIBRARY / f"{c}.png" for c in shot["cast"]] + [LIBRARY / f"{shot['set']}_{shot['lighting']}.png"]


def build(shots: list[dict], cfg: dict) -> list[dict]:
    lib = cfg["library"]
    who = {lib["hero"]["id"]: f"the hero ({lib['hero']['description']})"}
    who.update({c["id"]: f"{c['id']} ({c['description']})" for c in lib["cast"]})
    image_tpl = (PROMPTS / "keyframe_image.md").read_text(encoding="utf-8").strip()
    video_tpl = (PROMPTS / "clip_video.md").read_text(encoding="utf-8").strip()
    out = []
    for s in shots:
        fields = {
            "set": _readable(s["set"]), "lighting": s["lighting"], "camera": s["camera"],
            "cast": "; ".join(who.get(c, c) for c in s["cast"]), "expression": s["expression"],
            "action": s["action"], "duration": f"{s['duration']:.1f}",
            "vfx": "" if s["vfx"] == "none" else f"Visual effect: {s['vfx']}.",
        }
        n = f"{s['shot']:02d}"
        out.append({
            "shot": s["shot"], "start": s["start"], "end": s["end"], "duration": s["duration"],
            "narration": s["narration"],
            "image_prompt": image_tpl.format(**fields),
            "video_prompt": video_tpl.format(**fields),
            "references": [str(p.relative_to(ASSETS.parent)).replace("\\", "/") for p in references(s)],
            "missing_references": [p.name for p in references(s) if not p.exists()],
            "keyframe": f"keyframes/shot_{n}.png",
            "clip": f"clips/shot_{n}.mp4",
        })
    return out


GROUPS = {"crowd"}  # cast ids that are several different people, drawn as a line-up instead of one turnaround


def build_library(cfg: dict) -> list[dict]:
    """Prompts for the one-time reference images in assets/library/ (characters first, hero first)."""
    lib = cfg["library"]
    char_tpl = (PROMPTS / "ref_character.md").read_text(encoding="utf-8").strip()
    set_tpl = (PROMPTS / "ref_set.md").read_text(encoding="utf-8").strip()
    turnaround = "One character shown four times side by side: front view, 3/4 view, side profile, back view."
    lineup = "A line-up of six different characters side by side, front view, varied casual clothes and hair."
    items = []
    for c in [lib["hero"], *lib["cast"]]:
        group = c["id"] in GROUPS
        prompt = char_tpl.format(layout=lineup if group else turnaround,
                                 who="The characters" if group else "The character", description=c["description"])
        items.append({"file": f"{c['id']}.png", "kind": "personaj", "prompt": prompt})
    for s in lib["sets"]:
        for light in s["lighting"]:
            items.append({"file": f"{s['id']}_{light}.png", "kind": "decor",
                          "prompt": set_tpl.format(set=_readable(s["id"]), lighting=light)})
    for it in items:
        it["exists"] = (LIBRARY / it["file"]).exists()
    return items


def write_library(items: list[dict]) -> Path:
    done = sum(it["exists"] for it in items)
    parts = [f"<!doctype html><meta charset='utf-8'><title>Referinte</title><style>{CSS}</style>",
             f"<h1>Imagini de referinta ({done}/{len(items)} facute)</h1>",
             "<p>Le faci o singura data, cu <b>Nano Banana Pro</b>. Incepi cu <code>hero.png</code>: genereaza "
             "variante pana iti place eroul, el devine mascota canalului. Personajele: orice forma, fundal alb. "
             "Decorurile: alegi <b>9:16</b>. Salvezi in <code>assets/library/</code> cu numele exact de mai jos. "
             "Pentru acelasi stil, ataseaza <code>hero.png</code> ca referinta de stil la celelalte.</p>"]
    for i, it in enumerate(items):
        state = "&#10003; facut" if it["exists"] else "<span class='miss'>lipseste</span>"
        parts.append(f"<div class='card'><b>{it['file']}</b> <span class='meta'>{it['kind']} &middot; {state}</span>"
                     f"<textarea readonly id='r{i}'>{html.escape(it['prompt'])}</textarea>"
                     f"<button onclick=\"cp('r{i}')\">Copiaza</button></div>")
    parts.append(COPY_JS)
    path = LIBRARY / "reference_prompts.html"
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


COPY_JS = ("<script>function cp(id){const t=document.getElementById(id);t.select();"
           "navigator.clipboard.writeText(t.value)}</script>")

CSS = """
body{font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px;background:#f6f5f2;color:#222}
h1{font-size:22px}.card{background:#fff;border:1px solid #ddd;border-radius:10px;padding:14px;margin:14px 0}
.meta{color:#666;font-size:13px}textarea{width:100%;box-sizing:border-box;font:13px/1.4 monospace;height:150px}
button{margin:4px 0 10px;padding:4px 12px;cursor:pointer}.miss{color:#b3261e}code{background:#eee;padding:1px 4px}
"""


def write(items: list[dict], title: str, out_dir: Path) -> Path:
    (out_dir / "shot_prompts.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    missing = sorted({m for it in items for m in it["missing_references"]})
    parts = [f"<!doctype html><meta charset='utf-8'><title>Cadre: {html.escape(title)}</title><style>{CSS}</style>",
             f"<h1>{html.escape(title)}</h1>",
             "<p>Pentru fiecare cadru: 1) copiezi promptul de imagine in AI Studio / Nano Banana, atasezi "
             "referintele, salvezi imaginea aleasa cu numele din <code>keyframes/</code>. 2) Dai imaginea + promptul "
             "video la Kling si salvezi clipul cu numele din <code>clips/</code>. 3) <code>python run.py assemble "
             "&lt;slug&gt;</code>. Un cadru fara clip apare ca imagine cu zoom lent.</p>"]
    if missing:
        parts.append(f"<p class='miss'>Lipsesc referinte in assets/library/: {', '.join(missing)}</p>")
    for i, it in enumerate(items):
        refs = "".join(f"<li class='{'miss' if Path(r).name in it['missing_references'] else ''}'>{r}</li>"
                       for r in it["references"])
        parts.append(
            f"<div class='card'><b>#{it['shot']}</b> <span class='meta'>{it['start']:.2f}-{it['end']:.2f}s "
            f"({it['duration']:.2f}s)</span><p><i>{html.escape(it['narration'])}</i></p>"
            f"<b>Imagine</b> &rarr; <code>{it['keyframe']}</code><textarea readonly id='i{i}'>"
            f"{html.escape(it['image_prompt'])}</textarea><button onclick=\"cp('i{i}')\">Copiaza</button>"
            f"<div class='meta'>Referinte de atasat:</div><ul>{refs}</ul>"
            f"<b>Video</b> &rarr; <code>{it['clip']}</code><textarea readonly id='v{i}'>"
            f"{html.escape(it['video_prompt'])}</textarea><button onclick=\"cp('v{i}')\">Copiaza</button></div>")
    parts.append(COPY_JS)
    path = out_dir / "shot_prompts.html"
    path.write_text("\n".join(parts), encoding="utf-8")
    return path
