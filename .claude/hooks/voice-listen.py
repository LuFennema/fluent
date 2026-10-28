#!/usr/bin/env python3
"""
Record from the microphone and transcribe it locally (speech-to-text).

Usage:
    python3 voice-listen.py --lang Dutch
    python3 voice-listen.py --lang nl --max-seconds 15
    python3 voice-listen.py --lang Dutch --expect "Ik wil graag een koffie."
    python3 voice-listen.py --file /path/to/recording.wav --lang Dutch

Options:
    --lang          target language name or ISO code (default: learner-profile target_language)
    --max-seconds   stop recording after this many seconds (default 20)
    --silence       seconds of silence that end the recording early (default 1.5;
                    only the sounddevice backend supports early stop)
    --expect        the sentence the learner was asked to say; adds a word-level
                    similarity score (0-100) and the missed / misheard words
    --file          transcribe an existing WAV instead of recording
    --keep          keep the WAV file (default: deleted after transcription)
    --countdown     seconds to wait (printing a countdown to stderr) before recording

Prints a JSON result:
    {
      "ok": true,
      "recording": {"backend": "sounddevice", "seconds": 3.4},
      "transcript": "ik wil graag een koffie",
      "confidence": 0.91,
      "stt_backend": "faster-whisper",
      "score": {"similarity": 100, "missed": [], "heard_instead": []}
    }

Exit 0 on success, 1 if recording or transcription failed (the JSON carries
the error and a hint to run voice-doctor.py).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fluent_paths import data_dir, force_utf8_io  # noqa: E402
from fluent_voice import emit, record, score_against, transcribe  # noqa: E402


def profile_language() -> str | None:
    try:
        p = json.loads((data_dir() / "learner-profile.json").read_text(encoding="utf-8"))
        return p.get("learner", {}).get("target_language")
    except Exception:
        return None


def main() -> int:
    force_utf8_io()
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang")
    ap.add_argument("--max-seconds", type=float, default=20.0)
    ap.add_argument("--silence", type=float, default=1.5)
    ap.add_argument("--expect")
    ap.add_argument("--file")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--countdown", type=int, default=0)
    a = ap.parse_args()

    lang = a.lang or profile_language()
    result: dict = {"ok": False}

    if a.file:
        audio = Path(a.file)
        if not audio.exists():
            emit({"ok": False, "error": f"file not found: {audio}"})
            return 1
        result["recording"] = {"backend": "file", "file": str(audio)}
        keep = True
    else:
        for n in range(a.countdown, 0, -1):
            sys.stderr.write(f"🎙️  recording in {n}...\n")
            sys.stderr.flush()
            time.sleep(1)
        sys.stderr.write("🎙️  speak now\n")
        sys.stderr.flush()
        rec = record(max_seconds=a.max_seconds, silence_seconds=a.silence)
        if not rec.get("ok"):
            rec["hint"] = "run voice-doctor.py to see which microphone backends are available"
            emit(rec)
            return 1
        audio = Path(rec["file"])
        result["recording"] = {k: rec[k] for k in ("backend", "seconds") if k in rec}
        keep = a.keep

    stt = transcribe(audio, lang)
    if not keep:
        try:
            audio.unlink()
        except Exception:
            pass
    else:
        result["recording"]["file"] = str(audio)

    if not stt.get("ok"):
        stt["hint"] = "run voice-doctor.py to see how to install a speech-to-text backend"
        result.update(stt)
        emit(result)
        return 1

    result.update({
        "ok": True,
        "language": stt.get("language"),
        "transcript": stt.get("transcript", ""),
        "confidence": stt.get("confidence"),
        "stt_backend": stt.get("backend"),
        "stt_seconds": stt.get("seconds"),
    })
    if a.expect:
        result["expected"] = a.expect
        result["score"] = score_against(a.expect, result["transcript"])
    emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
