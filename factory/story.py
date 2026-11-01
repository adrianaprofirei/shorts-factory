"""Story engine: premise ideas -> script with shot list -> critic/rewrite -> validation."""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import PROJECTS, PROMPTS
from .llm import ask_json

MOODS = {"wonder", "tense", "emotional", "playful"}
ROLES = {"hook", "demo", "limit", "crisis", "climax", "ending"}
HISTORY = PROJECTS / "premise_history.jsonl"


# ------------------------------------------------------------------ helpers
def clean_token(word: str) -> str:
    """'Brother,' -> 'brother' (used everywhere words are compared)."""
    return re.sub(r"[^\w']", "", word.lower()).strip("'")


def beat_words(narration: str) -> list[str]:
    return narration.split()


def full_narration(script: dict) -> str:
    return " ".join(b["narration"].strip() for b in script["beats"])


def word_count(script: dict) -> int:
    return len(full_narration(script).split())


def library_text(cfg: dict) -> str:
    lib = cfg["library"]
    lines = ["## PRODUCTION LIBRARY (use only these ids)"]
    lines.append(f"- hero: {lib['hero']['description']}")
    lines.append("- cast: " + "; ".join(f"{c['id']} ({c['description']})" for c in lib["cast"]))
    lines.append("- sets: " + "; ".join(f"{s['id']} [lighting: {', '.join(s['lighting'])}]" for s in lib["sets"]))
    lines.append("- expressions: " + ", ".join(lib["expressions"]))
    lines.append("- cameras: " + ", ".join(lib["cameras"]))
    lines.append("- vfx: " + ", ".join(lib["vfx"]))
    lines.append("- sfx tags: " + ", ".join(lib["sfx_tags"]))
    return "\n".join(lines)


def load_prompt(name: str, cfg: dict, fmt: bool = True) -> str:
    text = (PROMPTS / name).read_text(encoding="utf-8")
    if fmt:
        s = cfg["story"]
        text = text.format(
            min_words=s["min_words"], max_words=s["max_words"],
            max_words_per_beat=s["max_words_per_beat"], max_title_chars=s["max_title_chars"],
        )
    return text + "\n\n" + library_text(cfg)


def read_history(limit: int = 300) -> list[str]:
    if not HISTORY.exists():
        return []
    rows = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line)["premise"])
        except (json.JSONDecodeError, KeyError):
            continue
    return rows[-limit:]


def add_to_history(premise: str, slug: str) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps({"premise": premise, "slug": slug,
                            "date": datetime.now(timezone.utc).isoformat()}) + "\n")


# --------------------------------------------------------------- validation
def validate_script(script: dict, cfg: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors must be fixed before production."""
    s, lib = cfg["story"], cfg["library"]
    errors, warnings = [], []
    sets = {x["id"]: x["lighting"] for x in lib["sets"]}
    cast_ids = {"hero"} | {c["id"] for c in lib["cast"]}

    for key in ("title", "premise", "beats", "description", "pinned_comment", "music_mood", "ending_type"):
        if key not in script or script[key] in (None, "", []):
            errors.append(f"Lipseste campul '{key}'.")
    if errors:
        return errors, warnings

    beats = script["beats"]
    if not (s["min_beats"] <= len(beats) <= s["max_beats"]):
        errors.append(f"{len(beats)} beats; trebuie {s['min_beats']}-{s['max_beats']}.")
    total = word_count(script)
    if not (s["min_words"] <= total <= s["max_words"]):
        errors.append(f"{total} cuvinte in total; trebuie {s['min_words']}-{s['max_words']}.")
    title = script["title"].strip()
    if len(title) > s["max_title_chars"]:
        errors.append(f"Titlul are {len(title)} caractere; maxim {s['max_title_chars']}.")
    if not title.endswith("..."):
        warnings.append("Titlul nu se termina cu '...'.")
    if script["music_mood"] not in MOODS:
        errors.append(f"music_mood '{script['music_mood']}' nu e in {sorted(MOODS)}.")
    if script["ending_type"] not in ("resolution", "cliffhanger"):
        errors.append("ending_type trebuie sa fie 'resolution' sau 'cliffhanger'.")

    for i, b in enumerate(beats, 1):
        nar = (b.get("narration") or "").strip()
        tag = f"Beat {i}"
        if not nar:
            errors.append(f"{tag}: narration goala.")
            continue
        words = beat_words(nar)
        tokens = [clean_token(w) for w in words]
        if len(words) > s["max_words_per_beat"]:
            errors.append(f"{tag}: {len(words)} cuvinte; maxim {s['max_words_per_beat']}.")
        if '"' in nar or "\u201c" in nar or "\u201d" in nar:
            errors.append(f"{tag}: contine ghilimele (personajele nu vorbesc).")
        if "..." in nar or "\u2026" in nar or " - " in nar or "\u2014" in nar:
            warnings.append(f"{tag}: evita '...' si liniile de dialog in naratiune.")
        if b.get("role") not in ROLES:
            errors.append(f"{tag}: role '{b.get('role')}' invalid.")
        emph = b.get("emphasis")
        if emph and clean_token(emph) not in tokens:
            errors.append(f"{tag}: emphasis '{emph}' nu apare in narratiune.")
        for fx in b.get("sfx") or []:
            if fx.get("tag") not in lib["sfx_tags"]:
                errors.append(f"{tag}: sfx '{fx.get('tag')}' nu e in biblioteca.")
            if clean_token(fx.get("at_word", "")) not in tokens:
                errors.append(f"{tag}: sfx at_word '{fx.get('at_word')}' nu apare in narratiune.")
        shot = b.get("shot") or {}
        if shot.get("set") not in sets:
            errors.append(f"{tag}: set '{shot.get('set')}' nu e in biblioteca.")
        elif shot.get("lighting") not in sets[shot["set"]]:
            errors.append(f"{tag}: lighting '{shot.get('lighting')}' nu exista pentru {shot['set']}.")
        for c in shot.get("cast") or []:
            if c not in cast_ids:
                errors.append(f"{tag}: personajul '{c}' nu e in biblioteca.")
        if shot.get("expression") not in lib["expressions"]:
            errors.append(f"{tag}: expresia '{shot.get('expression')}' nu e in biblioteca.")
        if shot.get("camera") not in lib["cameras"]:
            errors.append(f"{tag}: camera '{shot.get('camera')}' nu e in biblioteca.")
        if shot.get("vfx") not in lib["vfx"]:
            errors.append(f"{tag}: vfx '{shot.get('vfx')}' nu e in biblioteca.")
        if not (shot.get("action") or "").strip():
            errors.append(f"{tag}: lipseste descrierea actiunii.")

    first_words = len(beat_words(beats[0].get("narration", "")))
    if first_words > 9:
        warnings.append("Primul beat e lung; hook-ul trebuie sa fie rapid.")
    used_sets = {b.get("shot", {}).get("set") for b in beats}
    if len(used_sets) > 4:
        warnings.append(f"{len(used_sets)} decoruri folosite; tinta e 2-4 (animatie mai ieftina).")
    n_emph = sum(1 for b in beats if b.get("emphasis"))
    if n_emph == 0:
        warnings.append("Niciun cuvant-cheie rosu.")
    cams = [b.get("shot", {}).get("camera") for b in beats]
    repeats = sum(1 for a, b in zip(cams, cams[1:]) if a == b)
    if repeats > 3:
        warnings.append(f"Camera se repeta de {repeats} ori la rand; variaza unghiurile.")
    return errors, warnings


# ------------------------------------------------------------------- steps
def generate_ideas(cfg: dict, n: int, theme: str | None, mock: bool) -> dict:
    if mock:
        return copy.deepcopy(MOCK_IDEAS)
    system = load_prompt("ideas_system.md", cfg, fmt=False)
    banned = cfg["story"].get("banned_premises", []) + read_history()
    user = f"Generate {n} new premises."
    if theme:
        user += f" Theme or constraint for this batch: {theme}."
    user += "\n\n## BANNED premises (and anything too close to them)\n" + "\n".join(f"- {p}" for p in banned)
    return ask_json(system, user, cfg["llm"]["model"], cfg["llm"]["max_tokens"])


def write_script(cfg: dict, premise: dict | str, mock: bool) -> dict:
    if mock:
        return copy.deepcopy(MOCK_SCRIPT)
    system = load_prompt("script_system.md", cfg)
    if isinstance(premise, dict):
        brief = json.dumps(premise, ensure_ascii=False, indent=2)
    else:
        brief = premise
    user = f"Write the full script for this premise:\n\n{brief}"
    return ask_json(system, user, cfg["llm"]["model"], cfg["llm"]["max_tokens"])


def critique(cfg: dict, script: dict, mock: bool) -> dict:
    if mock:
        return {"scores": {"hook": 8, "clarity": 9, "escalation": 8, "payoff": 8,
                           "loop": 8, "visuals": 9, "pacing": 9, "safety": 10},
                "issues": ["(mock) niciun apel real catre API"],
                "revised_script": copy.deepcopy(script)}
    system = load_prompt("critic_system.md", cfg)
    user = "Here is the script to judge and rewrite:\n\n" + json.dumps(script, ensure_ascii=False, indent=2)
    return ask_json(system, user, cfg["llm"]["model"], cfg["llm"]["max_tokens"])


def fix_script(cfg: dict, script: dict, errors: list[str]) -> dict:
    system = load_prompt("script_system.md", cfg)
    user = ("This script breaks the rules. Fix ONLY these problems and return the full corrected JSON.\n\n"
            "Problems:\n" + "\n".join(f"- {e}" for e in errors) +
            "\n\nScript:\n" + json.dumps(script, ensure_ascii=False, indent=2))
    return ask_json(system, user, cfg["llm"]["model"], cfg["llm"]["max_tokens"])


def build_script(cfg: dict, premise: dict | str, out_dir: Path, mock: bool) -> dict:
    """Full chain: write -> critic rounds -> validate -> auto-fix -> save."""
    print("  1/3 scriu scriptul...")
    script = write_script(cfg, premise, mock)
    (out_dir / "script_v0.json").write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")

    for rnd in range(cfg["llm"].get("critic_rounds", 1)):
        print(f"  2/3 critic, runda {rnd + 1}...")
        review = critique(cfg, script, mock)
        (out_dir / f"critic_{rnd + 1}.json").write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
        if isinstance(review.get("revised_script"), dict) and review["revised_script"].get("beats"):
            script = review["revised_script"]

    print("  3/3 validez...")
    errors, warnings = validate_script(script, cfg)
    attempts = 0
    while errors and not mock and attempts < 2:
        attempts += 1
        print(f"  ... {len(errors)} erori, cer corectura (incercarea {attempts})")
        script = fix_script(cfg, script, errors)
        errors, warnings = validate_script(script, cfg)

    script["_validation"] = {"errors": errors, "warnings": warnings, "words": word_count(script)}
    (out_dir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "script.md").write_text(script_markdown(script), encoding="utf-8")
    return script


def script_markdown(script: dict) -> str:
    lines = [f"# {script['title']}", "", f"**Premisa:** {script['premise']}",
             f"**Final:** {script['ending_type']} · **Muzica:** {script['music_mood']} · "
             f"**Cuvinte:** {word_count(script)}", "", "## Naratiune", ""]
    for i, b in enumerate(script["beats"], 1):
        emph = f"  _(rosu: {b['emphasis']})_" if b.get("emphasis") else ""
        lines.append(f"{i}. [{b['role']}] {b['narration']}{emph}")
    lines += ["", "## Descriere", "", script["description"], "", "## Comentariu fixat", "",
              script["pinned_comment"]]
    v = script.get("_validation", {})
    if v.get("errors") or v.get("warnings"):
        lines += ["", "## Validare"]
        lines += [f"- EROARE: {e}" for e in v.get("errors", [])]
        lines += [f"- atentie: {w}" for w in v.get("warnings", [])]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- mock data
def _shot(set_, light, cast, expr, cam, action, vfx="none"):
    return {"set": set_, "lighting": light, "cast": cast, "expression": expr,
            "camera": cam, "action": action, "vfx": vfx}


MOCK_SCRIPT = {
    "title": "His Shadow Did Everything He Was Afraid To...",
    "premise": "A boy discovers his shadow does everything he is too scared to do.",
    "ending_type": "cliffhanger",
    "music_mood": "wonder",
    "beats": [
        {"role": "hook", "narration": "A boy discovers his shadow", "emphasis": "shadow",
         "shot": _shot("home_bedroom", "day", ["hero"], "confused", "low angle",
                       "The boy stands still; his shadow on the wall tilts its head on its own."),
         "sfx": [{"tag": "magic", "at_word": "shadow"}]},
        {"role": "hook", "narration": "does everything he is too scared to do.", "emphasis": "scared",
         "shot": _shot("home_bedroom", "day", ["hero"], "scared", "close-up",
                       "The shadow peels off the wall and stretches, the boy steps back."),
         "sfx": []},
        {"role": "demo", "narration": "It raises its hand in class,", "emphasis": None,
         "shot": _shot("school", "day", ["hero", "crowd"], "shocked", "wide establishing",
                       "In class, the boy's shadow raises a dark hand high while he hides behind a book."),
         "sfx": [{"tag": "pop", "at_word": "raises"}]},
        {"role": "demo", "narration": "talks to the new kid at lunch,", "emphasis": None,
         "shot": _shot("school", "day", ["hero", "neighbor"], "panicked", "over-the-shoulder",
                       "The shadow slides across the table and waves at the new kid."),
         "sfx": []},
        {"role": "demo", "narration": "and sings first at the school show.", "emphasis": None,
         "shot": _shot("school", "day", ["hero", "friend", "crowd"], "amazed", "low angle",
                       "On the school stage the shadow grabs the microphone while the boy hides behind the curtain."),
         "sfx": [{"tag": "whoosh", "at_word": "sings"}]},
        {"role": "limit", "narration": "But every time it acts,", "emphasis": None,
         "shot": _shot("home_bedroom", "night", ["hero"], "tired", "medium",
                       "The boy sits on his bed; his shadow on the wall is noticeably larger."),
         "sfx": []},
        {"role": "limit", "narration": "the shadow gets a little bigger", "emphasis": "bigger",
         "shot": _shot("home_bedroom", "night", ["hero"], "scared", "push-in",
                       "The shadow grows until it covers the whole wall and ceiling."),
         "sfx": [{"tag": "rumble", "at_word": "bigger"}]},
        {"role": "limit", "narration": "and he gets a little quieter.", "emphasis": None,
         "shot": _shot("home_bedroom", "night", ["hero", "mom"], "sad", "high angle",
                       "The boy sits small on his bed, not answering his mom at the door."),
         "sfx": []},
        {"role": "crisis", "narration": "Then the storm hits his street.", "emphasis": "storm",
         "shot": _shot("street", "night", ["crowd"], "neutral", "wide establishing",
                       "Rain and wind lash the street, a lamp post flickers out.", "lightning"),
         "sfx": [{"tag": "thunder", "at_word": "storm"}]},
        {"role": "crisis", "narration": "His little brother is stuck on the roof,", "emphasis": "roof",
         "shot": _shot("rooftop", "night", ["brother"], "crying", "low angle",
                       "The little brother clings to the chimney as the wind pushes him.", "water"),
         "sfx": [{"tag": "wind", "at_word": "stuck"}]},
        {"role": "crisis", "narration": "and the shadow is already climbing.", "emphasis": None,
         "shot": _shot("street", "night", ["hero"], "shocked", "tracking",
                       "The giant shadow climbs the house wall alone, the boy frozen at the door."),
         "sfx": []},
        {"role": "climax", "narration": "This time, the boy grabs its hand", "emphasis": "grabs",
         "shot": _shot("street", "night", ["hero"], "determined", "extreme close-up",
                       "The boy's hand closes around the shadow's dark hand.", "glow"),
         "sfx": [{"tag": "impact", "at_word": "grabs"}]},
        {"role": "climax", "narration": "and climbs beside it.", "emphasis": None,
         "shot": _shot("rooftop", "night", ["hero"], "determined", "tracking",
                       "Boy and shadow climb the drainpipe side by side through the rain.", "water"),
         "sfx": []},
        {"role": "climax", "narration": "Together they pull his brother inside.", "emphasis": None,
         "shot": _shot("home_bedroom", "night", ["hero", "brother"], "relieved", "medium",
                       "They tumble through the window onto the bedroom floor, safe.", "none"),
         "sfx": [{"tag": "slam", "at_word": "inside"}]},
        {"role": "ending", "narration": "When the lights come back on,", "emphasis": None,
         "shot": _shot("home_bedroom", "night", ["hero", "brother", "mom", "dad"], "relieved", "wide establishing",
                       "The lights flicker on; the family hugs in the bedroom."),
         "sfx": []},
        {"role": "ending", "narration": "his shadow is normal size again.", "emphasis": "normal",
         "shot": _shot("home_bedroom", "night", ["hero"], "happy", "low angle",
                       "On the wall, the boy's shadow is small and normal again."),
         "sfx": []},
        {"role": "ending", "narration": "Then it waves at him first.", "emphasis": "waves",
         "shot": _shot("home_bedroom", "night", ["hero"], "shocked", "close-up",
                       "The shadow lifts its hand and waves before the boy moves.", "sparkles"),
         "sfx": [{"tag": "magic", "at_word": "waves"}]},
    ],
    "description": "His shadow was braver than him. Until the night of the storm.\n\n#shorts #roblox #animation",
    "pinned_comment": "What would YOUR shadow do first?",
}

MOCK_IDEAS = {
    "ideas": [
        {"premise": "A boy discovers his shadow does everything he is too scared to do.",
         "demos": ["raises hand in class", "talks to the new kid", "climbs the tallest tree"],
         "limit": "the shadow grows while the boy fades", "crisis": "little brother stuck on the roof in a storm",
         "payoff": "the boy finally acts with it", "ending_type": "cliffhanger",
         "sets": ["home_bedroom", "school", "street"], "cast": ["hero", "brother"],
         "scores": {"hook": 9, "visual": 9, "payoff": 8, "cost": 7, "originality": 8},
         "why_it_hooks": "Everyone has felt too scared to do something."},
        {"premise": "In this town, every lie you tell turns into a tiny bird.",
         "demos": ["a fib about homework", "a white lie to grandma", "a flock at a party"],
         "limit": "birds follow you until you tell the truth", "crisis": "a flock blocks the only bridge",
         "payoff": "the boy confesses and the sky clears", "ending_type": "resolution",
         "sets": ["school", "town_square", "street"], "cast": ["hero", "elder", "crowd"],
         "scores": {"hook": 8, "visual": 9, "payoff": 7, "cost": 6, "originality": 8},
         "why_it_hooks": "Lies you can see are instantly funny and visual."},
        {"premise": "A girl finds out she can pause the world for exactly one breath.",
         "demos": ["catches a falling glass", "fixes a messy room", "wins tag"],
         "limit": "each pause ages her one day", "crisis": "her friend falls into the lake",
         "payoff": "she spends many pauses to swim him out", "ending_type": "resolution",
         "sets": ["home_kitchen", "lake_beach"], "cast": ["hero", "friend"],
         "scores": {"hook": 8, "visual": 8, "payoff": 8, "cost": 8, "originality": 6},
         "why_it_hooks": "Time stop with a cost is instantly clear."},
    ]
}
