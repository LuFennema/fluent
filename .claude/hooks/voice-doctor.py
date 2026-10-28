#!/usr/bin/env python3
"""
Report which local voice backends are available (TTS, microphone, speech-to-text)
and how to install the missing ones.

Usage:
    python3 voice-doctor.py            # human-readable report
    python3 voice-doctor.py --json     # machine-readable (used by skills)
    python3 voice-doctor.py --test     # also speak a short test sentence
    python3 voice-doctor.py --download-voice --lang Dutch   # pre-fetch the neural voice

Exit 0 when every required component has a backend, 2 when something is missing
(so skills can branch on it without parsing output). Kokoro and Piper are
optional quality upgrades and never affect the exit code.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fluent_paths import force_utf8_io  # noqa: E402
from fluent_voice import (doctor_report, emit, kokoro_available, kokoro_voice_for,  # noqa: E402
                          piper_available, piper_model_path, piper_voice_for, speak,
                          tts_backend)
import fluent_phonemes  # noqa: E402
import fluent_server  # noqa: E402

LABELS = {
    "tts": ("🔊", "Text-to-speech", "listening drills, hearing the tutor"),
    "kokoro": ("🎵", "Kokoro", "best-quality neural voices (optional upgrade)"),
    "piper": ("🎶", "Piper", "neural voices for 40+ languages (optional upgrade)"),
    "microphone": ("🎙️", "Microphone", "pronunciation and spoken conversation"),
    "speech-to-text": ("📝", "Speech-to-text", "understanding what you said"),
    "g2p": ("🔤", "Phonemizer", "target pronunciation in IPA (optional, for phone-level scoring)"),
    "phoneme-recognizer": ("👂", "Phoneme recognizer", "hearing which sounds you actually produced (optional)"),
}
OPTIONAL = ("kokoro", "piper", "g2p", "phoneme-recognizer")


def _profile_language():
    try:
        import json
        from fluent_paths import data_dir
        return json.loads((data_dir() / "learner-profile.json").read_text(encoding="utf-8")) \
            .get("learner", {}).get("target_language")
    except Exception:
        return None


def _kokoro_warmup(lang: str) -> dict:
    """Synthesize one short phrase to trigger the one-time model download."""
    from fluent_voice import kokoro_synthesize, recordings_dir
    lc, kv = kokoro_voice_for(lang)
    out = recordings_dir() / "kokoro-warmup.wav"
    try:
        kokoro_synthesize("Fluent.", lc, kv, out)
        return {"ok": True, "voice": kv}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            out.unlink()
        except Exception:
            pass


def main() -> int:
    force_utf8_io()
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--test", action="store_true", help="speak a test sentence if TTS works")
    ap.add_argument("--lang", default=None)
    ap.add_argument("--download-voice", action="store_true",
                    help="download the Piper voice for --lang (or the profile language) now")
    a = ap.parse_args()

    if a.download_voice:
        lang = a.lang or _profile_language() or "en"
        engine = tts_backend(lang)
        if engine == "kokoro":
            lc, kv = kokoro_voice_for(lang)
            print(f"⬇️  warming up Kokoro ({kv}) — first run downloads the model...")
            res = _kokoro_warmup(lang)
        elif engine == "piper":
            res = piper_model_path(piper_voice_for(lang), lang, download=True)
        else:
            res = {"ok": False, "error": f"no neural engine will be used for '{lang}' "
                                         f"(current engine: {engine}). Install kokoro or piper-tts, "
                                         "or set FLUENT_PIPER_VOICE / FLUENT_KOKORO_VOICE."}
        if a.json:
            emit(res)
        elif res["ok"]:
            print(f"✅ {res.get('voice')} ready" + (f" at {res['model']}" if res.get("model") else "")
                  + ("" if res.get("downloaded", True) else " (already present)"))
        else:
            print(f"❌ {res['error']}")
        return 0 if res["ok"] else 2

    rep = doctor_report()
    ph = fluent_phonemes.doctor()
    rep["checks"].append({"component": "g2p", "backend": ph["g2p"]["backend"], "ok": ph["g2p"]["ok"],
                          "hint": ph["g2p"]["hint"], "alternatives": []})
    rep["checks"].append({"component": "phoneme-recognizer", "backend": ph["recognizer"]["backend"],
                          "ok": ph["recognizer"]["ok"], "hint": ph["recognizer"]["hint"], "alternatives": [],
                          "model": ph["recognizer"]["model"]})
    rep["phoneme_scoring"] = ph["g2p"]["ok"] and ph["recognizer"]["ok"]
    rep["voice_server"] = {"enabled": fluent_server.enabled(), "running": fluent_server.is_running()}
    if a.json:
        emit(rep)
        return 0 if rep["ok"] else 2

    print(f"🌍 Fluent voice check — {rep['platform']}, Python {rep['python']}\n")
    for c in rep["checks"]:
        icon, label, used_for = LABELS.get(c["component"], ("•", c["component"], ""))
        optional = c["component"] in OPTIONAL
        status = f"✅ {c['backend']}" if c["ok"] else ("➖ not installed (optional)" if optional else "❌ not found")
        print(f"{icon} {label:<16} {status}")
        print(f"   used for: {used_for}")
        if c["component"] == "tts" and c["ok"]:
            lang = a.lang or _profile_language()
            if lang:
                eng = tts_backend(lang)
                if eng == "kokoro":
                    print(f"   for {lang}: kokoro voice {kokoro_voice_for(lang)[1]}")
                elif eng == "piper":
                    print(f"   for {lang}: piper voice {piper_voice_for(lang) or os.environ.get('FLUENT_PIPER_VOICE')}")
                else:
                    note = " (no Kokoro/Piper voice for this language)" if (kokoro_available() or piper_available()) else ""
                    print(f"   for {lang}: {eng}{note}")
        if not c["ok"]:
            print(f"   {'optional upgrade' if optional else 'how to fix'}: {c['hint']}")
            if c["alternatives"]:
                print("   alternatives: " + " | ".join(c["alternatives"]))
        print()

    print("🧪 Phone-level pronunciation scoring: " + ("✅ available" if rep["phoneme_scoring"] else
          "➖ off (word-level only) — needs the phonemizer and the phoneme recognizer above"))
    vs = rep["voice_server"]
    print("⚡ Voice server: " + ("running — models stay loaded between sentences" if vs["running"] else
          ("not running — starts automatically on first neural use (`voice-server.py start` to pre-warm)"
           if vs["enabled"] else "disabled (FLUENT_VOICE_SERVER=0)")) + "\n")
    if rep["env"]:
        print("Environment overrides: " + ", ".join(f"{k}={v}" for k, v in rep["env"].items()) + "\n")

    if rep["ok"]:
        print("Everything is ready: /fluent-listening, /fluent-pronunciation and "
              "/fluent-speaking voice all work on this machine.")
        if not (kokoro_available() or piper_available()):
            print("Tip: `pip install kokoro soundfile` (or `piper-tts`) for much more natural voices — still local.")
    else:
        missing = [c["component"] for c in rep["checks"]
                   if not c["ok"] and c["component"] not in OPTIONAL]
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
        res = speak("Fluent voice is working.", a.lang or "en")
        print("   " + ("✅ ok" if res.get("ok") else f"❌ {res.get('error')}"))

    return 0 if rep["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
