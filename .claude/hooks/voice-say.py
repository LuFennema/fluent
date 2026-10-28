#!/usr/bin/env python3
"""
Speak text aloud with the local TTS backend.

Usage:
    python3 voice-say.py --lang Dutch "Goedemiddag! Wat wilt u drinken?"
    echo "text" | python3 voice-say.py --lang nl
    python3 voice-say.py --lang Dutch --rate 0.8 "Langzaam, alsjeblieft."
    python3 voice-say.py --lang Spanish --variety "¿Dónde está la estación?"   # listening drills

Options:
    --lang     target language name or ISO code (default: learner-profile target_language)
    --rate     speed multiplier, 0.5 (slow) .. 1.5 (fast), default 1.0
    --voice    force a voice (OS voice name, Kokoro id like em_alex, Piper id or .onnx),
               or `random` for one of the engine's voices for the language
    --noise    background noise 0..1 mixed into the audio (neural engines only);
               0.1 ≈ quiet café, 0.3 ≈ busy street
    --variety  shorthand for listening practice: random voice + random speed 0.9-1.1
               (+ --noise if given). Use once the learner is comfortable at normal speed.
    --quiet    print nothing on success

Synthesized neural audio is cached in <data_dir>/.voice/cache (FLUENT_TTS_CACHE=0
disables, FLUENT_TTS_CACHE_MB caps the size), so repeated sentences play instantly.

Prints a JSON result. Exit 0 on success, 1 if no backend / playback failed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fluent_paths import data_dir, force_utf8_io  # noqa: E402
from fluent_voice import emit, speak  # noqa: E402


def profile_language() -> str | None:
    try:
        p = json.loads((data_dir() / "learner-profile.json").read_text(encoding="utf-8"))
        return p.get("learner", {}).get("target_language")
    except Exception:
        return None


def main() -> int:
    force_utf8_io()
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="*")
    ap.add_argument("--lang")
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--voice")
    ap.add_argument("--noise", type=float, default=0.0)
    ap.add_argument("--variety", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    text = " ".join(a.text).strip() or sys.stdin.read().strip()
    rate, voice = a.rate, a.voice
    if a.variety:
        import random
        rate = round(a.rate * random.uniform(0.9, 1.1), 2)
        voice = voice or "random"
    res = speak(text, a.lang or profile_language(), rate=rate, voice=voice, noise=a.noise)
    if a.variety and res.get("ok"):
        res["rate"] = rate
    if not (a.quiet and res.get("ok")):
        emit(res)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
