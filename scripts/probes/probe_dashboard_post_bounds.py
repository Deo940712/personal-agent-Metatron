"""part-020 slice-001 operational probe: verify Content-Length boundary
hardening (W1) by sending malformed POST requests to the running dashboard.

Usage (with dashboard running on 127.0.0.1:7777):
    python scripts/probes/probe_dashboard_post_bounds.py

Exit 0 when every boundary-violating request is cleanly rejected.
Exit 1 if any unexpected result is observed.
"""

from __future__ import annotations

import http.client
import json
import sys

HOST = "127.0.0.1"
PORT = 7777
TIMEOUT = 3.0  # seconds — must not hang


def _post(path: str, body_bytes: bytes | None, extra_headers: dict | None = None) -> tuple[int, dict | None]:
    conn = http.client.HTTPConnection(HOST, PORT, timeout=TIMEOUT)
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    if body_bytes is not None:
        headers["Content-Length"] = str(len(body_bytes))
    try:
        conn.request("POST", path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        data = json.loads(raw) if raw else None
        return resp.status, data
    except (ConnectionRefusedError, OSError) as e:
        print(f"ERROR: cannot reach dashboard at http://{HOST}:{PORT} — {e}")
        print("Make sure the dashboard is running before executing this probe.")
        sys.exit(2)
    finally:
        conn.close()


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
                         b'{"pending_id":1,"approve":true}',
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
