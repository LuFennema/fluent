#!/usr/bin/env python3
"""
Tests for the voice layer (.claude/hooks/fluent_voice.py and the voice-*.py CLIs).

Everything runs without audio hardware: TTS and STT are exercised through the
FLUENT_TTS_CMD / FLUENT_STT_CMD custom-command hooks, the microphone path is
covered through --file, and backend detection is tested with a scrubbed PATH.

Usage:
    python3 tests/test_voice.py
"""
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / ".claude" / "hooks"
sys.path.insert(0, str(HOOKS))

import fluent_voice as fv  # noqa: E402


def write_silence(path: Path, seconds: float = 1.0) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fv.SAMPLE_RATE)
        w.writeframes(struct.pack("<h", 0) * int(fv.SAMPLE_RATE * seconds))


def run_cli(script: str, *args: str, env: dict | None = None, stdin: str | None = None):
    e = os.environ.copy()
    e.update(env or {})
    return subprocess.run([sys.executable, str(HOOKS / script), *args], capture_output=True,
                          text=True, env=e, input=stdin, timeout=60)


class TestLangCodes(unittest.TestCase):
    def test_names(self):
        self.assertEqual(fv.lang_codes("Dutch"), ("nl", "nl-NL"))
        self.assertEqual(fv.lang_codes("spanish"), ("es", "es-ES"))
        self.assertEqual(fv.lang_codes("Español"), ("es", "es-ES"))
        self.assertEqual(fv.lang_codes("Brazilian Portuguese"), ("pt", "pt-BR"))

    def test_codes(self):
        self.assertEqual(fv.lang_codes("nl"), ("nl", "nl-NL"))
        self.assertEqual(fv.lang_codes("es-MX"), ("es", "es-MX"))
        self.assertEqual(fv.lang_codes("pt_br"), ("pt", "pt-BR"))

    def test_decorated_and_unknown(self):
        self.assertEqual(fv.lang_codes("Dutch (Netherlands)"), ("nl", "nl-NL"))
        self.assertEqual(fv.lang_codes("Klingon"), ("en", "en-US"))
        self.assertEqual(fv.lang_codes(None), ("en", "en-US"))
        self.assertEqual(fv.lang_codes(""), ("en", "en-US"))


class TestScoring(unittest.TestCase):
    def test_exact_ignores_case_and_punctuation(self):
        s = fv.score_against("Ik wil graag een koffie.", "ik wil graag een koffie")
        self.assertEqual(s["similarity"], 100)
        self.assertEqual(s["missed"], [])
        self.assertEqual(s["heard_instead"], [])

    def test_substitution(self):
        s = fv.score_against("El perro corre por el parque.", "El pero corre por el parque")
        self.assertEqual(s["missed"], ["perro"])
        self.assertEqual(s["heard_instead"], ["pero"])
        self.assertTrue(70 <= s["similarity"] < 100)

    def test_missing_word(self):
        s = fv.score_against("Ik wil graag een koffie.", "ik wil graag koffie")
        self.assertEqual(s["missed"], ["een"])
        self.assertEqual(s["heard_instead"], [])
        self.assertEqual(s["expected_words"], 5)
        self.assertEqual(s["heard_words"], 4)

    def test_empty_transcript(self):
        s = fv.score_against("man maan", "")
        self.assertEqual(s["similarity"], 0)
        self.assertEqual(s["missed"], ["man", "maan"])

    def test_japanese_kanji_matches_kana(self):
        if fv._ja_tagger() is None:
            self.skipTest("needs fugashi + unidic (pip install 'misaki[ja]')")
        s = fv.score_against("ごはん、おいしい！", "ご飯おいしい")
        self.assertEqual(s["similarity"], 100)
        self.assertEqual(s["expected_words"], 2)

    def test_no_space_script_without_tagger_compares_characters(self):
        with unittest.mock.patch.object(fv, "_ja_tagger", return_value=None):
            s = fv.score_against("ねこです", "ネコです")
        self.assertEqual(s["similarity"], 100)
        self.assertEqual(s["expected_words"], 4)

    def test_unicode_normalisation(self):
        # decomposed vs precomposed accents should match
        s = fv.score_against("café", "café")
        self.assertEqual(s["similarity"], 100)


class TestBackendDetection(unittest.TestCase):
    def test_custom_env_wins(self):
        with unittest.mock.patch.dict(os.environ, {"FLUENT_TTS_CMD": "x", "FLUENT_STT_CMD": "y"}):
            self.assertEqual(fv.tts_backend(), "custom")
            self.assertEqual(fv.stt_backend(), "custom")

    def test_nothing_available(self):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("FLUENT_")}
        env["PATH"] = ""
        with unittest.mock.patch.dict(os.environ, env, clear=True), \
             unittest.mock.patch.object(fv, "_has_module", return_value=False), \
             unittest.mock.patch.object(fv, "is_macos", return_value=False), \
             unittest.mock.patch.object(fv, "is_windows", return_value=False):
            self.assertIsNone(fv.tts_backend())
            self.assertIsNone(fv.mic_backend())
            self.assertIsNone(fv.stt_backend())
            rep = fv.doctor_report()
            self.assertFalse(rep["ok"])
            self.assertEqual([c["component"] for c in rep["checks"]],
                             ["tts", "kokoro", "piper", "microphone", "speech-to-text"])
            self.assertTrue(all(not c["ok"] for c in rep["checks"]))
            self.assertTrue(all(c["hint"] for c in rep["checks"]))

    def test_speak_without_backend_is_clean_error(self):
        with unittest.mock.patch.object(fv, "tts_backend", return_value=None):
            res = fv.speak("hallo", "nl")
            self.assertFalse(res["ok"])
            self.assertIn("voice-doctor", res["error"])

    def test_record_without_backend_is_clean_error(self):
        with unittest.mock.patch.object(fv, "mic_backend", return_value=None):
            res = fv.record()
            self.assertFalse(res["ok"])

    def test_speak_empty(self):
        self.assertFalse(fv.speak("   ")["ok"])


FAKE_KOKORO = """
import numpy as np
class KPipeline:
    def __init__(self, lang_code, repo_id=None):
        self.lang = lang_code
    def __call__(self, text, voice, speed=1.0):
        yield ("g", "p", np.zeros(2400, dtype="float32"))
"""


def _have(*mods):
    try:
        for m in mods:
            __import__(m)
        return True
    except Exception:
        return False


class TestNeuralEngines(unittest.TestCase):
    """Kokoro / Piper selection and fallback, without the real models."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fluent-neural-"))
        self.played: list = []
        self._orig_play = fv.play_wav
        fv.play_wav = lambda p: self.played.append(Path(p).stat().st_size)
        self._orig_player = fv.player_backend
        fv.player_backend = lambda: "fake"
        os.environ["FLUENT_DATA_DIR"] = str(self.tmp)
        fv.data_dir.cache_clear() if hasattr(fv.data_dir, "cache_clear") else None

    def tearDown(self):
        fv.play_wav = self._orig_play
        fv.player_backend = self._orig_player
        for k in ("FLUENT_DATA_DIR", "FLUENT_TTS_ENGINE", "FLUENT_PIPER_AUTO_DOWNLOAD",
                  "FLUENT_PIPER_VOICE", "FLUENT_KOKORO_VOICE"):
            os.environ.pop(k, None)

    def test_kokoro_language_table(self):
        self.assertEqual(fv.kokoro_voice_for("Spanish"), ("e", "ef_dora"))
        self.assertEqual(fv.kokoro_voice_for("en-GB"), ("b", "bf_emma"))
        self.assertEqual(fv.kokoro_voice_for("Brazilian Portuguese"), ("p", "pf_dora"))
        self.assertIsNone(fv.kokoro_voice_for("Dutch"))
        self.assertIsNone(fv.kokoro_voice_for("German"))
        with unittest.mock.patch.dict(os.environ, {"FLUENT_KOKORO_VOICE": "em_alex"}):
            self.assertEqual(fv.kokoro_voice_for("es"), ("e", "em_alex"))

    def test_piper_language_table_and_urls(self):
        self.assertEqual(fv.piper_voice_for("Dutch"), "nl_NL-mls-medium")
        self.assertEqual(fv.piper_voice_for("nl-BE"), "nl_BE-nathalie-medium")
        self.assertEqual(fv.piper_voice_for("German"), "de_DE-thorsten-medium")
        self.assertIsNone(fv.piper_voice_for("Japanese"))
        onnx, cfg = fv.piper_voice_url("nl_NL-mls-medium")
        self.assertTrue(onnx.endswith("/nl/nl_NL/mls/medium/nl_NL-mls-medium.onnx"))
        self.assertEqual(cfg, onnx + ".json")
        for vid in set(fv.PIPER_DEFAULT_VOICES.values()):
            fv.piper_voice_url(vid)  # every catalog id must parse

    def test_engine_order_prefers_kokoro_then_piper_then_system(self):
        with unittest.mock.patch.object(fv, "kokoro_available", return_value=True), \
             unittest.mock.patch.object(fv, "piper_available", return_value=True), \
             unittest.mock.patch.object(fv, "system_tts_backend", return_value="espeak-ng"):
            self.assertEqual(fv.tts_backend("Spanish"), "kokoro")   # kokoro has es
            self.assertEqual(fv.tts_backend("Dutch"), "piper")      # kokoro lacks nl, piper has it
            self.assertEqual(fv.tts_backend("Japanese"), "kokoro")  # kokoro has ja, piper doesn't
            self.assertEqual(fv.tts_backend("Korean"), "espeak-ng") # neither
            self.assertEqual(fv.tts_backend(), "kokoro")
            with unittest.mock.patch.dict(os.environ, {"FLUENT_TTS_ENGINE": "system"}):
                self.assertEqual(fv.tts_backend("Spanish"), "espeak-ng")
            with unittest.mock.patch.dict(os.environ, {"FLUENT_TTS_ENGINE": "piper"}):
                self.assertEqual(fv.tts_backend("Spanish"), "piper")
            with unittest.mock.patch.dict(os.environ, {"FLUENT_TTS_CMD": "x"}):
                self.assertEqual(fv.tts_backend("Spanish"), "custom")

    def test_no_player_disables_neural_engines(self):
        fv.player_backend = lambda: None
        with unittest.mock.patch.object(fv, "kokoro_available", return_value=True), \
             unittest.mock.patch.object(fv, "piper_available", return_value=True), \
             unittest.mock.patch.object(fv, "system_tts_backend", return_value="say"):
            self.assertEqual(fv.tts_backend("Spanish"), "say")

    @unittest.skipUnless(_have("numpy", "soundfile"), "needs numpy + soundfile")
    def test_kokoro_synthesis_through_worker(self):
        mods = self.tmp / "mods"
        (mods / "kokoro").mkdir(parents=True)
        (mods / "kokoro" / "__init__.py").write_text(FAKE_KOKORO)
        with unittest.mock.patch.dict(os.environ, {"PYTHONPATH": str(mods)}), \
             unittest.mock.patch.object(fv, "kokoro_available", return_value=True):
            res = fv.speak("Hola, ¿qué tal?", "Spanish")
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["backend"], "kokoro")
        self.assertEqual(res["voice"], "ef_dora")
        self.assertEqual(len(self.played), 1)
        self.assertGreater(self.played[0], 44)  # a real WAV was written and played
        self.assertEqual(list((self.tmp / ".voice").glob("tts-*.wav")), [], "temp wav must be removed")

    def test_kokoro_worker_failure_is_reported(self):
        with unittest.mock.patch.dict(os.environ, {"PYTHONPATH": str(self.tmp)}), \
             unittest.mock.patch.object(fv, "kokoro_available", return_value=True):
            res = fv.speak("Hola", "Spanish")   # no kokoro module on that path -> ImportError
        self.assertFalse(res["ok"])
        self.assertEqual(res["backend"], "kokoro")
        self.assertIn("kokoro", res["error"])

    def test_piper_model_resolution_and_download(self):
        downloads: list = []

        def fake_download(url, dest):
            downloads.append(url)
            dest.write_bytes(b"model")

        with unittest.mock.patch.object(fv, "_download", fake_download):
            res = fv.piper_model_path(None, "Dutch")
            self.assertTrue(res["ok"], res)
            self.assertTrue(res["downloaded"])
            self.assertEqual(res["voice"], "nl_NL-mls-medium")
            self.assertEqual(len(downloads), 2)
            self.assertTrue(Path(res["model"]).exists())
            # second call: cached, no download
            res2 = fv.piper_model_path(None, "Dutch")
            self.assertFalse(res2["downloaded"])
            self.assertEqual(len(downloads), 2)

    def test_piper_download_disabled_and_failure(self):
        with unittest.mock.patch.dict(os.environ, {"FLUENT_PIPER_AUTO_DOWNLOAD": "0"}):
            res = fv.piper_model_path(None, "German")
            self.assertFalse(res["ok"])
            self.assertIn("not downloaded", res["error"])
        self.assertFalse(fv.piper_model_path(None, "Japanese")["ok"])

        def boom(url, dest):
            raise OSError("network down")
        with unittest.mock.patch.object(fv, "_download", boom):
            res = fv.piper_model_path(None, "German")
            self.assertFalse(res["ok"])
            self.assertIn("could not download", res["error"])
            self.assertEqual(list((self.tmp / ".voice" / "models").glob("*")), [], "no partial files left")

    def test_piper_speak_falls_back_to_system_when_download_refused(self):
        spoken = []
        with unittest.mock.patch.dict(os.environ, {"FLUENT_PIPER_AUTO_DOWNLOAD": "0",
                                                   "FLUENT_TTS_CMD": ""}), \
             unittest.mock.patch.object(fv, "kokoro_available", return_value=False), \
             unittest.mock.patch.object(fv, "piper_available", return_value=True), \
             unittest.mock.patch.object(fv, "system_tts_backend", return_value="espeak-ng"), \
             unittest.mock.patch.object(fv.subprocess, "run", lambda cmd, **k: spoken.append(cmd)):
            os.environ.pop("FLUENT_TTS_CMD")
            res = fv.speak("Guten Tag", "German")
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["backend"], "espeak-ng")
        self.assertIn("piper_fallback", res)
        self.assertEqual(spoken[0][0], "espeak-ng")

    def test_piper_speak_synthesizes_and_plays(self):
        model = self.tmp / "v.onnx"
        model.write_bytes(b"m"); model.with_suffix(".onnx.json").write_text("{}")
        calls = []

        def fake_run(cmd, **k):
            calls.append(cmd)
            Path(cmd[cmd.index("--output_file") + 1]).write_bytes(b"RIFF" + b"\0" * 100)
        with unittest.mock.patch.object(fv, "kokoro_available", return_value=False), \
             unittest.mock.patch.object(fv, "piper_available", return_value=True), \
             unittest.mock.patch.object(fv, "_piper_cmd", return_value=["piper"]), \
             unittest.mock.patch.object(fv.subprocess, "run", fake_run):
            res = fv.speak("Hallo wereld", "Dutch", rate=0.8, voice=str(model))
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["backend"], "piper")
        self.assertEqual(res["voice"], "v")
        self.assertIn("--length_scale", calls[0])
        self.assertEqual(calls[0][calls[0].index("--length_scale") + 1], "1.250")
        self.assertEqual(self.played, [104])

    def test_doctor_marks_neural_engines_optional(self):
        with unittest.mock.patch.object(fv, "kokoro_available", return_value=False), \
             unittest.mock.patch.object(fv, "piper_available", return_value=False), \
             unittest.mock.patch.object(fv, "tts_backend", return_value="say"), \
             unittest.mock.patch.object(fv, "mic_backend", return_value="ffmpeg"), \
             unittest.mock.patch.object(fv, "stt_backend", return_value="faster-whisper"):
            rep = fv.doctor_report()
        self.assertTrue(rep["ok"], "missing kokoro/piper must not fail the report")
        comps = {c["component"]: c for c in rep["checks"]}
        self.assertFalse(comps["kokoro"]["ok"]); self.assertFalse(comps["piper"]["ok"])
        self.assertIn("kokoro", comps["tts"]["hint"])


class TestCLIs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fluent-voice-")
        self.data = Path(self.tmp) / "data"
        self.data.mkdir()
        (self.data / "learner-profile.json").write_text(json.dumps(
            {"learner": {"name": "T", "target_language": "Dutch"}}), encoding="utf-8")
        self.env = {"FLUENT_DATA_DIR": str(self.data)}
        self.log = Path(self.tmp) / "tts.log"

    def test_say_uses_custom_cmd_and_profile_language(self):
        env = dict(self.env, FLUENT_TTS_CMD=f"echo {{lang}}:{{text}} >> {self.log}")
        r = run_cli("voice-say.py", "Goedemiddag!", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["ok"])
        self.assertEqual(out["backend"], "custom")
        self.assertEqual(out["language"], "nl")  # from learner-profile
        self.assertEqual(self.log.read_text().strip(), "nl:Goedemiddag!")

    def test_say_lang_override_stdin_and_quiet(self):
        env = dict(self.env, FLUENT_TTS_CMD=f"echo {{lang}}:{{text}} >> {self.log}")
        r = run_cli("voice-say.py", "--lang", "Spanish", "--quiet", env=env, stdin="Hola")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.log.read_text().strip(), "es:Hola")

    def test_say_without_backend_exits_1(self):
        env = dict(self.env, PATH="")
        r = run_cli("voice-say.py", "x", env=env)
        self.assertEqual(r.returncode, 1)
        self.assertFalse(json.loads(r.stdout)["ok"])

    def test_listen_file_with_expect(self):
        wav = Path(self.tmp) / "in.wav"
        write_silence(wav)
        env = dict(self.env, FLUENT_STT_CMD="echo ik wil graag koffie")
        r = run_cli("voice-listen.py", "--file", str(wav), "--expect", "Ik wil graag een koffie.",
                    env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["ok"])
        self.assertEqual(out["transcript"], "ik wil graag koffie")
        self.assertEqual(out["language"], "nl")
        self.assertEqual(out["stt_backend"], "custom")
        self.assertEqual(out["score"]["missed"], ["een"])
        self.assertTrue(wav.exists(), "--file input must never be deleted")

    def test_listen_stt_receives_file_and_lang(self):
        wav = Path(self.tmp) / "in.wav"
        write_silence(wav)
        env = dict(self.env, FLUENT_STT_CMD="echo got:{lang}:{file}")
        r = run_cli("voice-listen.py", "--file", str(wav), "--lang", "fr", env=env)
        out = json.loads(r.stdout)
        self.assertEqual(out["transcript"], f"got:fr:{wav}")

    def test_listen_missing_file(self):
        r = run_cli("voice-listen.py", "--file", "/nonexistent.wav", env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertFalse(json.loads(r.stdout)["ok"])

    def test_listen_without_stt_backend_exits_1(self):
        wav = Path(self.tmp) / "in.wav"
        write_silence(wav)
        env = dict(self.env, PATH="")
        r = run_cli("voice-listen.py", "--file", str(wav), env=env)
        self.assertEqual(r.returncode, 1)
        out = json.loads(r.stdout)
        self.assertFalse(out["ok"])
        self.assertIn("voice-doctor", out["hint"])

    def test_doctor_json_and_exit_codes(self):
        env = dict(self.env, PATH="")
        r = run_cli("voice-doctor.py", "--json", env=env)
        self.assertEqual(r.returncode, 2)
        rep = json.loads(r.stdout)
        self.assertFalse(rep["ok"])
        self.assertEqual([c["component"] for c in rep["checks"]],
                         ["tts", "kokoro", "piper", "microphone", "speech-to-text", "g2p", "phoneme-recognizer"])

        env = dict(self.env, FLUENT_TTS_CMD="true", FLUENT_STT_CMD="true",
                   FLUENT_MIC_FAKE="1")
        r = run_cli("voice-doctor.py", env=env)
        self.assertIn("Text-to-speech", r.stdout)
        self.assertIn("Speech-to-text", r.stdout)

    def test_doctor_human_output_mentions_fix(self):
        env = dict(self.env, PATH="")
        r = run_cli("voice-doctor.py", env=env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("how to fix", r.stdout)
        self.assertIn("Typed practice", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
