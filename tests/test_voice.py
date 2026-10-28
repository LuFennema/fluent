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
                             ["tts", "microphone", "speech-to-text"])
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
        self.assertEqual(len(rep["checks"]), 3)

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
