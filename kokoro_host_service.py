#!/usr/bin/env python3
"""
[LOCAL-573] Kokoro-82M host-native TTS service.
================================================
Kokoro runs *natively* on the Mac host (LEAD measured 16.5 s for a 2,300-char
stop with ``~/kokoro-venv`` — 2.9x faster than the 48 s the same model took
inside Docker). The polly-tts *container* no longer carries Kokoro; instead it
calls this host service over the Docker host gateway. If this service is down,
the container falls back to Polly, so a tour never loses its audio.

Contract
--------
* ``POST /render``  body ``{"text": "...", "voice": "Joanna"}``  (``voice`` may
  also be sent as ``voice_id``) → **MP3 bytes** (``Content-Type: audio/mpeg``),
  24 kHz mono for neural English voices / 22050 Hz for standard English voices,
  encoded exactly like r1's ``kokoro_engine`` (ffmpeg, same bitrate/sample rate),
  so the bytes are the shape the equivalent Polly voice would have produced.
* ``GET /health`` → ``{"status": "healthy", ...}`` once the pipeline is loaded.

Design
------
* **Pipeline loaded once** at start (``kokoro_engine.warmup()``); cached in the
  module singleton inside ``kokoro_engine``.
* **One render at a time** — a module-level lock serialises ``/render``. Kokoro
  is CPU-bound; concurrent renders only slow each other down and thrash memory.
* **Binds 127.0.0.1 and the Docker host gateway** so the container (which
  reaches the host as ``host.docker.internal`` / the gateway IP) can call it,
  while nothing off-box can. By default we bind ``0.0.0.0`` on the host (the Mac
  is not exposed; Subscribed is local-only) which covers both the loopback and
  the Docker bridge; set ``KOKORO_BIND`` to override.
* **Stdlib only** (``http.server``) — no Flask, so ``~/kokoro-venv`` is used
  exactly as installed (it already has kokoro + torch + numpy + ffmpeg on PATH).

Encoding is delegated to ``kokoro_engine.synthesize_to_mp3`` so the host service
and the container's in-process fallback produce identical MP3s.
"""

import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# kokoro_engine lives at the repo root next to this file. The launchd job runs
# ~/Audioura/kokoro_host_service.py, so the repo root (this file's dir) is on the
# path for the import below.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kokoro_engine  # noqa: E402  (encoding + routing, shared with the container)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s"
)
_log = logging.getLogger("kokoro_host")

PORT = int(os.getenv("KOKORO_PORT", "5181"))
# Bind both loopback and the Docker bridge. 0.0.0.0 is the simplest way to be
# reachable as host.docker.internal from the container while the Mac itself is
# not internet-exposed (local-only Subscribed box). Override with KOKORO_BIND.
BIND = os.getenv("KOKORO_BIND", "0.0.0.0")

# One render at a time: Kokoro is CPU-bound, concurrency only slows each render.
_render_lock = threading.Lock()

# Pipeline load state (reported by /health). Loaded once at start.
_pipeline_ready = False
_pipeline_error = None


def _warm_pipeline():
    """Load the Kokoro pipeline once at start. Records readiness for /health."""
    global _pipeline_ready, _pipeline_error
    try:
        ok = kokoro_engine.warmup()
        _pipeline_ready = bool(ok)
        if not ok:
            _pipeline_error = kokoro_engine._pipeline_load_failed or "warmup returned False"
            _log.warning(f"[LOCAL-573] host pipeline not ready: {_pipeline_error}")
        else:
            _log.info("[LOCAL-573] host Kokoro pipeline ready")
    except Exception as e:  # noqa: BLE001
        _pipeline_ready = False
        _pipeline_error = str(e)
        _log.warning(f"[LOCAL-573] host pipeline warmup raised: {e}")


class KokoroHandler(BaseHTTPRequestHandler):
    # Quieter default logging (one line per request via _log, not stderr spam).
    def log_message(self, fmt, *args):  # noqa: A003
        _log.info("%s - %s", self.address_string(), fmt % args)

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_mp3(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") == "/health":
            self._send_json(
                200,
                {
                    "status": "healthy" if _pipeline_ready else "loading",
                    "service": "kokoro_host",
                    "pipeline_ready": _pipeline_ready,
                    "error": _pipeline_error,
                    "port": PORT,
                },
            )
            return
        self._send_json(404, {"error": "not found", "path": self.path})

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/render":
            self._send_json(404, {"error": "not found", "path": self.path})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b""
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception as e:  # noqa: BLE001
            self._send_json(400, {"error": f"bad request body: {e}"})
            return

        text = (payload.get("text") or "").strip()
        # Accept 'voice' (task contract) or 'voice_id' (Polly field name).
        voice = payload.get("voice") or payload.get("voice_id") or "Joanna"
        if not text:
            self._send_json(400, {"error": "no text provided"})
            return

        # Serialise renders — CPU-bound single-model pipeline.
        with _render_lock:
            try:
                mp3 = kokoro_engine.synthesize_to_mp3(text, voice)
            except kokoro_engine.KokoroUnavailable as e:
                _log.warning(f"[LOCAL-573] kokoro unavailable: {e}")
                self._send_json(503, {"error": f"kokoro unavailable: {e}"})
                return
            except Exception as e:  # noqa: BLE001 (incl. KokoroSynthesisError)
                _log.warning(f"[LOCAL-573] kokoro render failed: {e}")
                self._send_json(500, {"error": f"kokoro render failed: {e}"})
                return

        _log.info(
            f"[LOCAL-573] rendered {len(text)} chars voice={voice} -> {len(mp3)} MP3 bytes"
        )
        self._send_mp3(mp3)


def main():
    _log.info(f"[LOCAL-573] starting Kokoro host service on {BIND}:{PORT}")
    _warm_pipeline()
    server = ThreadingHTTPServer((BIND, PORT), KokoroHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
