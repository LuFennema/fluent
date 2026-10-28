---
name: fluent-voice-setup
description: Check and set up the local audio stack Fluent uses for listening, pronunciation and spoken conversation — text-to-speech, microphone and speech-to-text (Whisper). Runs voice-doctor.py, explains what is missing and how to install it for the learner's OS, and plays a test sentence. Use when the learner asks whether audio/voice works, wants to set up the microphone or speech recognition, or any voice skill reports a missing backend.
allowed-tools: Read, Bash
---

# Voice Setup & Diagnostics

## Overview

Fluent's audio features run **entirely on the learner's machine** — no API keys, no cloud speech services. Three components, each with several interchangeable backends:

| Component | Used by | Backends (first found wins) |
|-----------|---------|-----------------------------|
| 🔊 Text-to-speech | `/fluent-listening`, voice replies in `/fluent-speaking voice`, model pronunciation in `/fluent-pronunciation` | **Kokoro** (pip, best quality, 9 languages) → **Piper** (pip, good, 40+ languages) → OS engine: macOS `say` · `espeak-ng` / `espeak` / `spd-say` (Linux) · PowerShell SAPI (Windows) · `pyttsx3` · `$FLUENT_TTS_CMD` |
| 🎙️ Microphone | `/fluent-pronunciation`, `/fluent-speaking voice` | `sounddevice`+`numpy` (pip, silence-aware) · `ffmpeg` · `sox` (`rec`) · `arecord` |
| 📝 Speech-to-text | `/fluent-pronunciation`, `/fluent-speaking voice` | `faster-whisper` (pip, recommended) · `openai-whisper` · whisper.cpp (`FLUENT_WHISPER_CPP_MODEL`) · `$FLUENT_STT_CMD` |

Everything lives in `.claude/hooks/fluent_voice.py` with three CLIs next to it: `voice-say.py`, `voice-listen.py`, `voice-doctor.py`.

## When to Use

- Learner asks "does voice/audio work?", "how do I set up the microphone?", "can you hear me?"
- A voice skill got `{"ok": false, "error": "no ... backend found"}` from a script.
- First run of any voice skill on a new machine (those skills call the doctor themselves and hand off here when something is missing).

## Instructions

### 1. Run the doctor

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-doctor.py"
```

Exit 0 = everything available. Exit 2 = something missing; the output already names the fix for the current OS.

### 2. Explain in learner terms

Map the result to what they can do **right now**:

- TTS only → `/fluent-listening` works. Pronunciation and voice conversation need mic + STT.
- TTS + mic + STT → all voice skills work.
- Nothing → typed practice is unaffected; offer the install steps.

Keep it short: one line per missing component, the exact install command for their OS, and what it unlocks.

### 2b. Voice quality — the thing learners notice most

The OS engines are intelligible but flat (espeak-ng is outright robotic). For listening and shadowing the learner should hear a natural voice, so recommend a neural engine **by target language**:

| Target language | Recommend | Why |
|-----------------|-----------|-----|
| English, Spanish, French, Italian, Portuguese (BR), Hindi, Japanese, Mandarin | **Kokoro** — `pip install kokoro soundfile` | Best quality available locally. Pulls in torch (~1-2 GB) and downloads a 330 MB model on first use. Japanese needs `pip install misaki[ja]`, Mandarin `misaki[zh]`; non-English needs `espeak-ng` on PATH for phonemes. |
| Dutch, German, Russian, Polish, Nordic, Turkish, Arabic, Persian, Catalan, Ukrainian, Czech, Greek, … (40+) | **Piper** — `pip install piper-tts` | Lightweight (onnxruntime), ~20-80 MB voice per language, downloaded on first use into `<data_dir>/.voice/models/`. |
| Korean, Hebrew, Thai, Indonesian, … | OS voice | No neural voice shipped yet; install the OS language voice (steps below) or point `FLUENT_PIPER_VOICE` at a community model. |

Fluent picks automatically per sentence: Kokoro if it has the language, else Piper if it has the language, else the OS engine. Both neural engines need an audio player (`afplay` / `paplay` / `aplay` / `ffplay` / `play`); the doctor says if none is found. `FLUENT_TTS_ENGINE=kokoro|piper|system` forces one.

Pre-fetch the model so the first lesson doesn't stall on a download:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-doctor.py" --download-voice --lang {target_language}
```

### 3. Recommended install (copy the block for their OS)

**macOS**
```bash
pip3 install faster-whisper sounddevice numpy   # STT + silence-aware mic
pip3 install kokoro soundfile                   # or: pip3 install piper-tts  (see table above)
# OS fallback voices: System Settings → Accessibility → Spoken Content → System Voice → Manage Voices
```

**Linux (Debian/Ubuntu)**
```bash
sudo apt install espeak-ng ffmpeg               # espeak-ng doubles as Kokoro's phonemizer
pip3 install faster-whisper sounddevice numpy
pip3 install kokoro soundfile                   # or: pip3 install piper-tts
```

**Windows (PowerShell or Git Bash)**
```powershell
pip install faster-whisper sounddevice numpy
pip install kokoro soundfile                    # or: pip install piper-tts
# OS fallback voices: Settings → Time & Language → Speech → Manage voices
```

Notes to mention when relevant:
- First transcription downloads a Whisper model (~500 MB for `small`). `FLUENT_WHISPER_MODEL=base` is faster on slow machines; `medium` is more accurate for non-Latin scripts.
- `pip` may need `--break-system-packages` on recent Linux distros, or a venv.
- Preferred voice: `FLUENT_KOKORO_VOICE=em_alex` (Kokoro voice id), `FLUENT_PIPER_VOICE=nl_BE-nathalie-medium` (Piper id or path to an `.onnx`), `FLUENT_TTS_VOICE="Xander"` (OS engines).
- Models download from Hugging Face on first use. If the learner's network blocks it, `FLUENT_PIPER_AUTO_DOWNLOAD=0` and place the `.onnx` + `.onnx.json` in `<data_dir>/.voice/models/` by hand.
- Custom engines plug in via `FLUENT_TTS_CMD='piper ... {text}'` and `FLUENT_STT_CMD='... {file} ...'`.

### 4. Test

After installing, re-run with `--test` so they hear something:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-doctor.py" --test --lang {target_language}
```

Then a 5-second mic check:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-listen.py" --lang {target_language} --max-seconds 5 --countdown 2
```

Read the transcript back to them. If it is roughly right, they are ready — suggest `/fluent-pronunciation` for a first short session.

### 5. Record the preference

If the learner says they want voice by default, add to `learner-profile.json` → `preferences.voice: true` (use a small Python edit or the Write tool; the PostToolUse hook validates and backs up the file). `/fluent-speaking` reads this flag to default to voice mode.

## Critical Rules

- **Never install anything without telling the learner the command first.** Show the command, let them run it or confirm.
- **Don't send audio anywhere.** All backends are local; if the learner asks about cloud STT, explain it is intentionally not supported.
- **Platform first.** Read `platform` from the doctor output; don't paste macOS commands to a Linux user.
- **Degrade gracefully.** A missing backend is never an error for the learner — it just narrows which voice skills are available today.
