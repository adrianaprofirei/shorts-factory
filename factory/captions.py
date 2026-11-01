"""Captions as an .ass subtitle file (rendered by ffmpeg/libass)."""
from __future__ import annotations

import re
from pathlib import Path


def ass_color(hex_rgb: str, alpha: int = 0) -> str:
    """'#RRGGBB' -> '&HAABBGGRR' (ASS uses BGR + alpha, 00 = opaque)."""
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_inline_color(hex_rgb: str) -> str:
    h = hex_rgb.lstrip("#")
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def clean_caption_word(word: str, cfg: dict) -> str:
    c = cfg["captions"]
    w = word.replace("{", "").replace("}", "").replace("\\", "")
    if c.get("strip_punctuation", True):
        w = re.sub(r"[^\w'\u00C0-\u024F-]", "", w)
    if c.get("lowercase", True):
        w = w.lower()
    return w


def build_ass(chunks: list[dict], cfg: dict, out_path: Path,
              shot_labels: list[dict] | None = None) -> None:
    """Write the .ass file.

    shot_labels (animatic only): [{'start','end','text'}] drawn small at the top-left.
    """
    c, v = cfg["captions"], cfg["video"]
    W, H = v["width"], v["height"]
    margin_v = int(H * c["position_y_ratio"])
    primary = ass_color(c["primary_color"])
    outline = ass_color(c["outline_color"])
    shadow = ass_color("#000000", alpha=0x60)
    font = c["font_name"]

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{c['font_size']},{primary},{primary},{outline},{shadow},-1,0,0,0,100,100,0,0,1,{c['outline']},{c['shadow']},8,80,80,{margin_v},1
Style: ShotInfo,{font},34,{ass_color('#FFFFFF')},{ass_color('#FFFFFF')},{ass_color('#000000')},{ass_color('#000000', 0x40)},-1,0,0,0,100,100,0,0,3,2,0,7,40,40,60,1
Style: Watermark,{font},40,{ass_color('#FFFFFF', 0xA0)},{ass_color('#FFFFFF', 0xA0)},{ass_color('#000000', 0xC0)},{ass_color('#000000', 0xFF)},-1,0,0,0,100,100,0,0,1,1,0,2,40,40,{int(H * 0.30)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    red = ass_inline_color(c["emphasis_color"])
    pop = r"{\fscx82\fscy82\t(0,90,\fscx100\fscy100)}" if c.get("pop_in", True) else ""
    lines = []
    for ch in chunks:
        parts = []
        for w in ch["words"]:
            word = clean_caption_word(w["text"], cfg)
            if not word:
                continue
            if w["emphasis"]:
                parts.append(f"{{\\c{red}}}{word}{{\\c{ass_inline_color(c['primary_color'])}}}")
            else:
                parts.append(word)
        if not parts:
            continue
        text = pop + " ".join(parts)
        lines.append(f"Dialogue: 1,{ts(ch['start'])},{ts(ch['end'])},Caption,,0,0,0,,{text}")

    if shot_labels:
        for s in shot_labels:
            label = s["text"].replace("{", "(").replace("}", ")").replace("\\", "/").replace("\n", "\\N")
            lines.append(f"Dialogue: 0,{ts(s['start'])},{ts(s['end'])},ShotInfo,,0,0,0,,{label}")

    if v.get("watermark") and cfg["channel"].get("handle"):
        end = max((ch["end"] for ch in chunks), default=1.0)
        lines.append(f"Dialogue: 0,{ts(0)},{ts(end + 1)},Watermark,,0,0,0,,{cfg['channel']['handle']}")

    out_path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
