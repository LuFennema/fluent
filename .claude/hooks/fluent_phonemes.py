"""
Fluent phoneme layer — phoneme-level pronunciation scoring, fully local.

Why: a Whisper transcript is a weak pronunciation signal. Whisper is a language
model; say "pero" where "perro" makes sense and it will often write "perro"
anyway, hiding the error. Here we compare what the learner *actually produced*
at the phone level with what the sentence *should* sound like:

  target phones  = espeak-ng phonemization of the target text (G2P)
  heard phones   = a phoneme recognizer run on the recording (acoustic, no LM)
  score          = alignment of the two sequences, attributed back to words

G2P backends (first available wins):
  `espeak-ng` on PATH                        espeak-ng -q --ipa=3 -v <lang>
  `espeakng-loader` (pip)                    bundled libespeak-ng via ctypes
                                             (works on Windows, no system install)

Phoneme recognizer backends:
  $FLUENT_PHONEME_CMD                        custom, {file} and {lang} placeholders,
                                             prints space-separated IPA phones
  transformers + torch (pip)                 wav2vec2 CTC phoneme model, default
                                             facebook/wav2vec2-xlsr-53-espeak-cv-ft
                                             ($FLUENT_PHONEME_MODEL to change),
                                             run in a child interpreter
  the Fluent voice server, when running      (keeps the model loaded)

Everything degrades: no recognizer -> word-level scoring only (plus the target
IPA, which is still useful to show the learner).
"""
from __future__ import annotations

import ctypes
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Optional

# espeak-ng voice names differ from ISO codes for a few languages.
ESPEAK_VOICES: dict[str, str] = {
    "en": "en-us", "en-US": "en-us", "en-GB": "en-gb",
    "pt": "pt", "pt-BR": "pt-br", "pt-PT": "pt",
    "zh": "cmn", "yue": "yue",
    "no": "nb", "nb": "nb",
    "es-MX": "es-419",
    "fa": "fa", "he": "he", "hi": "hi", "ko": "ko", "ja": "ja", "th": "th",
}

STRESS = "ˈˌ"
DEFAULT_PHONEME_MODEL = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"


def espeak_voice(iso: str, bcp: str) -> str:
    return ESPEAK_VOICES.get(bcp) or ESPEAK_VOICES.get(iso) or iso


# ---------------------------------------------------------------------------
# Grapheme-to-phoneme (target side)
# ---------------------------------------------------------------------------

def _which(*names: str) -> Optional[str]:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def g2p_backend() -> Optional[str]:
    if _which("espeak-ng", "espeak"):
        return "espeak-ng"
    try:
        import espeakng_loader  # type: ignore # noqa: F401
        return "espeakng-loader"
    except Exception:
        return None


_lib = None


def _espeak_lib():
    """Load bundled libespeak-ng once (espeakng-loader)."""
    global _lib
    if _lib is not None:
        return _lib
    import espeakng_loader  # type: ignore
    lib = ctypes.cdll.LoadLibrary(espeakng_loader.get_library_path())
    lib.espeak_Initialize.restype = ctypes.c_int
    lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
    lib.espeak_SetVoiceByName.restype = ctypes.c_int
    lib.espeak_TextToPhonemes.restype = ctypes.c_char_p
    lib.espeak_TextToPhonemes.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_int, ctypes.c_int]
    if lib.espeak_Initialize(1, 0, espeakng_loader.get_data_path().encode(), 0) <= 0:  # AUDIO_OUTPUT_RETRIEVAL
        raise RuntimeError("espeak_Initialize failed")
    _lib = lib
    return lib


def _phonemize_raw(text: str, voice: str) -> str:
    """Return espeak's `--ipa=3` style string: words by space, phones by `_`."""
    b = g2p_backend()
    if b == "espeak-ng":
        exe = _which("espeak-ng", "espeak")
        r = subprocess.run([exe, "-q", "--ipa=3", "-v", voice, text], capture_output=True,
                           text=True, timeout=30)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or "espeak-ng failed").strip().splitlines()[-1])
        return " ".join(r.stdout.split())
    if b == "espeakng-loader":
        lib = _espeak_lib()
        if lib.espeak_SetVoiceByName(voice.encode()) != 0:
            raise RuntimeError(f"espeak-ng has no voice '{voice}'")
        buf = ctypes.c_char_p(text.encode("utf-8"))
        out = []
        while buf.value:
            res = lib.espeak_TextToPhonemes(ctypes.byref(buf), 1, 0x02 | (ord("_") << 8))  # UTF-8, IPA, '_' sep
            out.append(res.decode("utf-8") if res else "")
        return " ".join(" ".join(out).split())
    raise RuntimeError("no G2P backend: install espeak-ng or `pip install espeakng-loader`")


def _clean_phone(p: str) -> str:
    p = unicodedata.normalize("NFC", p)
    p = "".join(ch for ch in p if ch not in STRESS and ch != "͡")  # stress, tie bar
    return p


def phonemize(text: str, iso: str, bcp: str | None = None) -> dict:
    """Phonemize `text`. Returns {"ok", "backend", "voice", "words": [{"word", "phones"}], "ipa"}."""
    voice = espeak_voice(iso, bcp or iso)
    words = [w for w in re.split(r"\s+", text.strip()) if re.search(r"\w", w)]
    try:
        raw = _phonemize_raw(" ".join(words), voice)
    except Exception as e:
        return {"ok": False, "error": str(e), "backend": g2p_backend(), "voice": voice}
    chunks = [c for c in raw.split(" ") if c.strip("_")]
    phones_per_chunk = [[_clean_phone(p) for p in c.split("_") if _clean_phone(p)] for c in chunks]
    # espeak may merge/split tokens vs. our word list (e.g. "ship__" or numbers); align counts
    if len(phones_per_chunk) == len(words):
        pairs = list(zip(words, phones_per_chunk))
    else:
        pairs = [(" ".join(words), [p for c in phones_per_chunk for p in c])]
    out_words = [{"word": w.strip(".,;:!?¡¿\"'()[]«»—-"), "phones": ph} for w, ph in pairs]
    return {"ok": True, "backend": g2p_backend(), "voice": voice, "words": out_words,
            "ipa": " ".join("".join(w["phones"]) for w in out_words)}


# ---------------------------------------------------------------------------
# Phoneme recognition (heard side)
# ---------------------------------------------------------------------------

_RECOGNIZER_WORKER = r"""
import json, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, soundfile as sf, torch
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
a = json.loads(sys.argv[1])
audio, sr = sf.read(a["file"], dtype="float32")
if audio.ndim > 1:
    audio = audio.mean(axis=1)
if sr != 16000:
    n = int(len(audio) * 16000 / sr)
    audio = np.interp(np.linspace(0, len(audio), n, endpoint=False), np.arange(len(audio)), audio).astype("float32")
proc = Wav2Vec2Processor.from_pretrained(a["model"])
model = Wav2Vec2ForCTC.from_pretrained(a["model"]).eval()
with torch.no_grad():
    logits = model(**proc(audio, sampling_rate=16000, return_tensors="pt")).logits
ids = torch.argmax(logits, dim=-1)
print(proc.batch_decode(ids)[0])
"""


def _has_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def recognizer_backend() -> Optional[str]:
    if os.environ.get("FLUENT_PHONEME_CMD"):
        return "custom"
    if _has_module("transformers") and _has_module("torch") and _has_module("soundfile"):
        return "wav2vec2"
    return None


def phoneme_model() -> str:
    return os.environ.get("FLUENT_PHONEME_MODEL", DEFAULT_PHONEME_MODEL)


def recognize_phones(audio_file: str | Path, iso: str) -> dict:
    """Run the acoustic phoneme recognizer. Returns {"ok", "backend", "phones": [...]}."""
    backend = recognizer_backend()
    try:
        if backend == "custom":
            import shlex
            cmd = os.environ["FLUENT_PHONEME_CMD"].format(file=shlex.quote(str(audio_file)), lang=iso)
            raw = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True,
                                 timeout=300).stdout
        elif backend == "wav2vec2":
            try:
                from fluent_server import client_call  # type: ignore
                res = client_call({"op": "phonemes", "file": str(audio_file), "model": phoneme_model()})
            except Exception:
                res = None
            if res and res.get("ok"):
                raw = res["raw"]
            else:
                args = json.dumps({"file": str(audio_file), "model": phoneme_model()})
                r = subprocess.run([sys.executable, "-c", _RECOGNIZER_WORKER, args], capture_output=True,
                                   text=True, timeout=900, env=dict(os.environ, PYTHONWARNINGS="ignore"))
                if r.returncode != 0:
                    tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["recognizer failed"]
                    raise RuntimeError(tail[0])
                raw = r.stdout
        else:
            return {"ok": False, "backend": None,
                    "error": "no phoneme recognizer; `pip install transformers torch soundfile` "
                             "or set FLUENT_PHONEME_CMD"}
    except Exception as e:
        return {"ok": False, "backend": backend, "error": str(e)}
    return {"ok": True, "backend": backend, "phones": parse_phones(raw), "raw": raw.strip()}


def parse_phones(raw: str) -> list[str]:
    """Space-separated phones (wav2vec2 phoneme tokenizers) or espeak `_` style."""
    toks = re.split(r"[\s_]+", raw.strip())
    return [_clean_phone(t) for t in toks if _clean_phone(t) and t not in ("|", "<unk>", "<pad>")]


# ---------------------------------------------------------------------------
# Alignment and scoring
# ---------------------------------------------------------------------------

def _base(p: str) -> str:
    """Phone without length/diacritics, for 'near miss' detection."""
    return "".join(ch for ch in unicodedata.normalize("NFD", p)
                   if unicodedata.category(ch)[0] != "M" and ch not in "ːˑ")


def align_phones(target: list[str], heard: list[str]) -> list[dict]:
    """Phone-level edit ops: equal / substitute / delete (missed) / insert (extra)."""
    sm = difflib.SequenceMatcher(a=target, b=heard, autojunk=False)
    ops: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            ops += [{"op": "equal", "t": i, "target": target[i], "heard": target[i]} for i in range(i1, i2)]
        elif tag == "replace":
            n = max(i2 - i1, j2 - j1)
            for k in range(n):
                ti, hj = i1 + k, j1 + k
                if ti < i2 and hj < j2:
                    ops.append({"op": "substitute", "t": ti, "target": target[ti], "heard": heard[hj],
                                "near": _base(target[ti]) == _base(heard[hj])})
                elif ti < i2:
                    ops.append({"op": "delete", "t": ti, "target": target[ti], "heard": None})
                else:
                    ops.append({"op": "insert", "t": i2 - 1, "target": None, "heard": heard[hj]})
        elif tag == "delete":
            ops += [{"op": "delete", "t": i, "target": target[i], "heard": None} for i in range(i1, i2)]
        elif tag == "insert":
            ops += [{"op": "insert", "t": max(i1 - 1, 0), "target": None, "heard": heard[j]} for j in range(j1, j2)]
    return ops


def score_phonemes(target_words: list[dict], heard: list[str]) -> dict:
    """Score heard phones against target words [{"word","phones"}].

    Returns per-word accuracy and a list of confusions the tutor can coach on.
    Near misses (same base phone, different length/diacritic) count half."""
    target = [p for w in target_words for p in w["phones"]]
    owner = [wi for wi, w in enumerate(target_words) for _ in w["phones"]]
    if not target:
        return {"score": 0, "error": "no target phones"}
    ops = align_phones(target, heard)
    errors = 0.0
    per_word = [{"word": w["word"], "target_ipa": "".join(w["phones"]), "phones": len(w["phones"]),
                 "errors": 0.0, "issues": []} for w in target_words]
    confusions: list[dict] = []
    for o in ops:
        if o["op"] == "equal":
            continue
        cost = 0.5 if o.get("near") else 1.0
        errors += cost
        wi = owner[min(o["t"], len(owner) - 1)]
        per_word[wi]["errors"] += cost
        issue = {"word": per_word[wi]["word"], "expected": o["target"], "heard": o["heard"],
                 "kind": o["op"], "near": bool(o.get("near"))}
        per_word[wi]["issues"].append({k: issue[k] for k in ("expected", "heard", "kind", "near")})
        confusions.append(issue)
    for w in per_word:
        w["accuracy"] = round(max(0.0, 1 - w["errors"] / max(w["phones"], 1)) * 100)
        w["ok"] = w["accuracy"] >= 80
    score = round(max(0.0, 1 - errors / len(target)) * 100)
    # Most frequent substitution pairs -> the sound to coach first
    pair_counts: dict[tuple, int] = {}
    for c in confusions:
        if c["kind"] == "substitute":
            key = (c["expected"], c["heard"])
            pair_counts[key] = pair_counts.get(key, 0) + 1
    top = sorted(pair_counts.items(), key=lambda kv: -kv[1])[:3]
    return {
        "score": score,
        "target_phones": len(target),
        "heard_phones": len(heard),
        "target_ipa": " ".join("".join(w["phones"]) for w in target_words),
        "heard_ipa": "".join(heard),
        "per_word": per_word,
        "confusions": confusions,
        "top_confusions": [{"expected": e, "heard": h, "count": n} for (e, h), n in top],
        "weak_words": [w["word"] for w in per_word if not w["ok"]],
    }


def analyze(audio_file: str | Path, expected: str, iso: str, bcp: str | None = None) -> dict:
    """Full pipeline: G2P on expected text + recognizer on audio + scoring."""
    g2p = phonemize(expected, iso, bcp)
    if not g2p["ok"]:
        return {"available": False, "reason": f"g2p: {g2p['error']}", "g2p": g2p}
    rec = recognize_phones(audio_file, iso)
    if not rec["ok"]:
        return {"available": False, "reason": f"recognizer: {rec['error']}",
                "target_ipa": g2p["ipa"], "g2p_backend": g2p["backend"]}
    res = score_phonemes(g2p["words"], rec["phones"])
    res.update({"available": True, "g2p_backend": g2p["backend"], "recognizer": rec["backend"]})
    return res


def doctor() -> dict:
    g = g2p_backend()
    r = recognizer_backend()
    return {
        "g2p": {"backend": g, "ok": g is not None,
                "hint": "install espeak-ng (brew/apt) or `pip install espeakng-loader`"},
        "recognizer": {"backend": r, "ok": r is not None, "model": phoneme_model() if r == "wav2vec2" else None,
                       "hint": "`pip install transformers torch soundfile` (first use downloads the "
                               "~1.2 GB wav2vec2 phoneme model), or set FLUENT_PHONEME_CMD"},
    }
