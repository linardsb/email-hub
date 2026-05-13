#!/usr/bin/env python3
"""Export OpenAPI spec from FastAPI app.

Two modes:
  * default (static) — call ``app.openapi()`` on the in-process app object.
  * ``--live`` — boot uvicorn on an ephemeral port and fetch ``/openapi.json``
    over HTTP. Catches middleware/lifespan-injected schema differences that
    the static mode misses.

Usage:
    uv run python scripts/export-openapi.py
    uv run python scripts/export-openapi.py --output path/to/openapi.json
    uv run python scripts/export-openapi.py --live
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

# Allow importing app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_BOOT_TIMEOUT_S = 30.0
_POLL_INTERVAL_S = 0.25


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _fetch_static() -> dict[str, object]:
    from app.main import app

    return dict(app.openapi())


def _fetch_live() -> dict[str, object]:
    """Boot uvicorn on an ephemeral port and fetch /openapi.json over HTTP."""
    port = _free_port()
    proc = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + _BOOT_TIMEOUT_S
        url = f"http://127.0.0.1:{port}/openapi.json"
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                resp = httpx.get(url, timeout=2.0)
                if resp.status_code == 200:
                    return dict(resp.json())
            except httpx.HTTPError as exc:
                last_error = exc
            time.sleep(_POLL_INTERVAL_S)
        msg = f"Uvicorn did not serve /openapi.json within {_BOOT_TIMEOUT_S}s"
        if last_error is not None:
            msg += f" (last error: {last_error})"
        raise RuntimeError(msg)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export OpenAPI spec from FastAPI app",
    )
    parser.add_argument(
        "--output",
        default="cms/packages/sdk/openapi.json",
        help="Output path (default: cms/packages/sdk/openapi.json)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Boot uvicorn and fetch /openapi.json over HTTP (catches middleware effects)",
    )
    args = parser.parse_args()

    spec = _fetch_live() if args.live else _fetch_static()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(spec, indent=2) + "\n")
    path_count = len(spec.get("paths", {}) or {})
    mode = "live" if args.live else "static"
    print(f"OpenAPI spec written to {output} ({path_count} paths, mode={mode})")


if __name__ == "__main__":
    main()
