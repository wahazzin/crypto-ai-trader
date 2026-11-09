"""Health check must read cycles.jsonl without a suffix byte-range (raw.githubusercontent answers 501 since 2026-11-06)."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import health_check as hc  # noqa: E402


class _Resp:
    def __init__(self, code, text=""):
        self.status_code, self.text = code, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise hc.requests.HTTPError(f"{self.status_code}")


class HealthCheckRead(unittest.TestCase):
    def test_no_range_header_and_last_cycles(self):
        lines = "\n".join(json.dumps({"cycle_id": f"c{i}", "status": "OK", "ai": {"a": {"ok": True}}}) for i in range(5))
        seen = {}

        def get(url, **kw):
            seen.update(kw)
            if "Range" in (kw.get("headers") or {}):
                return _Resp(501)          # what raw.githubusercontent now does for "bytes=-N"
            return _Resp(200, lines + "\n")

        cyc = hc.last_cycles(hc.read_cycles_text(get=get), 2)
        self.assertNotIn("Range", seen.get("headers") or {})
        self.assertEqual([c["cycle_id"] for c in cyc], ["c3", "c4"])

    def test_retries_once_on_5xx(self):
        calls = []
        hc.time.sleep, orig = (lambda s: None), hc.time.sleep
        try:
            def get(url, **kw):
                calls.append(1)
                return _Resp(502) if len(calls) == 1 else _Resp(200, '{"cycle_id": "x", "status": "OK"}')
            self.assertEqual(hc.last_cycles(hc.read_cycles_text(get=get))[0]["cycle_id"], "x")
            self.assertEqual(len(calls), 2)
        finally:
            hc.time.sleep = orig

    def test_empty_file_raises(self):
        with self.assertRaises(ValueError):
            hc.last_cycles("")


if __name__ == "__main__":
    unittest.main()
