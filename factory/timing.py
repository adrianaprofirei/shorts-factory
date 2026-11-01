"""Timing: character alignment -> words -> beats/shots -> caption chunks -> SFX cues."""
from __future__ import annotations

from .story import clean_token


def alignment_to_words(alignment: dict) -> list[dict]:
    """Group characters into whitespace-separated words with start/end times."""
    chars = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    words, cur, cur_start, cur_end = [], "", None, None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append({"text": cur, "start": cur_start, "end": cur_end})
                cur, cur_start = "", None
            continue
        if not cur:
            cur_start = s
        cur += ch
        cur_end = e
    if cur:
        words.append({"text": cur, "start": cur_start, "end": cur_end})
    return words


def assign_beats(script: dict, words: list[dict]) -> list[dict]:
    """Attach each spoken word to its beat. Returns words with a 'beat' index.

    Normal case: the word counts match exactly. If the TTS normalised something
    (e.g. a number), fall back to a proportional mapping so nothing breaks.
    """
    counts = [len(b["narration"].split()) for b in script["beats"]]
    total = sum(counts)
    out = []
    if total == len(words):
        idx = 0
        for bi, c in enumerate(counts):
            for _ in range(c):
                out.append({**words[idx], "beat": bi})
                idx += 1
        return out
    # proportional fallback
    bounds, acc = [], 0
    for c in counts:
        acc += c
        bounds.append(acc / total)
    for wi, w in enumerate(words):
        pos = (wi + 0.5) / len(words)
        bi = next(i for i, b in enumerate(bounds) if pos <= b + 1e-9)
        out.append({**w, "beat": bi})
    return out


def beat_timings(script: dict, words: list[dict], audio_duration: float) -> list[dict]:
    """Shot i lasts from the first word of beat i to the first word of beat i+1."""
    n = len(script["beats"])
    first = {}
    for w in words:
        first.setdefault(w["beat"], w["start"])
    timings = []
    for i in range(n):
        if i == 0:
            start = 0.0
        else:
            # a beat with no matched words (rare) starts where the previous one started
            start = first.get(i, timings[-1]["start"])
        timings.append({"beat": i, "start": round(start, 3)})
    for i in range(n):
        end = timings[i + 1]["start"] if i + 1 < n else audio_duration
        timings[i]["end"] = round(end, 3)
        timings[i]["duration"] = round(end - timings[i]["start"], 3)
    return timings


WEAK_ENDINGS = {"a", "an", "the", "his", "her", "its", "their", "my", "your", "to", "of", "in", "on",
                "at", "for", "with", "and", "but", "or", "is", "are", "was", "into", "from", "by",
                "every", "each", "that", "this", "than", "as", "it"}


def _segments(beat_ws: list[dict]) -> list[list[dict]]:
    """Split one beat's words at punctuation (commas, full stops...)."""
    segs, cur = [], []
    for w in beat_ws:
        cur.append(w)
        if w["text"].endswith((",", ".", "!", "?", ";", ":")):
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    return segs


def _chars(ws: list[dict]) -> int:
    return sum(len(w["text"]) for w in ws) + max(0, len(ws) - 1)


def _balanced(seg: list[dict], max_words: int, max_chars: int) -> list[list[dict]]:
    """Split a phrase into evenly sized captions (5 words -> 3+2, 8 -> 4+4),
    never ending a caption on a weak word like 'the' or 'his' when avoidable."""
    m = len(seg)
    k = max(1, -(-m // max_words))
    while True:
        base, extra = divmod(m, k)
        sizes = [base + (1 if i < extra else 0) for i in range(k)]
        parts, i = [], 0
        for s in sizes:
            parts.append(seg[i:i + s])
            i += s
        # move weak trailing words to the next caption
        for j in range(len(parts) - 1):
            while (len(parts[j]) > 1 and len(parts[j + 1]) < max_words
                   and clean_token(parts[j][-1]["text"]) in WEAK_ENDINGS):
                parts[j + 1].insert(0, parts[j].pop())
        if all(_chars(p) <= max_chars or len(p) == 1 for p in parts) or k >= m:
            return [p for p in parts if p]
        k += 1


def caption_chunks(script: dict, words: list[dict], cfg: dict, audio_duration: float) -> list[dict]:
    """Split spoken words into on-screen captions (2-4 words, never across beats)."""
    c = cfg["captions"]
    max_words, max_chars = c["max_words"], c["max_chars"]
    chunks = []
    beats_in_order = []
    for w in words:
        if not beats_in_order or beats_in_order[-1][0]["beat"] != w["beat"]:
            beats_in_order.append([])
        beats_in_order[-1].append(w)
    for beat_ws in beats_in_order:
        for seg in _segments(beat_ws):
            chunks.extend(_balanced(seg, max_words, max_chars))

    emphasised_beats = set()
    out = []
    for i, ch in enumerate(chunks):
        beat = script["beats"][ch[0]["beat"]]
        emph = clean_token(beat.get("emphasis") or "")
        start = ch[0]["start"]
        end = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else min(audio_duration, ch[-1]["end"] + 0.4)
        end = max(end, start + c["min_duration"]) if i + 1 == len(chunks) else end
        items = []
        for w in ch:
            is_emph = bool(emph) and clean_token(w["text"]) == emph and ch[0]["beat"] not in emphasised_beats
            if is_emph:
                emphasised_beats.add(ch[0]["beat"])
            items.append({"text": w["text"], "emphasis": is_emph})
        out.append({"start": round(start, 3), "end": round(end, 3), "words": items,
                    "beat": ch[0]["beat"]})
    return out


def sfx_cues(script: dict, words: list[dict]) -> list[dict]:
    cues = []
    for bi, beat in enumerate(script["beats"]):
        beat_ws = [w for w in words if w["beat"] == bi]
        for fx in beat.get("sfx") or []:
            target = clean_token(fx.get("at_word", ""))
            hit = next((w for w in beat_ws if clean_token(w["text"]) == target), None)
            if hit is None and beat_ws:
                hit = beat_ws[0]
            if hit is not None:
                cues.append({"tag": fx["tag"], "time": round(hit["start"], 3), "beat": bi})
    return cues


def emphasis_windows(chunks: list[dict]) -> list[tuple[float, float]]:
    """Time windows of captions that contain a red word (used for punch-in zooms)."""
    return [(ch["start"], ch["end"]) for ch in chunks if any(w["emphasis"] for w in ch["words"])]
