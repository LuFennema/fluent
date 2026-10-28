"""
Fluent voice layer — local-only text-to-speech, microphone capture and
speech-to-text. No API keys, nothing leaves the machine.

Backends (first available wins, override with env vars):

  TTS   $FLUENT_TTS_CMD           custom command, {text} and {lang} placeholders
        macOS                     `say` (picks a voice for the target language)
        Linux                     `espeak-ng` / `espeak` / `spd-say`
        Windows                   PowerShell + System.Speech (SAPI)
        any                       `pyttsx3` (pip) as a last resort

  MIC   python `sounddevice`      silence-aware recording (recommended)
        `ffmpeg`                  avfoundation (macOS) / alsa|pulse (Linux)
        `sox` (`rec`)             any platform where sox is installed
        `arecord`                 Linux ALSA

  STT   $FLUENT_STT_CMD           custom command, {file} and {lang} placeholders,
                                  must print the transcript on stdout
        `faster-whisper` (pip)    recommended; model from $FLUENT_WHISPER_MODEL
        `openai-whisper` (pip)    fallback
        `whisper-cli` / `whisper-cpp` / `main` from whisper.cpp on PATH, with
                                  $FLUENT_WHISPER_CPP_MODEL pointing at a .bin

The CLI entry points live next to this file:
  voice-say.py     speak text
  voice-listen.py  record + transcribe (optionally score against expected text)
  voice-doctor.py  report which backends are available and how to install them
"""
from __future__ import annotations

import difflib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import wave
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

try:  # running as a module next to fluent_paths.py
    from fluent_paths import data_dir  # type: ignore
except Exception:  # pragma: no cover - fallback when imported from elsewhere
    def data_dir() -> Path:  # type: ignore
        return Path.home() / ".claude" / "fluent-data"


# ---------------------------------------------------------------------------
# Language table
# ---------------------------------------------------------------------------

# language name (as stored in learner-profile.json) -> (ISO 639-1, BCP-47 default)
LANGUAGES: dict[str, tuple[str, str]] = {
    "english": ("en", "en-US"),
    "spanish": ("es", "es-ES"),
    "castellano": ("es", "es-ES"),
    "español": ("es", "es-ES"),
    "french": ("fr", "fr-FR"),
    "français": ("fr", "fr-FR"),
    "german": ("de", "de-DE"),
    "deutsch": ("de", "de-DE"),
    "dutch": ("nl", "nl-NL"),
    "nederlands": ("nl", "nl-NL"),
    "italian": ("it", "it-IT"),
    "italiano": ("it", "it-IT"),
    "portuguese": ("pt", "pt-PT"),
    "português": ("pt", "pt-BR"),
    "brazilian portuguese": ("pt", "pt-BR"),
    "japanese": ("ja", "ja-JP"),
    "korean": ("ko", "ko-KR"),
    "chinese": ("zh", "zh-CN"),
    "mandarin": ("zh", "zh-CN"),
    "cantonese": ("yue", "zh-HK"),
    "arabic": ("ar", "ar-SA"),
    "russian": ("ru", "ru-RU"),
    "turkish": ("tr", "tr-TR"),
    "polish": ("pl", "pl-PL"),
    "swedish": ("sv", "sv-SE"),
    "norwegian": ("no", "nb-NO"),
    "danish": ("da", "da-DK"),
    "finnish": ("fi", "fi-FI"),
    "greek": ("el", "el-GR"),
    "hebrew": ("he", "he-IL"),
    "hindi": ("hi", "hi-IN"),
    "indonesian": ("id", "id-ID"),
    "vietnamese": ("vi", "vi-VN"),
    "thai": ("th", "th-TH"),
    "czech": ("cs", "cs-CZ"),
    "hungarian": ("hu", "hu-HU"),
    "romanian": ("ro", "ro-RO"),
    "ukrainian": ("uk", "uk-UA"),
    "catalan": ("ca", "ca-ES"),
    "persian": ("fa", "fa-IR"),
    "farsi": ("fa", "fa-IR"),
}


def lang_codes(language: str | None) -> tuple[str, str]:
    """Map a language name or code to (iso639-1, bcp47). Unknown -> ('en','en-US')."""
    if not language:
        return ("en", "en-US")
    key = language.strip().lower()
    if key in LANGUAGES:
        return LANGUAGES[key]
    # already a code like "nl" or "nl-NL"
    m = re.fullmatch(r"([a-z]{2,3})(?:[-_]([A-Za-z]{2}))?", language.strip())
    if m:
        iso = m.group(1).lower()
        region = m.group(2)
        for _, (code, bcp) in LANGUAGES.items():
            if code == iso:
                return (iso, f"{iso}-{region.upper()}" if region else bcp)
        return (iso, f"{iso}-{region.upper()}" if region else iso)
    # "Dutch (Netherlands)" style
    first = re.split(r"[\s(/]", key)[0]
    if first in LANGUAGES:
        return LANGUAGES[first]
    return ("en", "en-US")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _which(*names: str) -> Optional[str]:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _has_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def is_macos() -> bool:
    return platform.system() == "Darwin"


def is_windows() -> bool:
    return platform.system() == "Windows"


def is_linux() -> bool:
    return platform.system() == "Linux"


def recordings_dir() -> Path:
    d = data_dir() / ".voice"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Text-to-speech
# ---------------------------------------------------------------------------

def _macos_voice_for(bcp47: str) -> Optional[str]:
    """Pick an installed `say` voice whose language matches."""
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return None
    want = bcp47.replace("-", "_")
    iso = want.split("_")[0]
    exact, loose = [], []
    for line in out.splitlines():
        # "Xander              nl_NL    # Hallo, ik ben Xander."
        m = re.match(r"^(.+?)\s{2,}([a-z]{2,3}_[A-Za-z]{2,})\s+#", line)
        if not m:
            continue
        name, code = m.group(1).strip(), m.group(2)
        if code == want:
            exact.append(name)
        elif code.startswith(iso + "_"):
            loose.append(name)
    for pool in (exact, loose):
        # prefer non-novelty voices (Siri/premium names appear without parens)
        plain = [n for n in pool if "(" not in n]
        if plain:
            return plain[0]
        if pool:
            return pool[0]
    return None


def tts_backend() -> Optional[str]:
    if os.environ.get("FLUENT_TTS_CMD"):
        return "custom"
    if is_macos() and _which("say"):
        return "say"
    if _which("espeak-ng"):
        return "espeak-ng"
    if _which("espeak"):
        return "espeak"
    if _which("spd-say"):
        return "spd-say"
    if is_windows() and _which("powershell", "pwsh"):
        return "sapi"
    if _has_module("pyttsx3"):
        return "pyttsx3"
    return None


def speak(text: str, language: str | None = None, rate: float = 1.0, voice: str | None = None) -> dict:
    """Speak `text` aloud. Blocks until playback finishes. Returns a result dict."""
    text = text.strip()
    if not text:
        return {"ok": False, "error": "empty text"}
    iso, bcp = lang_codes(language)
    backend = tts_backend()
    started = time.time()
    try:
        if backend == "custom":
            cmd = os.environ["FLUENT_TTS_CMD"].format(text=shlex.quote(text), lang=iso)
            subprocess.run(cmd, shell=True, check=True, timeout=120)
        elif backend == "say":
            v = voice or os.environ.get("FLUENT_TTS_VOICE") or _macos_voice_for(bcp)
            cmd = ["say", "-r", str(int(175 * rate))]
            if v:
                cmd += ["-v", v]
            cmd.append(text)
            subprocess.run(cmd, check=True, timeout=120)
        elif backend in ("espeak-ng", "espeak"):
            cmd = [backend, "-v", voice or os.environ.get("FLUENT_TTS_VOICE") or iso,
                   "-s", str(int(160 * rate)), text]
            subprocess.run(cmd, check=True, timeout=120)
        elif backend == "spd-say":
            cmd = ["spd-say", "-w", "-l", iso, "-r", str(int((rate - 1.0) * 50)), text]
            subprocess.run(cmd, check=True, timeout=120)
        elif backend == "sapi":
            ps = _which("powershell", "pwsh")
            safe = text.replace("'", "''")
            v = (voice or os.environ.get("FLUENT_TTS_VOICE") or "").replace("'", "''")
            script = (
                "Add-Type -AssemblyName System.Speech;"
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                f"$s.Rate = {int((rate - 1.0) * 5)};"
                + (f"try {{ $s.SelectVoice('{v}') }} catch {{}};" if v else
                   f"$vs = $s.GetInstalledVoices() | Where-Object {{ $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq '{iso}' }};"
                   "if ($vs) { $s.SelectVoice($vs[0].VoiceInfo.Name) };")
                + f"$s.Speak('{safe}');"
            )
            subprocess.run([ps, "-NoProfile", "-Command", script], check=True, timeout=120)
        elif backend == "pyttsx3":
            import pyttsx3  # type: ignore
            eng = pyttsx3.init()
            eng.setProperty("rate", int(eng.getProperty("rate") * rate))
            for v_ in eng.getProperty("voices"):
                langs = [str(x).lower() for x in getattr(v_, "languages", [])] + [str(v_.id).lower()]
                if any(iso in s for s in langs):
                    eng.setProperty("voice", v_.id)
                    break
            eng.say(text)
            eng.runAndWait()
        else:
            return {"ok": False, "error": "no TTS backend found; run voice-doctor.py"}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "backend": backend, "error": f"TTS command failed ({e.returncode})"}
    except Exception as e:  # pragma: no cover
        return {"ok": False, "backend": backend, "error": str(e)}
    return {"ok": True, "backend": backend, "language": iso, "seconds": round(time.time() - started, 2)}


# ---------------------------------------------------------------------------
# Microphone capture
# ---------------------------------------------------------------------------

SAMPLE_RATE = 16000


def mic_backend() -> Optional[str]:
    if _has_module("sounddevice") and _has_module("numpy"):
        return "sounddevice"
    if _which("ffmpeg"):
        return "ffmpeg"
    if _which("rec"):
        return "sox"
    if is_linux() and _which("arecord"):
        return "arecord"
    return None


def _record_sounddevice(out: Path, max_seconds: float, silence_seconds: float,
                        silence_threshold: float) -> float:
    import numpy as np  # type: ignore
    import sounddevice as sd  # type: ignore

    device = os.environ.get("FLUENT_MIC_DEVICE")
    block = int(SAMPLE_RATE * 0.1)  # 100 ms
    frames: list = []
    spoke = False
    quiet_blocks = 0
    needed_quiet = max(1, int(silence_seconds / 0.1))
    max_blocks = int(max_seconds / 0.1)

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                        blocksize=block, device=device or None) as stream:
        for _ in range(max_blocks):
            data, _overflow = stream.read(block)
            frames.append(data.copy())
            rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2))) / 32768.0
            if rms > silence_threshold:
                spoke = True
                quiet_blocks = 0
            elif spoke:
                quiet_blocks += 1
                if quiet_blocks >= needed_quiet:
                    break
    audio = np.concatenate(frames) if frames else np.zeros((0, 1), dtype="int16")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())
    return len(audio) / SAMPLE_RATE


def _record_cli(backend: str, out: Path, max_seconds: float) -> float:
    device = os.environ.get("FLUENT_MIC_DEVICE")
    if backend == "ffmpeg":
        if is_macos():
            inp = ["-f", "avfoundation", "-i", f":{device or '0'}"]
        elif is_linux():
            if _which("pactl") or os.environ.get("PULSE_SERVER"):
                inp = ["-f", "pulse", "-i", device or "default"]
            else:
                inp = ["-f", "alsa", "-i", device or "default"]
        else:
            if not device:
                raise RuntimeError("set FLUENT_MIC_DEVICE to your dshow device name, e.g. "
                                   "'Microphone (Realtek Audio)'")
            inp = ["-f", "dshow", "-i", f"audio={device}"]
        cmd = ["ffmpeg", "-y", "-loglevel", "error", *inp, "-t", str(max_seconds),
               "-ac", "1", "-ar", str(SAMPLE_RATE), "-sample_fmt", "s16", str(out)]
    elif backend == "sox":
        cmd = ["rec", "-q", "-r", str(SAMPLE_RATE), "-c", "1", "-b", "16", str(out),
               "trim", "0", str(max_seconds)]
    elif backend == "arecord":
        cmd = ["arecord", "-q", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1",
               "-d", str(int(max_seconds))] + (["-D", device] if device else []) + [str(out)]
    else:
        raise RuntimeError(f"unknown mic backend {backend}")
    subprocess.run(cmd, check=True, timeout=max_seconds + 15)
    try:
        with wave.open(str(out), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return max_seconds


def record(max_seconds: float = 20.0, silence_seconds: float = 1.5,
           silence_threshold: float = 0.012, out: Path | None = None) -> dict:
    """Record from the default microphone to a 16 kHz mono WAV."""
    backend = mic_backend()
    if not backend:
        return {"ok": False, "error": "no microphone backend found; run voice-doctor.py"}
    out = out or recordings_dir() / f"rec-{time.strftime('%Y%m%d-%H%M%S')}.wav"
    try:
        if backend == "sounddevice":
            secs = _record_sounddevice(out, max_seconds, silence_seconds, silence_threshold)
        else:
            secs = _record_cli(backend, out, max_seconds)
    except Exception as e:
        return {"ok": False, "backend": backend, "error": str(e)}
    return {"ok": True, "backend": backend, "file": str(out), "seconds": round(secs, 2)}


# ---------------------------------------------------------------------------
# Speech-to-text
# ---------------------------------------------------------------------------

def stt_backend() -> Optional[str]:
    if os.environ.get("FLUENT_STT_CMD"):
        return "custom"
    if _has_module("faster_whisper"):
        return "faster-whisper"
    if _has_module("whisper"):
        return "openai-whisper"
    if _which("whisper-cli", "whisper-cpp", "whisper.cpp") and os.environ.get("FLUENT_WHISPER_CPP_MODEL"):
        return "whisper.cpp"
    return None


def transcribe(audio_file: str | Path, language: str | None = None) -> dict:
    iso, _ = lang_codes(language)
    backend = stt_backend()
    model_name = os.environ.get("FLUENT_WHISPER_MODEL", "small")
    started = time.time()
    try:
        if backend == "custom":
            cmd = os.environ["FLUENT_STT_CMD"].format(file=shlex.quote(str(audio_file)), lang=iso)
            text = subprocess.run(cmd, shell=True, check=True, capture_output=True,
                                  text=True, timeout=300).stdout.strip()
            conf = None
        elif backend == "faster-whisper":
            from faster_whisper import WhisperModel  # type: ignore
            model = WhisperModel(model_name, device="auto", compute_type="auto")
            segments, info = model.transcribe(str(audio_file), language=iso, beam_size=5,
                                              vad_filter=True)
            segs = list(segments)
            text = " ".join(s.text.strip() for s in segs).strip()
            probs = [getattr(s, "avg_logprob", None) for s in segs]
            probs = [p for p in probs if p is not None]
            # avg_logprob ~ -0.1 good, -1 poor; map to 0..1
            conf = round(max(0.0, min(1.0, 1.0 + (sum(probs) / len(probs)))), 2) if probs else None
        elif backend == "openai-whisper":
            import whisper  # type: ignore
            model = whisper.load_model(model_name)
            res = model.transcribe(str(audio_file), language=iso, fp16=False)
            text = res.get("text", "").strip()
            conf = None
        elif backend == "whisper.cpp":
            exe = _which("whisper-cli", "whisper-cpp", "whisper.cpp")
            cmd = [exe, "-m", os.environ["FLUENT_WHISPER_CPP_MODEL"], "-l", iso, "-nt",
                   "-f", str(audio_file)]
            text = subprocess.run(cmd, check=True, capture_output=True, text=True,
                                  timeout=300).stdout.strip()
            conf = None
        else:
            return {"ok": False, "error": "no speech-to-text backend found; run voice-doctor.py"}
    except Exception as e:
        return {"ok": False, "backend": backend, "error": str(e)}
    return {"ok": True, "backend": backend, "language": iso, "transcript": text,
            "confidence": conf, "seconds": round(time.time() - started, 2)}


# ---------------------------------------------------------------------------
# Pronunciation / repeat-after-me scoring
# ---------------------------------------------------------------------------

def _norm_words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s']", " ", text)
    return [w for w in text.split() if w]


def score_against(expected: str, transcript: str) -> dict:
    """Word-level similarity between what the learner was supposed to say and what
    the recognizer heard. Returns similarity 0..100 plus the mismatched words."""
    exp, got = _norm_words(expected), _norm_words(transcript)
    sm = difflib.SequenceMatcher(a=exp, b=got, autojunk=False)
    similarity = round(sm.ratio() * 100)
    missed, extra = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            missed.extend(exp[i1:i2])
        if tag in ("replace", "insert"):
            extra.extend(got[j1:j2])
    return {"similarity": similarity, "expected_words": len(exp), "heard_words": len(got),
            "missed": missed, "heard_instead": extra}


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

@dataclass
class Check:
    component: str
    backend: Optional[str]
    ok: bool
    hint: str = ""
    alternatives: list[str] = field(default_factory=list)


def doctor() -> list[Check]:
    checks: list[Check] = []

    tts = tts_backend()
    if is_macos():
        hint = "`say` ships with macOS. Add voices in System Settings → Accessibility → Spoken Content."
    elif is_windows():
        hint = "PowerShell + System.Speech ships with Windows. Add language voices in Settings → Time & Language → Speech."
    else:
        hint = "Install espeak-ng: `sudo apt install espeak-ng` (Debian/Ubuntu) or `sudo dnf install espeak-ng`."
    checks.append(Check("tts", tts, tts is not None, hint,
                        ["pip install pyttsx3", "export FLUENT_TTS_CMD='...{text}...'"]))

    mic = mic_backend()
    checks.append(Check("microphone", mic, mic is not None,
                        "Recommended: `pip install sounddevice numpy` (silence-aware recording). "
                        "Fallbacks: ffmpeg, sox (`rec`), arecord.",
                        ["brew install ffmpeg", "sudo apt install ffmpeg", "sudo apt install sox"]))

    stt = stt_backend()
    checks.append(Check("speech-to-text", stt, stt is not None,
                        "Recommended: `pip install faster-whisper` (downloads a model on first use, "
                        f"currently FLUENT_WHISPER_MODEL={os.environ.get('FLUENT_WHISPER_MODEL', 'small')}). "
                        "Fallback: `pip install openai-whisper` (needs ffmpeg), or whisper.cpp with "
                        "FLUENT_WHISPER_CPP_MODEL=/path/to/ggml-small.bin.",
                        ["pip install faster-whisper", "pip install openai-whisper"]))
    return checks


def doctor_report() -> dict:
    checks = doctor()
    return {
        "ok": all(c.ok for c in checks),
        "platform": platform.system(),
        "python": sys.version.split()[0],
        "checks": [asdict(c) for c in checks],
        "env": {k: os.environ.get(k) for k in (
            "FLUENT_TTS_CMD", "FLUENT_TTS_VOICE", "FLUENT_STT_CMD", "FLUENT_WHISPER_MODEL",
            "FLUENT_WHISPER_CPP_MODEL", "FLUENT_MIC_DEVICE") if os.environ.get(k)},
    }


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
