#!/usr/bin/env python3
"""
Tests for phone-level pronunciation scoring (.claude/hooks/fluent_phonemes.py),
the voice server (fluent_server.py) and the TTS cache / listening-variety
helpers in fluent_voice.py. No real models: the recognizer is simulated with
FLUENT_PHONEME_CMD, Kokoro / Whisper with stub modules on PYTHONPATH.

Usage:
    python3 tests/test_phonemes.py
"""
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / ".claude" / "hooks"
sys.path.insert(0, str(HOOKS))

import fluent_phonemes as fp  # noqa: E402
import fluent_server as fs  # noqa: E402
import fluent_voice as fv  # noqa: E402

HAVE_G2P = fp.g2p_backend() is not None

STUBS = {
    "kokoro/__init__.py": """
import numpy as np
class KPipeline:
    def __init__(self, lang_code, repo_id=None): self.lang = lang_code
    def __call__(self, text, voice, speed=1.0):
        yield ("g", "p", np.zeros(int(2400 * speed), dtype="float32"))
""",
    "faster_whisper/__init__.py": """
class _Seg:
    def __init__(self, t): self.text = t; self.avg_logprob = -0.2
class WhisperModel:
    def __init__(self, *a, **k): pass
    def transcribe(self, f, language=None, beam_size=5, vad_filter=True, initial_prompt=None):
        t = "el pero corre por el parque" + (f" [{initial_prompt}]" if initial_prompt else "")
        return iter([_Seg(t)]), None
""",
}


def write_silence(path: Path, seconds: float = 1.0, sr: int = 16000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(struct.pack("<h", 0) * int(sr * seconds))


def _have(*mods):
    try:
        for m in mods:
            __import__(m)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------

class TestG2P(unittest.TestCase):
    @unittest.skipUnless(HAVE_G2P, "needs espeak-ng or espeakng-loader")
    def test_spanish_words_and_phones(self):
        g = fp.phonemize("El perro corre por el parque.", "es")
        self.assertTrue(g["ok"], g)
        self.assertEqual([w["word"] for w in g["words"]], ["El", "perro", "corre", "por", "el", "parque"])
        self.assertEqual(g["words"][1]["phones"], ["p", "e", "r", "o"])   # trill r
        self.assertEqual(g["words"][3]["phones"], ["p", "o", "ɾ"])        # tap r
        self.assertNotIn("ˈ", g["ipa"])                                   # stress stripped

    @unittest.skipUnless(HAVE_G2P, "needs espeak-ng or espeakng-loader")
    def test_dutch_length_contrast(self):
        g = fp.phonemize("man maan", "nl")
        self.assertEqual(g["words"][0]["phones"], ["m", "ɑ", "n"])
        self.assertEqual(g["words"][1]["phones"], ["m", "aː", "n"])

    @unittest.skipUnless(HAVE_G2P, "needs espeak-ng or espeakng-loader")
    def test_japanese_splits_on_cjk_punctuation(self):
        g = fp.phonemize("ごはん、おいしい！", "ja")
        self.assertTrue(g["ok"], g)
        self.assertEqual([w["word"] for w in g["words"]], ["ごはん", "おいしい"])
        self.assertGreater(len(g["words"][1]["phones"]), 1)              # phones, not one blob

    @unittest.skipUnless(HAVE_G2P, "needs espeak-ng or espeakng-loader")
    def test_unknown_voice_is_clean_error(self):
        g = fp.phonemize("hello", "xx")
        self.assertFalse(g["ok"])
        self.assertIn("voice", g["error"].lower())

    def test_espeak_voice_mapping(self):
        self.assertEqual(fp.espeak_voice("en", "en-US"), "en-us")
        self.assertEqual(fp.espeak_voice("zh", "zh-CN"), "cmn")
        self.assertEqual(fp.espeak_voice("pt", "pt-BR"), "pt-br")
        self.assertEqual(fp.espeak_voice("nl", "nl-NL"), "nl")

    def test_parse_phones_formats(self):
        self.assertEqual(fp.parse_phones("p e ɾ o"), ["p", "e", "ɾ", "o"])
        self.assertEqual(fp.parse_phones("p_ˈe_r_o"), ["p", "e", "r", "o"])
        self.assertEqual(fp.parse_phones("<pad> p | e"), ["p", "e"])


class TestScoring(unittest.TestCase):
    WORDS = [{"word": "El", "phones": ["e", "l"]}, {"word": "perro", "phones": ["p", "e", "r", "o"]},
             {"word": "corre", "phones": ["k", "o", "r", "e"]}]

    def test_perfect(self):
        r = fp.score_phonemes(self.WORDS, list("elperokore"))
        self.assertEqual(r["score"], 100)
        self.assertEqual(r["weak_words"], [])
        self.assertEqual(r["confusions"], [])

    def test_substitution_attributed_to_word(self):
        heard = ["e", "l", "p", "e", "ɾ", "o", "k", "o", "r", "e"]
        r = fp.score_phonemes(self.WORDS, heard)
        self.assertEqual(r["score"], 90)
        self.assertEqual(r["weak_words"], ["perro"])
        self.assertEqual(r["top_confusions"], [{"expected": "r", "heard": "ɾ", "count": 1}])
        pw = {w["word"]: w for w in r["per_word"]}
        self.assertEqual(pw["perro"]["accuracy"], 75)
        self.assertEqual(pw["corre"]["accuracy"], 100)
        self.assertEqual(pw["perro"]["issues"][0]["kind"], "substitute")

    def test_near_miss_counts_half(self):
        words = [{"word": "maan", "phones": ["m", "aː", "n"]}]
        r = fp.score_phonemes(words, ["m", "a", "n"])   # right vowel, too short
        self.assertTrue(r["confusions"][0]["near"])
        self.assertEqual(r["score"], 83)                 # 1 - 0.5/3

    def test_narrow_diacritics_and_moraic_n_match(self):
        # espeak's Japanese o̞ / ä / ɴ against a recognizer's plain o / a / n
        words = [{"word": "ごはん", "phones": ["ɡ", "o̞", "h", "ä", "ɴ"]}]
        self.assertEqual(fp.score_phonemes(words, ["ɡ", "o", "h", "a", "n"])["score"], 100)

    def test_length_and_nasal_tilde_still_count(self):
        self.assertTrue(fp.score_phonemes([{"word": "x", "phones": ["iː"]}], ["i"])["confusions"])
        self.assertTrue(fp.score_phonemes([{"word": "x", "phones": ["ɐ̃"]}], ["ɐ"])["confusions"])

    def test_sh_variants_are_near_miss(self):
        r = fp.score_phonemes([{"word": "し", "phones": ["ɕ", "i"]}], ["ʃ", "i"])
        self.assertTrue(r["confusions"][0]["near"])
        self.assertEqual(r["score"], 75)

    def test_deletion_and_insertion(self):
        words = [{"word": "koffie", "phones": ["k", "ɔ", "f", "i"]}]
        r = fp.score_phonemes(words, ["k", "ɔ", "i"])
        self.assertEqual([c["kind"] for c in r["confusions"]], ["delete"])
        r = fp.score_phonemes(words, ["k", "ɔ", "f", "i", "ə"])
        self.assertEqual([c["kind"] for c in r["confusions"]], ["insert"])
        self.assertEqual(r["score"], 75)

    def test_empty(self):
        self.assertEqual(fp.score_phonemes(self.WORDS, [])["score"], 0)
        self.assertIn("error", fp.score_phonemes([], ["a"]))

    @unittest.skipUnless(HAVE_G2P, "needs espeak-ng or espeakng-loader")
    def test_analyze_with_custom_recognizer(self):
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "a.wav"; write_silence(wav)
            with unittest.mock.patch.dict(os.environ, {"FLUENT_PHONEME_CMD": "echo e l p e ɾ o"}):
                r = fp.analyze(wav, "El perro", "es")
            self.assertTrue(r["available"], r)
            self.assertEqual(r["recognizer"], "custom")
            self.assertEqual(r["weak_words"], ["perro"])
            self.assertEqual(r["target_ipa"], "el pero")

    def test_analyze_without_recognizer_reports_target_ipa(self):
        with tempfile.TemporaryDirectory() as d, \
             unittest.mock.patch.object(fp, "recognizer_backend", return_value=None), \
             unittest.mock.patch.object(fp, "phonemize", return_value={
                 "ok": True, "backend": "x", "voice": "es", "ipa": "el pero",
                 "words": [{"word": "El", "phones": ["e", "l"]}]}):
            r = fp.analyze(Path(d) / "a.wav", "El", "es")
        self.assertFalse(r["available"])
        self.assertEqual(r["target_ipa"], "el pero")
        self.assertIn("recognizer", r["reason"])


# ---------------------------------------------------------------------------

class TestServerAndCache(unittest.TestCase):
    """Starts a real server process with stub models on PYTHONPATH."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="fluent-server-"))
        cls.mods = cls.tmp / "mods"
        for rel, src in STUBS.items():
            f = cls.mods / rel; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(src)
        cls.data = cls.tmp / "data"; cls.data.mkdir()
        cls.env = {"FLUENT_DATA_DIR": str(cls.data), "PYTHONPATH": str(cls.mods),
                   "FLUENT_VOICE_SERVER_IDLE": "60"}
        os.environ.update(cls.env)
        fv.data_dir.cache_clear()
        cls.proc = subprocess.Popen([sys.executable, str(HOOKS / "voice-server.py"), "run"],
                                    env={**os.environ, **cls.env})
        for _ in range(50):
            if fs.is_running():
                break
            time.sleep(0.1)
        assert fs.is_running(), "server did not start"

    @classmethod
    def tearDownClass(cls):
        fs.stop_server()
        try:
            cls.proc.wait(timeout=10)
        except Exception:
            cls.proc.kill()
        for k in cls.env:
            os.environ.pop(k, None)
        fv.data_dir.cache_clear()

    def setUp(self):
        self.played = []
        self._play = fv.play_wav
        fv.play_wav = lambda p: self.played.append(Path(p).stat().st_size)
        self._player = fv.player_backend
        fv.player_backend = lambda: "fake"

    def tearDown(self):
        fv.play_wav = self._play
        fv.player_backend = self._player

    def test_ping_and_bad_token(self):
        res = fs.client_call({"op": "ping"})
        self.assertTrue(res["ok"]); self.assertEqual(res["pid"], self.proc.pid)
        st = fs.read_state()
        import socket
        with socket.create_connection(("127.0.0.1", st["port"]), timeout=5) as s:
            s.sendall(b'{"op":"ping","token":"nope"}\n')
            self.assertIn(b"bad token", s.recv(4096))

    @unittest.skipUnless(_have("numpy", "soundfile"), "needs numpy + soundfile")
    def test_tts_goes_through_server_and_is_cached(self):
        before = len(list(fv.tts_cache_dir().glob("*.wav")))
        with unittest.mock.patch.object(fv, "kokoro_available", return_value=True):
            r1 = fv.speak("Hola, ¿qué tal?", "Spanish")
            r2 = fv.speak("Hola, ¿qué tal?", "Spanish")
            r3 = fv.speak("Hola, ¿qué tal?", "Spanish", rate=0.8)
        self.assertTrue(r1["ok"], r1); self.assertNotIn("cached", r1)
        self.assertTrue(r2.get("cached"))
        self.assertNotIn("cached", r3, "different rate = different cache entry")
        self.assertEqual(len(self.played), 3)
        self.assertIn("kokoro:e", fs.client_call({"op": "ping"})["loaded"])
        self.assertEqual(len(list(fv.tts_cache_dir().glob("*.wav"))), before + 2)

    @unittest.skipUnless(_have("numpy", "soundfile"), "needs numpy + soundfile")
    def test_cache_disabled_and_pruned(self):
        with unittest.mock.patch.object(fv, "kokoro_available", return_value=True), \
             unittest.mock.patch.dict(os.environ, {"FLUENT_TTS_CACHE": "0"}):
            before = len(list(fv.tts_cache_dir().glob("*.wav")))
            r = fv.speak("Sin caché", "Spanish")
            self.assertTrue(r["ok"]); self.assertNotIn("cached", r)
            self.assertEqual(len(list(fv.tts_cache_dir().glob("*.wav"))), before)
        for i in range(3):
            (fv.tts_cache_dir() / f"old{i}.wav").write_bytes(b"x" * 1000)
            os.utime(fv.tts_cache_dir() / f"old{i}.wav", (1, 1))
        fv._prune_tts_cache(max_mb=0.0001)   # ~100 bytes -> everything old goes
        self.assertEqual([f.name for f in fv.tts_cache_dir().glob("old*.wav")], [])

    @unittest.skipUnless(_have("numpy", "soundfile"), "needs numpy + soundfile")
    def test_noise_and_random_voice(self):
        with unittest.mock.patch.object(fv, "kokoro_available", return_value=True):
            r = fv.speak("Hola", "Spanish", voice="random", noise=0.3)
        self.assertTrue(r["ok"], r)
        self.assertIn(r["voice"], fv.KOKORO_ALT_VOICES["e"])
        self.assertEqual(list(fv.recordings_dir().glob("noisy-*.wav")), [], "noisy temp removed")

    def test_noise_mix_changes_samples(self):
        wav = self.tmp / "tone.wav"
        import math
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 10))) for i in range(16000)))
        out = fv._with_noise(wav, 0.3)
        self.assertNotEqual(out, wav)
        with wave.open(str(out), "rb") as w:
            self.assertEqual(w.getnframes(), 16000)
        self.assertNotEqual(out.read_bytes()[44:], wav.read_bytes()[44:])
        out.unlink()

    def test_stt_goes_through_server_with_prompt(self):
        wav = self.tmp / "s.wav"; write_silence(wav)
        with unittest.mock.patch.object(fv, "stt_backend", return_value="faster-whisper"):
            r = fv.transcribe(wav, "Spanish")
            self.assertEqual(r["backend"], "faster-whisper (server)")
            self.assertEqual(r["transcript"], "el pero corre por el parque")
            self.assertEqual(r["confidence"], 0.8)
            r = fv.transcribe(wav, "Spanish", prompt="Madrid")
            self.assertIn("[Madrid]", r["transcript"])

    def test_random_voice_piper_only_downloaded(self):
        self.assertIsNone(fv.random_voice("piper", "Dutch"))
        m = fv.piper_models_dir() / "nl_BE-nathalie-medium.onnx"; m.write_bytes(b"x")
        self.assertEqual(fv.random_voice("piper", "Dutch"), "nl_BE-nathalie-medium")
        m.unlink()
        self.assertIsNone(fv.random_voice("espeak-ng", "Dutch"))

    def test_listen_cli_reports_phonemes_and_prompt(self):
        wav = self.tmp / "l.wav"; write_silence(wav)
        env = {**os.environ, "FLUENT_PHONEME_CMD": "echo e l p e ɾ o k o r e p o ɾ e l p a ɾ k e",
               "FLUENT_STT_CMD": "echo el pero corre por el parque"}
        r = subprocess.run([sys.executable, str(HOOKS / "voice-listen.py"), "--file", str(wav), "--lang", "es",
                            "--expect", "El perro corre por el parque."], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["score"]["similarity"], 83)
        if HAVE_G2P:
            self.assertTrue(out["phonemes"]["available"])
            self.assertEqual(out["phonemes"]["weak_words"], ["perro"])
            self.assertEqual(out["phonemes"]["score"], 95)
        # --no-phonemes
        r = subprocess.run([sys.executable, str(HOOKS / "voice-listen.py"), "--file", str(wav), "--lang", "es",
                            "--expect", "El perro", "--no-phonemes"], capture_output=True, text=True, env=env)
        self.assertNotIn("phonemes", json.loads(r.stdout))

    def test_server_disabled_env(self):
        with unittest.mock.patch.dict(os.environ, {"FLUENT_VOICE_SERVER": "0"}):
            self.assertFalse(fs.enabled())
            self.assertIsNone(fv._server_call({"op": "ping"}))

    def test_doctor_json_has_phoneme_and_server_fields(self):
        r = subprocess.run([sys.executable, str(HOOKS / "voice-doctor.py"), "--json"],
                           capture_output=True, text=True, env=os.environ.copy())
        rep = json.loads(r.stdout)
        comps = [c["component"] for c in rep["checks"]]
        self.assertIn("g2p", comps); self.assertIn("phoneme-recognizer", comps)
        self.assertTrue(rep["voice_server"]["running"])
        self.assertIn("phoneme_scoring", rep)


if __name__ == "__main__":
    unittest.main(verbosity=2)
