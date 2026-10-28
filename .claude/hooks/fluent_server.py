"""
Fluent voice server — keeps the heavy models (Kokoro TTS, Whisper STT, the
wav2vec2 phoneme recognizer) loaded in one long-lived local process so each
sentence in a session doesn't pay the 3-10 s import + load cost again.

Transport: JSON lines over a localhost TCP socket (works on every OS). The
port and a random token are written to <data_dir>/.voice/server.json; only
clients that read that file can talk to it. The server exits by itself after
FLUENT_VOICE_SERVER_IDLE seconds without requests (default 1800).

CLI:
    python3 voice-server.py start      # start in the background (no-op if running)
    python3 voice-server.py stop
    python3 voice-server.py status
    python3 voice-server.py run        # foreground (what `start` spawns)

Clients (`kokoro_synthesize`, `transcribe`, `recognize_phones`) call
`client_call()`; when the server isn't running they fall back to the one-shot
child-process path. `ensure_server()` spawns it on first neural use unless
FLUENT_VOICE_SERVER=0.

Requests / responses (one JSON object per line):
    {"op":"ping"}                                         -> {"ok":true,"loaded":[...]}
    {"op":"tts","text":..,"lang":..,"voice":..,"rate":..,"repo":..,"out":..} -> {"ok":true}
    {"op":"stt","file":..,"lang":..,"model":..}           -> {"ok":true,"transcript":..,"confidence":..}
    {"op":"phonemes","file":..,"model":..}                -> {"ok":true,"raw":"p e r o ..."}
    {"op":"stop"}                                         -> {"ok":true}
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

try:
    from fluent_paths import data_dir  # type: ignore
except Exception:  # pragma: no cover
    def data_dir() -> Path:  # type: ignore
        return Path.home() / ".claude" / "fluent-data"


def state_file() -> Path:
    d = data_dir() / ".voice"
    d.mkdir(parents=True, exist_ok=True)
    return d / "server.json"


def read_state() -> Optional[dict]:
    try:
        return json.loads(state_file().read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Client side
# ---------------------------------------------------------------------------

def enabled() -> bool:
    return os.environ.get("FLUENT_VOICE_SERVER", "auto").lower() not in ("0", "off", "false", "no")


def client_call(req: dict, timeout: float = 600.0) -> dict:
    """Send one request to the running server. Raises if no server is reachable."""
    if not enabled():
        raise RuntimeError("voice server disabled")
    st = read_state()
    if not st:
        raise RuntimeError("voice server not running")
    with socket.create_connection(("127.0.0.1", st["port"]), timeout=5) as s:
        s.settimeout(timeout)
        s.sendall((json.dumps({**req, "token": st["token"]}, ensure_ascii=False) + "\n").encode("utf-8"))
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    if not buf:
        raise RuntimeError("voice server closed the connection")
    return json.loads(buf.decode("utf-8"))


def is_running() -> bool:
    try:
        return bool(client_call({"op": "ping"}, timeout=5).get("ok"))
    except Exception:
        return False


def _server_script() -> Path:
    return Path(__file__).resolve().parent / "voice-server.py"


def ensure_server(wait: float = 0.0) -> bool:
    """Start the server in the background if it isn't running. Returns True when
    a server is reachable (possibly only after `wait` seconds)."""
    if not enabled():
        return False
    if is_running():
        return True
    try:
        kw: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL, "close_fds": True}
        if os.name == "nt":  # pragma: no cover
            kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            kw["start_new_session"] = True
        subprocess.Popen([sys.executable, str(_server_script()), "run"], **kw)
    except Exception:
        return False
    deadline = time.time() + wait
    while time.time() < deadline:
        if is_running():
            return True
        time.sleep(0.2)
    return is_running()


def stop_server() -> bool:
    try:
        client_call({"op": "stop"}, timeout=5)
        return True
    except Exception:
        return False
    finally:
        try:
            state_file().unlink()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Server side
# ---------------------------------------------------------------------------

class _Models:
    """Lazy, cached model handles."""

    def __init__(self) -> None:
        self.kokoro: dict = {}      # lang_code -> KPipeline
        self.whisper: dict = {}     # model name -> WhisperModel
        self.phoneme: dict = {}     # model name -> (processor, model)
        self.lock = threading.Lock()

    def loaded(self) -> list[str]:
        return ([f"kokoro:{k}" for k in self.kokoro] + [f"whisper:{k}" for k in self.whisper]
                + [f"phonemes:{k}" for k in self.phoneme])

    def tts(self, req: dict) -> dict:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline  # type: ignore
        lc = req["lang"]
        if lc not in self.kokoro:
            self.kokoro[lc] = KPipeline(lang_code=lc, repo_id=req.get("repo", "hexgrad/Kokoro-82M"))
        pipe = self.kokoro[lc]
        chunks = [np.asarray(a) for _, _, a in pipe(req["text"], voice=req["voice"], speed=float(req.get("rate", 1.0)))]
        if not chunks:
            return {"ok": False, "error": "kokoro produced no audio"}
        sf.write(req["out"], np.concatenate(chunks), 24000)
        return {"ok": True}

    def stt(self, req: dict) -> dict:
        from faster_whisper import WhisperModel  # type: ignore
        name = req.get("model", "small")
        if name not in self.whisper:
            self.whisper[name] = WhisperModel(name, device="auto", compute_type="auto")
        segs, _info = self.whisper[name].transcribe(req["file"], language=req.get("lang"), beam_size=5,
                                                    vad_filter=True, initial_prompt=req.get("prompt"))
        segs = list(segs)
        text = " ".join(s.text.strip() for s in segs).strip()
        probs = [s.avg_logprob for s in segs if getattr(s, "avg_logprob", None) is not None]
        conf = round(max(0.0, min(1.0, 1.0 + sum(probs) / len(probs))), 2) if probs else None
        return {"ok": True, "transcript": text, "confidence": conf}

    def phonemes(self, req: dict) -> dict:
        import numpy as np
        import soundfile as sf
        import torch  # type: ignore
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor  # type: ignore
        name = req["model"]
        if name not in self.phoneme:
            self.phoneme[name] = (Wav2Vec2Processor.from_pretrained(name), Wav2Vec2ForCTC.from_pretrained(name).eval())
        proc, model = self.phoneme[name]
        audio, sr = sf.read(req["file"], dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != 16000:
            n = int(len(audio) * 16000 / sr)
            audio = np.interp(np.linspace(0, len(audio), n, endpoint=False), np.arange(len(audio)), audio).astype("float32")
        with torch.no_grad():
            logits = model(**proc(audio, sampling_rate=16000, return_tensors="pt")).logits
        return {"ok": True, "raw": proc.batch_decode(torch.argmax(logits, dim=-1))[0]}


def serve(idle_seconds: float | None = None) -> None:
    idle = float(idle_seconds or os.environ.get("FLUENT_VOICE_SERVER_IDLE", "1800"))
    token = secrets.token_hex(16)
    models = _Models()
    last = {"t": time.time()}
    stop_flag = threading.Event()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            line = self.rfile.readline()
            if not line:
                return
            try:
                req = json.loads(line.decode("utf-8"))
                if req.get("token") != token:
                    res = {"ok": False, "error": "bad token"}
                else:
                    last["t"] = time.time()
                    op = req.get("op")
                    with models.lock:
                        if op == "ping":
                            res = {"ok": True, "pid": os.getpid(), "loaded": models.loaded()}
                        elif op == "stop":
                            res = {"ok": True}
                            stop_flag.set()
                        elif op in ("tts", "stt", "phonemes"):
                            res = getattr(models, op)(req)
                        else:
                            res = {"ok": False, "error": f"unknown op {op!r}"}
            except Exception as e:
                res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            self.wfile.write((json.dumps(res, ensure_ascii=False) + "\n").encode("utf-8"))

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    srv = Server(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    state_file().write_text(json.dumps({"port": port, "token": token, "pid": os.getpid(),
                                        "started": time.time()}), encoding="utf-8")
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True)
    t.start()
    try:
        while not stop_flag.is_set():
            time.sleep(1.0)
            if time.time() - last["t"] > idle:
                break
    finally:
        srv.shutdown()
        srv.server_close()
        try:
            if read_state() and read_state().get("pid") == os.getpid():
                state_file().unlink()
        except Exception:
            pass
