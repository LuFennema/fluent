"""
Fluent voice layer — local-only text-to-speech, microphone capture and
speech-to-text. No API keys, nothing leaves the machine.

Backends (first available wins, override with env vars):

  TTS   $FLUENT_TTS_CMD           custom command, {text} and {lang} placeholders
        `kokoro` (pip kokoro)     best quality, local; en/es/fr/it/pt-BR/hi/ja/zh only
                                  ($FLUENT_KOKORO_VOICE to pick a voice)
        `piper` (pip piper-tts)   neural per-language voices, local; model auto-
                                  downloaded to <data_dir>/.voice/models on first
                                  use ($FLUENT_PIPER_VOICE, FLUENT_PIPER_AUTO_DOWNLOAD=0,
                                  FLUENT_TTS_ENGINE=kokoro|piper|system to force one)
        Order: custom > kokoro (if it has the language) > piper (if it has the
        language) > OS engine.
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


# ---------------------------------------------------------------------------
# Piper (neural, local, per-language voice models)
# ---------------------------------------------------------------------------

PIPER_VOICES_BASE = os.environ.get(
    "FLUENT_PIPER_VOICES_URL",
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0")

# bcp47 / iso -> default Piper voice id ("<locale>-<name>-<quality>").
# Catalog: https://huggingface.co/rhasspy/piper-voices  (no voice -> fall back
# to the OS engine for that language).
PIPER_DEFAULT_VOICES: dict[str, str] = {
    "en-US": "en_US-lessac-medium", "en-GB": "en_GB-alan-medium", "en": "en_US-lessac-medium",
    "es-ES": "es_ES-davefx-medium", "es-MX": "es_MX-claude-high", "es": "es_ES-davefx-medium",
    "fr": "fr_FR-siwis-medium",
    "de": "de_DE-thorsten-medium",
    "nl-NL": "nl_NL-mls-medium", "nl-BE": "nl_BE-nathalie-medium", "nl": "nl_NL-mls-medium",
    "it": "it_IT-paola-medium",
    "pt-BR": "pt_BR-faber-medium", "pt-PT": "pt_PT-tugão-medium", "pt": "pt_BR-faber-medium",
    "ru": "ru_RU-irina-medium",
    "pl": "pl_PL-darkman-medium",
    "sv": "sv_SE-nst-medium",
    "no": "no_NO-talesyntese-medium", "nb": "no_NO-talesyntese-medium",
    "da": "da_DK-talesyntese-medium",
    "fi": "fi_FI-harri-medium",
    "el": "el_GR-rapunzelina-low",
    "tr": "tr_TR-dfki-medium",
    "cs": "cs_CZ-jirka-medium",
    "hu": "hu_HU-anna-medium",
    "ro": "ro_RO-mihai-medium",
    "uk": "uk_UA-ukrainian_tts-medium",
    "ca": "ca_ES-upc_ona-medium",
    "zh": "zh_CN-huayan-medium",
    "vi": "vi_VN-vais1000-medium",
    "ar": "ar_JO-kareem-medium",
    "fa": "fa_IR-amir-medium",
    "sk": "sk_SK-lili-medium",
    "sl": "sl_SI-artur-medium",
    "sr": "sr_RS-serbski_institut-medium",
    "ka": "ka_GE-natia-medium",
    "kk": "kk_KZ-iseke-x_low",
    "ne": "ne_NP-google-medium",
    "sw": "sw_CD-lanfrica-medium",
    "lb": "lb_LU-marylux-medium",
    "is": "is_IS-bui-medium",
    "lv": "lv_LV-aivars-medium",
}


def piper_models_dir() -> Path:
    d = Path(os.environ.get("FLUENT_PIPER_MODELS_DIR") or (data_dir() / ".voice" / "models"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def piper_voice_for(language: str | None) -> Optional[str]:
    """Default Piper voice id for a language, or None if Piper has no voice for it."""
    iso, bcp = lang_codes(language)
    return PIPER_DEFAULT_VOICES.get(bcp) or PIPER_DEFAULT_VOICES.get(iso)


def piper_voice_url(voice_id: str) -> tuple[str, str]:
    """(onnx_url, json_url) on the piper-voices repo for a voice id like nl_NL-mls-medium."""
    locale, name, quality = voice_id.split("-", 2)
    iso = locale.split("_")[0]
    base = f"{PIPER_VOICES_BASE}/{iso}/{locale}/{name}/{quality}/{voice_id}.onnx"
    return base, base + ".json"


def _download(url: str, dest: Path) -> None:
    import urllib.request
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "fluent-voice/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(dest)


def piper_model_path(voice: str | None, language: str | None = None,
                     download: bool | None = None) -> dict:
    """Resolve a Piper .onnx model. `voice` may be a voice id, a path to an .onnx,
    or None (use the language default). Downloads the model on first use unless
    FLUENT_PIPER_AUTO_DOWNLOAD=0 / download=False."""
    voice = voice or os.environ.get("FLUENT_PIPER_VOICE") or piper_voice_for(language)
    if not voice:
        iso, _ = lang_codes(language)
        return {"ok": False, "error": f"Piper has no default voice for '{iso}'; "
                                      "set FLUENT_PIPER_VOICE to a voice id or .onnx path"}
    p = Path(voice).expanduser()
    if p.suffix == ".onnx":
        if p.exists() and p.with_suffix(".onnx.json").exists():
            return {"ok": True, "model": str(p), "voice": p.stem, "downloaded": False}
        return {"ok": False, "error": f"Piper model not found: {p} (needs the .onnx and .onnx.json)"}
    onnx = piper_models_dir() / f"{voice}.onnx"
    cfg = onnx.with_suffix(".onnx.json")
    if onnx.exists() and cfg.exists():
        return {"ok": True, "model": str(onnx), "voice": voice, "downloaded": False}
    if download is None:
        download = os.environ.get("FLUENT_PIPER_AUTO_DOWNLOAD", "1") not in ("0", "false", "no")
    if not download:
        return {"ok": False, "error": f"Piper voice '{voice}' is not downloaded "
                                      f"(expected {onnx}); run voice-doctor.py --download-voice"}
    try:
        onnx_url, json_url = piper_voice_url(voice)
    except ValueError:
        return {"ok": False, "error": f"'{voice}' is not a Piper voice id (expected <locale>-<name>-<quality>)"}
    sys.stderr.write(f"⬇️  downloading Piper voice {voice} to {onnx.parent} (one time, ~20-80 MB)...\n")
    sys.stderr.flush()
    try:
        _download(json_url, cfg)
        _download(onnx_url, onnx)
    except Exception as e:
        for f in (onnx, cfg, onnx.with_suffix(".onnx.part")):
            try:
                f.unlink()
            except Exception:
                pass
        return {"ok": False, "error": f"could not download Piper voice '{voice}': {e}. "
                                      "Download it manually from huggingface.co/rhasspy/piper-voices "
                                      f"into {onnx.parent}, or set FLUENT_PIPER_VOICE to a local .onnx"}
    return {"ok": True, "model": str(onnx), "voice": voice, "downloaded": True}


def piper_available() -> bool:
    return bool(_which("piper")) or _has_module("piper")


def _piper_cmd() -> list[str]:
    exe = _which("piper")
    return [exe] if exe else [sys.executable, "-m", "piper"]


def piper_synthesize(text: str, model: str, out: Path, rate: float = 1.0) -> None:
    # length_scale is inverse speed: 1.25 = slower
    cmd = _piper_cmd() + ["--model", model, "--output_file", str(out),
                          "--length_scale", f"{1.0 / max(rate, 0.1):.3f}"]
    subprocess.run(cmd, input=text, text=True, check=True, capture_output=True, timeout=120)


def player_backend() -> Optional[str]:
    if is_macos() and _which("afplay"):
        return "afplay"
    for p in ("paplay", "aplay", "ffplay", "play", "mpv"):
        if _which(p):
            return p
    if is_windows():
        return "powershell" if _which("powershell", "pwsh") else "winsound"
    if _has_module("sounddevice") and _has_module("soundfile"):
        return "sounddevice"
    return None


def play_wav(path: Path) -> None:
    b = player_backend()
    p = str(path)
    if b == "afplay":
        subprocess.run(["afplay", p], check=True, timeout=300)
    elif b == "paplay":
        subprocess.run(["paplay", p], check=True, timeout=300)
    elif b == "aplay":
        subprocess.run(["aplay", "-q", p], check=True, timeout=300)
    elif b == "ffplay":
        subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", p], check=True, timeout=300)
    elif b == "play":
        subprocess.run(["play", "-q", p], check=True, timeout=300)
    elif b == "mpv":
        subprocess.run(["mpv", "--really-quiet", "--no-video", p], check=True, timeout=300)
    elif b == "powershell":
        ps = _which("powershell", "pwsh")
        subprocess.run([ps, "-NoProfile", "-Command",
                        f"(New-Object Media.SoundPlayer '{p}').PlaySync()"], check=True, timeout=300)
    elif b == "winsound":
        import winsound  # type: ignore
        winsound.PlaySound(p, winsound.SND_FILENAME)
    elif b == "sounddevice":
        import sounddevice as sd  # type: ignore
        import soundfile as sf  # type: ignore
        data, sr = sf.read(p)
        sd.play(data, sr)
        sd.wait()
    else:
        raise RuntimeError("no audio player found (afplay/paplay/aplay/ffplay/play/mpv)")


# ---------------------------------------------------------------------------
# Kokoro (neural, local, highest quality; 9 languages)
# ---------------------------------------------------------------------------

KOKORO_REPO = os.environ.get("FLUENT_KOKORO_REPO", "hexgrad/Kokoro-82M")

# bcp47 / iso -> (kokoro lang_code, default voice). Kokoro-82M v1.0 covers only
# these languages; anything else falls through to Piper / the OS engine.
KOKORO_VOICES: dict[str, tuple[str, str]] = {
    "en-US": ("a", "af_heart"), "en-GB": ("b", "bf_emma"), "en": ("a", "af_heart"),
    "es": ("e", "ef_dora"),
    "fr": ("f", "ff_siwis"),
    "it": ("i", "if_sara"),
    "pt-BR": ("p", "pf_dora"), "pt": ("p", "pf_dora"),
    "hi": ("h", "hf_alpha"),
    "ja": ("j", "jf_alpha"),
    "zh": ("z", "zf_xiaobei"),
}

_KOKORO_WORKER = r"""
import json, sys
import numpy as np, soundfile as sf
from kokoro import KPipeline
a = json.loads(sys.argv[1])
pipe = KPipeline(lang_code=a["lang"], repo_id=a["repo"])
chunks = [audio for _, _, audio in pipe(a["text"], voice=a["voice"], speed=a["rate"])]
if not chunks:
    sys.exit("kokoro produced no audio")
sf.write(a["out"], np.concatenate([np.asarray(c) for c in chunks]), 24000)
"""


def kokoro_available() -> bool:
    return _has_module("kokoro") and _has_module("soundfile")


def kokoro_voice_for(language: str | None) -> Optional[tuple[str, str]]:
    """(lang_code, voice) for Kokoro, honoring FLUENT_KOKORO_VOICE; None if unsupported."""
    iso, bcp = lang_codes(language)
    entry = KOKORO_VOICES.get(bcp) or KOKORO_VOICES.get(iso)
    if not entry:
        return None
    override = os.environ.get("FLUENT_KOKORO_VOICE")
    return (entry[0], override) if override else entry


def kokoro_synthesize(text: str, lang_code: str, voice: str, out: Path, rate: float = 1.0) -> None:
    """Run Kokoro in a child interpreter so the torch import never lands in the
    caller's process (and a crash there can't take the hook down with it)."""
    args = json.dumps({"text": text, "lang": lang_code, "voice": voice, "out": str(out),
                       "rate": float(rate), "repo": KOKORO_REPO})
    env = dict(os.environ, PYTHONWARNINGS="ignore")
    r = subprocess.run([sys.executable, "-c", _KOKORO_WORKER, args], capture_output=True,
                       text=True, timeout=600, env=env)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["kokoro failed"]
        raise RuntimeError(f"kokoro: {tail[0]}")


def system_tts_backend() -> Optional[str]:
    """The OS / fallback engine (everything except custom and Piper)."""
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


def tts_backend(language: str | None = None) -> Optional[str]:
    """Pick the engine. With a language, neural engines are only chosen when they
    have a voice for it; without one, this answers "what would be used in general".
    FLUENT_TTS_ENGINE=kokoro|piper|system forces one."""
    if os.environ.get("FLUENT_TTS_CMD"):
        return "custom"
    want = os.environ.get("FLUENT_TTS_ENGINE", "auto").lower()
    has_player = player_backend() is not None
    if want in ("auto", "kokoro") and kokoro_available() and has_player \
            and (language is None or kokoro_voice_for(language)):
        return "kokoro"
    if want in ("auto", "piper") and piper_available() and has_player \
            and (language is None or piper_voice_for(language) or os.environ.get("FLUENT_PIPER_VOICE")):
        return "piper"
    return system_tts_backend()


def _is_model_ref(voice: str | None) -> bool:
    """True when `voice` names a neural model (Piper id / .onnx path / Kokoro voice)
    rather than an OS voice name."""
    return bool(voice) and (voice.endswith(".onnx") or voice.count("-") >= 2
                            or re.fullmatch(r"[a-z]{2}_[a-z]+", voice) is not None)


def speak(text: str, language: str | None = None, rate: float = 1.0, voice: str | None = None) -> dict:
    """Speak `text` aloud. Blocks until playback finishes. Returns a result dict."""
    text = text.strip()
    if not text:
        return {"ok": False, "error": "empty text"}
    iso, bcp = lang_codes(language)
    backend = tts_backend(language)
    started = time.time()
    extra: dict = {}
    model: dict = {}
    if backend == "kokoro":
        lang_code, kvoice = kokoro_voice_for(language)  # type: ignore[misc]
        if voice and re.fullmatch(r"[a-z]{2}_[a-z]+", voice):
            kvoice = voice
        extra = {"voice": kvoice}
    elif backend == "piper":
        model = piper_model_path(voice if _is_model_ref(voice) else None, language)
        if model.get("ok"):
            extra = {"voice": model["voice"], "downloaded": model["downloaded"]}
        else:
            # Download refused / failed -> OS engine.
            fallback = system_tts_backend()
            if not fallback:
                return {"ok": False, "backend": "piper", "error": model["error"]}
            extra = {"piper_fallback": model["error"]}
            backend = fallback
    if backend not in ("kokoro", "piper", "custom") and _is_model_ref(voice):
        voice = None  # a neural voice name means nothing to the OS engine
    try:
        if backend in ("kokoro", "piper"):
            out = recordings_dir() / f"tts-{os.getpid()}-{int(time.time() * 1000)}.wav"
            try:
                if backend == "kokoro":
                    kokoro_synthesize(text, lang_code, kvoice, out, rate=rate)
                else:
                    piper_synthesize(text, model["model"], out, rate=rate)
                play_wav(out)
            finally:
                try:
                    out.unlink()
                except Exception:
                    pass
        elif backend == "custom":
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
    return {"ok": True, "backend": backend, "language": iso,
            "seconds": round(time.time() - started, 2), **extra}


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
    kokoro_ok = kokoro_available()
    piper_ok = piper_available()
    player = player_backend()
    if is_macos():
        hint = "`say` ships with macOS. Add voices in System Settings → Accessibility → Spoken Content."
    elif is_windows():
        hint = "PowerShell + System.Speech ships with Windows. Add language voices in Settings → Time & Language → Speech."
    else:
        hint = "Install espeak-ng: `sudo apt install espeak-ng` (Debian/Ubuntu) or `sudo dnf install espeak-ng`."
    if tts and tts not in ("kokoro", "piper", "custom"):
        hint = ("Voice quality upgrade: `pip install kokoro soundfile` (best quality; en/es/fr/it/pt/hi/ja/zh) "
                "or `pip install piper-tts` (good quality, 40+ languages). Both are fully local. " + hint)
    elif (kokoro_ok or piper_ok) and not player:
        hint = ("a neural TTS is installed but no audio player was found — install one: "
                "ffmpeg (ffplay), sox (play), pulseaudio-utils (paplay) or alsa-utils (aplay). " + hint)
    checks.append(Check("tts", tts, tts is not None, hint,
                        ["pip install kokoro soundfile", "pip install piper-tts",
                         "pip install pyttsx3", "export FLUENT_TTS_CMD='...{text}...'"]))
    checks.append(Check("kokoro", "kokoro" if kokoro_ok else None, kokoro_ok,
                        "Optional, best quality. `pip install kokoro soundfile` (pulls in torch, ~1-2 GB; "
                        "first use downloads the 330 MB Kokoro-82M model from Hugging Face). "
                        "Languages: English, Spanish, French, Italian, Portuguese (BR), Hindi, Japanese "
                        "(`pip install misaki[ja]`), Mandarin (`pip install misaki[zh]`). Non-English "
                        "languages also need `espeak-ng` on PATH for phonemization.",
                        ["pip install kokoro soundfile"]))
    checks.append(Check("piper", "piper" if piper_ok else None, piper_ok,
                        "Optional, 40+ languages. `pip install piper-tts`; needs an audio player "
                        "(afplay/paplay/aplay/ffplay/play). Voice models (~20-80 MB) are downloaded on "
                        f"first use into {piper_models_dir()}.",
                        ["pip install piper-tts"]))

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
        "ok": all(c.ok for c in checks if c.component not in ("kokoro", "piper")),
        "platform": platform.system(),
        "python": sys.version.split()[0],
        "checks": [asdict(c) for c in checks],
        "env": {k: os.environ.get(k) for k in (
            "FLUENT_TTS_CMD", "FLUENT_TTS_VOICE", "FLUENT_STT_CMD", "FLUENT_WHISPER_MODEL",
            "FLUENT_WHISPER_CPP_MODEL", "FLUENT_MIC_DEVICE", "FLUENT_TTS_ENGINE",
            "FLUENT_KOKORO_VOICE", "FLUENT_KOKORO_REPO",
            "FLUENT_PIPER_VOICE", "FLUENT_PIPER_MODELS_DIR", "FLUENT_PIPER_AUTO_DOWNLOAD",
        ) if os.environ.get(k)},
    }


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
