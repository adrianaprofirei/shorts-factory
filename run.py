#!/usr/bin/env python3
"""Shorts Factory - comenzi:

  python run.py ideas [--n 15] [--theme "..."]          idei noi de premise
  python run.py new --premise "..."                    script + voce + mix + fisa de job + animatic
  python run.py new --ideas FISIER.json --pick 1       la fel, pornind de la o idee generata
  python run.py prep SLUG                               refa voce/mix/fisa/animatic dupa ce editezi script.json
  python run.py final SLUG [--render cale.mp4]          asamblare finala dupa ce vine animatia + QA
  python run.py voices | models                         listeaza vocile / modelele ElevenLabs
  python run.py sfx-pack                                genereaza efectele sonore care lipsesc (ElevenLabs)
  python run.py selftest                                test complet fara API (verifica instalarea)

Adauga --mock la ideas/new/prep ca sa rulezi fara chei API.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from factory import audio, captions, jobcard, qa, story, timing, video, voice
from factory.config import PROJECTS, load_config, load_env, project_dir, slugify
from factory.ff import check_tools, duration, run


def _save(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ ideas
def cmd_ideas(args, cfg):
    n = args.n or cfg["llm"]["ideas_per_batch"]
    print(f"Generez {n} idei...")
    data = story.generate_ideas(cfg, n, args.theme, args.mock)
    PROJECTS.mkdir(exist_ok=True)
    out = PROJECTS / f"ideas_{datetime.now():%Y%m%d_%H%M%S}.json"
    _save(out, data)
    for i, idea in enumerate(data.get("ideas", []), 1):
        sc = idea.get("scores", {})
        print(f"\n{i:2d}. {idea['premise']}  [total {sum(sc.values())}]")
        print(f"    cost: {idea.get('limit')} | criza: {idea.get('crisis')} | final: {idea.get('ending_type')}")
    print(f"\nSalvat in {out}\nUrmatorul pas: python run.py new --ideas {out} --pick <numar>")


# -------------------------------------------------------------- pipeline
def prep(slug: str, cfg: dict, mock: bool) -> None:
    """Voice -> timing -> mix -> captions -> job card -> animatic."""
    check_tools()
    d = project_dir(slug)
    script = _load(d / "script.json")
    errs_now, warns_now = story.validate_script(script, cfg)
    script["_validation"] = {"errors": errs_now, "warnings": warns_now, "words": story.word_count(script)}
    _save(d / "script.json", script)
    if errs_now:
        print("Scriptul are erori; corecteaza script.json si ruleaza din nou 'prep':")
        for e in errs_now:
            print("  -", e)
        sys.exit(1)

    text = story.full_narration(script)
    print("  voce...")
    if mock:
        alignment = voice.mock_tts(text, d / "voice.wav")
        voice_file = d / "voice.wav"
    else:
        voice_file = d / "voice.mp3"
        alignment = voice.tts_cached(text, cfg, voice_file)
    tempo = float(cfg["voice"].get("tempo", 1.0) or 1.0)
    if abs(tempo - 1.0) > 0.001:
        fast = d / "voice_tempo.wav"
        run(["ffmpeg", "-y", "-hide_banner", "-i", str(voice_file), "-af", f"atempo={tempo}",
             "-ar", str(cfg["audio"]["sample_rate"]), str(fast)])
        alignment = voice.scale_alignment(alignment, tempo)
        voice_file = fast
    max_pause = float(cfg["voice"].get("max_pause", 0) or 0)
    if max_pause > 0:
        trimmed = d / "voice_trimmed.wav"
        alignment, cut = audio.cap_pauses(voice_file, alignment, max_pause, cfg["audio"]["sample_rate"], trimmed)
        print(f"  pauze scurtate la max {max_pause:.2f}s: -{cut:.2f}s")
        voice_file = trimmed
    voice.save_alignment(alignment, d / "alignment.json")

    voice_dur = duration(voice_file)
    words = timing.assign_beats(script, timing.alignment_to_words(alignment))
    print("  mix audio...")
    cues = timing.sfx_cues(script, words)
    music = audio.pick_music(script["music_mood"], slug)
    report = audio.mix(voice_file, cues, cfg, d / "master.wav", music, d)
    total = duration(d / "master.wav")

    timings = timing.beat_timings(script, words, total)
    chunks = timing.caption_chunks(script, words, cfg, voice_dur)
    _save(d / "words.json", words)
    _save(d / "timings.json", timings)
    _save(d / "captions.json", chunks)
    _save(d / "sfx_cues.json", cues)
    _save(d / "mix_report.json", report)

    print("  subtitrari + fisa de job + animatic...")
    captions.build_ass(chunks, cfg, d / "captions.ass")
    shots = jobcard.build_shots(script, timings, chunks)
    labels = [{"start": s["start"], "end": s["end"],
               "text": f"#{s['shot']}  {s['set']} / {s['lighting']}\n{s['camera']}  ·  {s['expression']}\n{s['action']}"}
              for s in shots]
    captions.build_ass(chunks, cfg, d / "animatic.ass", shot_labels=labels)
    jobcard.write_job_card(script, shots, cfg, d, slug, total)
    video.build_animatic(d, shots, cfg, "animatic.ass", "master.wav", total)

    print(f"\nGata: {d}")
    wps = len(words) / max(0.1, voice_dur)
    print(f"  durata: {total:.2f}s · {len(shots)} cadre · {wps:.2f} cuvinte/s · loudness {report['lufs']:.1f} LUFS")
    if not report["music"]:
        print(f"  atentie: nu am gasit muzica in assets/music/{script['music_mood']}/ (mix fara muzica)")
    if report["sfx_missing"]:
        print(f"  atentie: lipsesc efectele {sorted(set(report['sfx_missing']))} (python run.py sfx-pack)")
    for w in warns_now:
        print("  atentie:", w)
    print("  Trimite animatorului: job_card.md, master.wav, animatic.mp4, shots.csv")


def cmd_new(args, cfg):
    if args.ideas:
        ideas = _load(Path(args.ideas))["ideas"]
        premise = ideas[args.pick - 1]
        premise_text = premise["premise"]
    elif args.premise:
        premise = premise_text = args.premise
    elif args.mock:
        premise = premise_text = story.MOCK_SCRIPT["premise"]
    else:
        sys.exit("Da --premise \"...\" sau --ideas FISIER --pick N")
    slug = f"{datetime.now():%Y%m%d}-{slugify(premise_text, 40)}"
    if args.mock:
        slug += "-mock"
    d = project_dir(slug)
    print(f"Proiect: {slug}")
    script = story.build_script(cfg, premise, d, args.mock)
    v = script["_validation"]
    print(f"  {v['words']} cuvinte · {len(script['beats'])} beats · titlu: {script['title']}")
    if v["errors"]:
        print("  Scriptul inca are erori; editeaza script.json apoi: python run.py prep", slug)
        for e in v["errors"]:
            print("   -", e)
        return
    if not args.mock:
        story.add_to_history(script["premise"], slug)
    if args.script_only:
        print(f"Citeste {d / 'script.md'}; cand e aprobat: python run.py prep {slug}")
        return
    prep(slug, cfg, args.mock)


def cmd_prep(args, cfg):
    prep(args.slug, cfg, args.mock)


def cmd_final(args, cfg):
    check_tools()
    d = project_dir(args.slug)
    script = _load(d / "script.json")
    render = Path(args.render) if args.render else d / "render.mp4"
    if not render.exists():
        sys.exit(f"Nu gasesc animatia: {render}. Pune fisierul de la animator ca {d / 'render.mp4'}.")
    if render.resolve() != (d / "render.mp4").resolve():
        shutil.copy2(render, d / "render.mp4")
    total = duration(d / "master.wav")
    issues = qa.check_render(d / "render.mp4", total, cfg)
    for i in issues:
        print("  render:", i)

    chunks = _load(d / "captions.json")
    captions.build_ass(chunks, cfg, d / "captions.ass")
    windows = timing.emphasis_windows(chunks)
    print("  asamblez video-ul final...")
    video.build_final(d, "render.mp4", "master.wav", "captions.ass", cfg, total, windows)
    report = qa.check_final(d / "final.mp4", total, script, cfg)
    report["render_issues"] = issues
    _save(d / "qa_report.json", report)
    write_upload_sheet(d, script)
    print(f"\nQA: {'OK' if report['ok'] else 'PROBLEME'} · {report['duration']}s · {report['lufs']} LUFS")
    for e in report["errors"]:
        print("  EROARE:", e)
    for w in report["warnings"]:
        print("  atentie:", w)
    print(f"Video: {d / 'final.mp4'}\nTitlu, descriere, comentariu: {d / 'upload.txt'}")


def write_upload_sheet(d: Path, script: dict) -> None:
    body = [
        "=== YOUTUBE SHORTS ===",
        f"Titlu: {script['title']}",
        "Descriere:",
        script["description"],
        "",
        f"Comentariu fixat: {script['pinned_comment']}",
        "Setari: Public · Audienta (made for kids sau nu): decizia ta, dupa publicul real (vezi planul) · "
        "Altered/synthetic content: NU (animatie evident fictiva)",
        "",
        "=== TIKTOK ===",
        f"{script['title']} #roblox #animation #story #fyp",
        "",
        "=== INSTAGRAM / FACEBOOK REELS ===",
        f"{script['title']}\n\n{script['pinned_comment']}\n\n#roblox #robloxanimation #animation #story",
    ]
    (d / "upload.txt").write_text("\n".join(body) + "\n", encoding="utf-8")


# ----------------------------------------------------------------- extras
def cmd_voices(args, cfg):
    for v in voice.list_voices():
        print(f"{v['voice_id']}  {v['name']}  {v['labels']}")


def cmd_models(args, cfg):
    for m in voice.list_models():
        if m["tts"]:
            print(f"{m['model_id']}  ({m['name']})")


def cmd_sfx_pack(args, cfg):
    from factory.config import ASSETS
    (ASSETS / "sfx").mkdir(parents=True, exist_ok=True)
    for tag in cfg["library"]["sfx_tags"]:
        if audio.find_sfx(tag):
            continue
        prompt, dur = voice.SFX_PROMPTS.get(tag, (tag.replace("_", " "), 1.5))
        print(f"  generez {tag}...")
        voice.generate_sfx(prompt, ASSETS / "sfx" / f"{tag}.mp3", dur)
    print("Efectele sunt in assets/sfx/. Asculta-le si inlocuieste ce nu-ti place.")


def cmd_selftest(args, cfg):
    """End-to-end test with no API: mock script + mock voice + fake 'animator render'."""
    check_tools()
    print("== selftest: pipeline complet fara API ==")
    ns = argparse.Namespace(ideas=None, premise=None, pick=1, mock=True, script_only=False)
    cmd_new(ns, cfg)
    slug = sorted(p.name for p in PROJECTS.iterdir() if p.is_dir() and p.name.endswith("-mock"))[-1]
    d = PROJECTS / slug
    # fake animator delivery: a moving test pattern at 24 fps and 720x1280 (wrong on purpose,
    # so the test also proves that size/fps get fixed automatically)
    total = duration(d / "master.wav")
    run(["ffmpeg", "-y", "-hide_banner", "-f", "lavfi", "-i", f"testsrc2=s=720x1280:r=24:d={total:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p", "fake_render.mp4"], cwd=d)
    cmd_final(argparse.Namespace(slug=slug, render=str(d / "fake_render.mp4")), cfg)
    rep = _load(d / "qa_report.json")
    print("\nSELFTEST", "TRECUT" if rep["ok"] else "PICAT")
    sys.exit(0 if rep["ok"] else 1)


def main():
    load_env()
    cfg = load_config()
    p = argparse.ArgumentParser(description="Shorts Factory")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ideas"); s.add_argument("--n", type=int); s.add_argument("--theme")
    s.add_argument("--mock", action="store_true"); s.set_defaults(fn=cmd_ideas)

    s = sub.add_parser("new"); s.add_argument("--premise"); s.add_argument("--ideas")
    s.add_argument("--pick", type=int, default=1); s.add_argument("--mock", action="store_true")
    s.add_argument("--script-only", action="store_true", help="doar scriptul, fara voce/animatic")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("prep"); s.add_argument("slug"); s.add_argument("--mock", action="store_true")
    s.set_defaults(fn=cmd_prep)

    s = sub.add_parser("final"); s.add_argument("slug"); s.add_argument("--render")
    s.set_defaults(fn=cmd_final)

    for name, fn in (("voices", cmd_voices), ("models", cmd_models), ("sfx-pack", cmd_sfx_pack),
                     ("selftest", cmd_selftest)):
        sub.add_parser(name).set_defaults(fn=fn)

    args = p.parse_args()
    args.fn(args, cfg)


if __name__ == "__main__":
    main()
