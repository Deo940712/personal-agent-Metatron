"""part-020 slice-001 operational probe: verify Content-Length boundary
hardening (W1) by sending malformed POST requests to the running dashboard.

Usage (with dashboard running on 127.0.0.1:7777):
    python scripts/probes/probe_dashboard_post_bounds.py

Exit 0 when every boundary-violating request is cleanly rejected.
Exit 1 if any unexpected result is observed.
"""

from __future__ import annotations

import http.client
import socket
import json
import sys

HOST = "127.0.0.1"
PORT = 7777
TIMEOUT = 3.0  # seconds — must not hang


def _post(path: str, body_bytes: bytes | None, extra_headers: dict | None = None) -> tuple[int, dict | None]:
    """Send a request with exact raw headers, including malformed lengths."""
    headers = {"Host": f"{HOST}:{PORT}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    if body_bytes is not None and "Content-Length" not in headers:
        headers["Content-Length"] = str(len(body_bytes))
    request = [f"POST {path} HTTP/1.1"]
    request.extend(f"{key}: {value}" for key, value in headers.items())
    request_bytes = ("\r\n".join(request) + "\r\n\r\n").encode("ascii")
    if body_bytes is not None:
        request_bytes += body_bytes
    try:
        with socket.create_connection((HOST, PORT), timeout=TIMEOUT) as sock:
            sock.sendall(request_bytes)
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\r\n\r\n" in b"".join(chunks) and len(b"".join(chunks)) > 65536:
                    break
        raw = b"".join(chunks)
        header, _, payload = raw.partition(b"\r\n\r\n")
        status = int(header.splitlines()[0].split()[1])
        data = json.loads(payload.decode("utf-8")) if payload else None
        return status, data
    except (ConnectionRefusedError, OSError) as e:
        print(f"ERROR: cannot reach dashboard at http://{HOST}:{PORT} — {e}")
        print("Make sure the dashboard is running before executing this probe.")
        sys.exit(2)


def main() -> int:
    failures = 0

    # ── Happy path (sanity check) ──────────────────────────────────────
    status, data = _post("/api/confirm",
                         json.dumps({"pending_id": 1, "approve": True}).encode())
    if status in (200, 400):  # 200 = pending exists, 400 = missing
        print(f"PASS  sanity: {status} (dashboard responding)")
    else:
        print(f"FAIL  sanity: unexpected status {status}")
        failures += 1

    # ── W1: missing Content-Length ─────────────────────────────────────
    status, data = _post("/api/confirm",
                         None,
                         extra_headers={})
    if status == 400:
        print(f"PASS  missing Content-Length: {status} (rejected)")
    else:
        print(f"FAIL  missing Content-Length: {status}")
        failures += 1

    # ── W1: zero Content-Length ────────────────────────────────────────
    status, data = _post("/api/confirm",
                         b'{"pending_id":1,"approve":true}',
                         extra_headers={"Content-Length": "0"})
    if status == 400:
        print(f"PASS  zero Content-Length: {status} (rejected)")
    else:
        print(f"FAIL  zero Content-Length: {status}")
        failures += 1

    # ── W1: negative Content-Length ────────────────────────────────────
    status, data = _post("/api/confirm",
                         b'{"pending_id":1,"approve":true}',
                         extra_headers={"Content-Length": "-1"})
    if status == 400:
        print(f"PASS  negative Content-Length: {status} (rejected, did not hang)")
    else:
        print(f"FAIL  negative Content-Length: {status}")
        failures += 1

    # ── W1: oversize Content-Length (> 65536) ──────────────────────────
    status, data = _post("/api/confirm",
                         b'{"pending_id":1,"approve":true}',
                         extra_headers={"Content-Length": "999999"})
    if status == 400:
        print(f"PASS  oversize Content-Length: {status} (rejected)")
    else:
        print(f"FAIL  oversize Content-Length: {status}")
        failures += 1

    # ── M2: confirm returns structured outcome ─────────────────────────
    status, data = _post("/api/confirm",
                         json.dumps({"pending_id": 99999, "approve": True}).encode())
    if data is not None and "outcome" in data:
        print(f"PASS  structured outcome: outcome={data.get('outcome')!r}")
    else:
        print(f"FAIL  structured outcome: {data}")
        failures += 1

    if failures:
        print(f"\n{failures} probe(s) FAILED")
        return 1
    print(f"\nAll probes PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
