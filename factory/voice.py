"""Voice: ElevenLabs TTS with character timestamps (+ an offline mock for testing)."""
from __future__ import annotations

import base64
import json
import math
import struct
import time
import wave
from pathlib import Path

import requests

from .config import require_env

BASE = "https://api.elevenlabs.io"


def _headers() -> dict:
    return {"xi-api-key": require_env("ELEVENLABS_API_KEY"), "Content-Type": "application/json"}


def _post(url: str, body: dict, params: dict | None = None, retries: int = 3) -> requests.Response:
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, headers=_headers(), json=body, params=params, timeout=180)
        except requests.RequestException as e:
            last = e
        else:
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503, 504):
                last = RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            else:
                raise RuntimeError(f"ElevenLabs HTTP {r.status_code}: {r.text[:800]}")
        time.sleep(2 ** attempt * 2)
    raise RuntimeError(f"ElevenLabs a esuat: {last}")


def tts_with_timestamps(text: str, cfg: dict, out_audio: Path) -> dict:
    """Generate speech + character alignment. Returns the alignment dict."""
    v = cfg["voice"]
    if v["voice_id"].startswith("PUT_"):
        raise SystemExit("Seteaza voice.voice_id in config.yaml (vezi: python run.py voices).")
    body = {"text": text, "model_id": v["model_id"], "voice_settings": v["settings"]}
    if v.get("seed") is not None:
        body["seed"] = v["seed"]
    url = f"{BASE}/v1/text-to-speech/{v['voice_id']}/with-timestamps"
    data = _post(url, body, params={"output_format": v["output_format"]}).json()
    out_audio.write_bytes(base64.b64decode(data["audio_base64"]))
    alignment = data.get("alignment") or data.get("normalized_alignment")
    if not alignment:
        raise RuntimeError("ElevenLabs nu a returnat alignment.")
    return alignment


def list_voices() -> list[dict]:
    r = requests.get(f"{BASE}/v1/voices", headers=_headers(), timeout=60)
    r.raise_for_status()
    return [{"voice_id": x["voice_id"], "name": x.get("name"), "labels": x.get("labels", {})}
            for x in r.json().get("voices", [])]


def list_models() -> list[dict]:
    r = requests.get(f"{BASE}/v1/models", headers=_headers(), timeout=60)
    r.raise_for_status()
    return [{"model_id": m["model_id"], "name": m.get("name"), "tts": m.get("can_do_text_to_speech")}
            for m in r.json()]


def generate_sfx(prompt: str, out_path: Path, duration: float | None = None) -> None:
    """Create one sound effect from a text prompt (ElevenLabs /v1/sound-generation)."""
    body = {"text": prompt, "prompt_influence": 0.5}
    if duration:
        body["duration_seconds"] = max(0.5, min(30.0, duration))
    r = _post(f"{BASE}/v1/sound-generation", body, params={"output_format": "mp3_44100_128"})
    out_path.write_bytes(r.content)


SFX_PROMPTS = {
    "whoosh": ("fast cartoon whoosh, clean, no music", 1.0),
    "impact": ("punchy cartoon impact thud, short", 0.8),
    "pop": ("soft bubbly cartoon pop", 0.5),
    "magic": ("short sparkling magic shimmer, whimsical", 1.5),
    "rumble": ("low deep rumble, building tension", 2.0),
    "thunder": ("loud thunder crack with rain", 3.0),
    "rain": ("steady rain ambience", 4.0),
    "splash": ("water splash, cartoon", 1.0),
    "door": ("wooden door opening and closing", 1.5),
    "footsteps": ("quick footsteps running on wood", 1.5),
    "gasp": ("crowd gasp, surprised, short", 1.2),
    "heartbeat": ("slow heavy heartbeat, two beats", 1.5),
    "glass": ("glass breaking, short", 1.0),
    "wind": ("strong howling wind gust", 2.5),
    "bell": ("single bright bell ding", 1.2),
    "swoosh_up": ("rising swoosh riser, short", 1.2),
    "slam": ("heavy slam, cartoon", 0.8),
    "creak": ("old wooden creak", 1.2),
}


# ----------------------------------------------------------------- mock voice
def mock_tts(text: str, out_wav: Path, sr: int = 44100) -> dict:
    """Offline stand-in: a soft tone per word + a fake character alignment.

    Lets you test the whole pipeline (captions, mix, animatic, QA) without any API.
    """
    chars, starts, ends = [], [], []
    t = 0.15
    frames = []
    words = text.split()
    for wi, word in enumerate(words):
        dur = 0.10 + 0.042 * len(word)  # ~2.8 words/s, close to a real narrator
        per_char = dur / len(word)
        for k, ch in enumerate(word):
            chars.append(ch)
            starts.append(round(t + k * per_char, 3))
            ends.append(round(t + (k + 1) * per_char, 3))
        # tone for this word
        n = int(dur * sr)
        freq = 180 + (wi % 5) * 25
        for i in range(n):
            env = math.sin(math.pi * i / n)
            frames.append(int(6000 * env * math.sin(2 * math.pi * freq * i / sr)))
        t += dur
        gap = 0.05 if not word.endswith((",", ".")) else 0.18
        frames.extend([0] * int(gap * sr))
        if wi < len(words) - 1:
            chars.append(" ")
            starts.append(round(t, 3))
            ends.append(round(t + gap, 3))
        t += gap
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", f) for f in frames))
    return {"characters": chars, "character_start_times_seconds": starts,
            "character_end_times_seconds": ends}


def scale_alignment(alignment: dict, tempo: float) -> dict:
    """After speeding audio up by `tempo`, every timestamp shrinks by the same factor."""
    return {
        "characters": alignment["characters"],
        "character_start_times_seconds": [round(t / tempo, 4) for t in alignment["character_start_times_seconds"]],
        "character_end_times_seconds": [round(t / tempo, 4) for t in alignment["character_end_times_seconds"]],
    }


def save_alignment(alignment: dict, path: Path) -> None:
    path.write_text(json.dumps(alignment), encoding="utf-8")
