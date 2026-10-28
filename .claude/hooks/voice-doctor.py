#!/usr/bin/env python3
"""
Report which local voice backends are available (TTS, microphone, speech-to-text)
and how to install the missing ones.

Usage:
    python3 voice-doctor.py            # human-readable report
    python3 voice-doctor.py --json     # machine-readable (used by skills)
    python3 voice-doctor.py --test     # also speak a short test sentence

Exit 0 when every component has a backend, 2 when something is missing
(so skills can branch on it without parsing output).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fluent_paths import force_utf8_io  # noqa: E402
from fluent_voice import doctor_report, emit, speak  # noqa: E402

LABELS = {
    "tts": ("🔊", "Text-to-speech", "listening drills, hearing the tutor"),
    "microphone": ("🎙️", "Microphone", "pronunciation and spoken conversation"),
    "speech-to-text": ("📝", "Speech-to-text", "understanding what you said"),
}


def main() -> int:
    force_utf8_io()
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--test", action="store_true", help="speak a test sentence if TTS works")
    ap.add_argument("--lang", default="en")
    a = ap.parse_args()

    rep = doctor_report()
    if a.json:
        emit(rep)
        return 0 if rep["ok"] else 2

    print(f"🌍 Fluent voice check — {rep['platform']}, Python {rep['python']}\n")
    for c in rep["checks"]:
        icon, label, used_for = LABELS.get(c["component"], ("•", c["component"], ""))
        status = f"✅ {c['backend']}" if c["ok"] else "❌ not found"
        print(f"{icon} {label:<16} {status}")
        print(f"   used for: {used_for}")
        if not c["ok"]:
            print(f"   how to fix: {c['hint']}")
            if c["alternatives"]:
                print("   alternatives: " + " | ".join(c["alternatives"]))
        print()

    if rep["env"]:
        print("Environment overrides: " + ", ".join(f"{k}={v}" for k, v in rep["env"].items()) + "\n")

    if rep["ok"]:
        print("Everything is ready: /fluent-listening, /fluent-pronunciation and "
              "/fluent-speaking voice all work on this machine.")
    else:
        missing = [c["component"] for c in rep["checks"] if not c["ok"]]
        have_tts = any(c["component"] == "tts" and c["ok"] for c in rep["checks"])
        print("Missing: " + ", ".join(missing) + ".")
        if have_tts:
            print("/fluent-listening works now (needs only text-to-speech). "
                  "Install a microphone + speech-to-text backend for /fluent-pronunciation "
                  "and /fluent-speaking voice.")
        else:
            print("Typed practice (/fluent-learn, /fluent-vocab, /fluent-writing, ...) "
                  "is unaffected.")

    if a.test and any(c["component"] == "tts" and c["ok"] for c in rep["checks"]):
        print("\n🔊 Speaking a test sentence...")
        res = speak("Fluent voice is working.", a.lang)
        print("   " + ("✅ ok" if res.get("ok") else f"❌ {res.get('error')}"))

    return 0 if rep["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
