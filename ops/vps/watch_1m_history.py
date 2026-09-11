#!/usr/bin/env python3
"""Poll host_1m_history progress every 5s until finished."""
from __future__ import annotations

import json
import time
import urllib.request

URL = "http://127.0.0.1:8001/api/v1/ops/schedulers/host_1m_history"


def main() -> None:
    while True:
        try:
            with urllib.request.urlopen(URL, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except Exception as exc:  # noqa: BLE001
            print(f"error: {exc}", flush=True)
            time.sleep(5)
            continue
        detail = data.get("last_detail") or data.get("last_status") or ""
        pct = data.get("progress_pct")
        running = data.get("running") or data.get("last_status") == "running"
        line = detail
        if pct is not None:
            line = f"[{pct}%] {detail}"
        print(line, flush=True)
        if not running and data.get("last_status") in ("ok", "failed", "skipped"):
            print(f"finished status={data.get('last_status')}", flush=True)
            break
        time.sleep(5)


if __name__ == "__main__":
    main()
