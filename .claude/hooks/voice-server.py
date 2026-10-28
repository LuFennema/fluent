#!/usr/bin/env python3
"""
Control the Fluent voice server (keeps Kokoro / Whisper / phoneme models loaded).

Usage:
    python3 voice-server.py start     # background; no-op if already running
    python3 voice-server.py stop
    python3 voice-server.py status    # JSON: running, pid, loaded models
    python3 voice-server.py run       # foreground (used by `start`)

Set FLUENT_VOICE_SERVER=0 to never use it; FLUENT_VOICE_SERVER_IDLE=<seconds>
to change the auto-exit timeout (default 1800).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fluent_paths import force_utf8_io  # noqa: E402
from fluent_server import client_call, ensure_server, is_running, read_state, serve, stop_server  # noqa: E402


def main() -> int:
    force_utf8_io()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "run":
        serve()
        return 0
    if cmd == "start":
        ok = ensure_server(wait=10)
        print(json.dumps({"ok": ok, "running": ok, **(read_state() or {})}))
        return 0 if ok else 1
    if cmd == "stop":
        print(json.dumps({"ok": True, "stopped": stop_server()}))
        return 0
    if cmd == "status":
        if is_running():
            res = client_call({"op": "ping"}, timeout=5)
            print(json.dumps({"running": True, "pid": res.get("pid"), "loaded": res.get("loaded", []),
                              "port": (read_state() or {}).get("port")}))
        else:
            print(json.dumps({"running": False}))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
