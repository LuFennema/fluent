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
| 🔊 Text-to-speech | `/fluent-listening`, voice replies in `/fluent-speaking voice`, model pronunciation in `/fluent-pronunciation` | macOS `say` · `espeak-ng` / `espeak` / `spd-say` (Linux) · PowerShell SAPI (Windows) · `pyttsx3` · `$FLUENT_TTS_CMD` |
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

### 3. Recommended install (copy the block for their OS)

**macOS**
```bash
pip3 install faster-whisper sounddevice numpy   # STT + silence-aware mic
# TTS: built in (`say`). Add voices: System Settings → Accessibility → Spoken Content → System Voice → Manage Voices
```

**Linux (Debian/Ubuntu)**
```bash
sudo apt install espeak-ng ffmpeg
pip3 install faster-whisper sounddevice numpy
```

**Windows (PowerShell or Git Bash)**
```powershell
pip install faster-whisper sounddevice numpy
# TTS: built in (System.Speech). Add language voices: Settings → Time & Language → Speech → Manage voices
```

Notes to mention when relevant:
- First transcription downloads a Whisper model (~500 MB for `small`). `FLUENT_WHISPER_MODEL=base` is faster on slow machines; `medium` is more accurate for non-Latin scripts.
- `pip` may need `--break-system-packages` on recent Linux distros, or a venv.
- If the learner has a preferred TTS voice: `export FLUENT_TTS_VOICE="Xander"` (macOS) / voice name from `say -v ?` or SAPI.
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
