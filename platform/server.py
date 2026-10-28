#!/usr/bin/env python
"""
Biomescan platform — local web server.

Standard-library only, deliberately. The platform's job is to present pipeline
outputs to a non-technical evaluator (an AFCD officer, a grant panel, an
investor) on a laptop with no build step, no npm, no network and no framework
churn. Anything heavier than ``http.server`` is a liability for that audience.

Run:
    python platform/server.py
    -> http://127.0.0.1:8790

The server reads ``platform/ui/data/bundle.json``, which stage 09 assembles.
It computes nothing scientific: every number it serves was produced and
validated by the pipeline. The one exception is ``/api/coverage``, which
recalculates the §5.3 coverage economics live from user-supplied platform
geometry — and that calls the same :mod:`mikania.economics` functions the
pipeline uses, rather than reimplementing them.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UI = os.path.join(HERE, "ui")
sys.path.insert(0, ROOT)

PORT = int(os.environ.get("BIOMESCAN_PORT", os.environ.get("MIKANIA_PORT", "8790")))

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".geojson": "application/geo+json",
    ".csv": "text/csv; charset=utf-8",
    ".tif": "image/tiff",
}


def _safe_join(base: str, rel: str) -> str | None:
    """
    Resolve ``rel`` under ``base``, refusing anything that escapes it.

    The server binds to loopback, but path traversal is cheap to get right and
    expensive to explain afterwards.
    """
    p = os.path.normpath(os.path.join(base, rel.lstrip("/")))
    return p if os.path.commonpath([os.path.abspath(base), os.path.abspath(p)]) == os.path.abspath(base) else None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body, ctype: str = "application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, default=float).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        mode, ctype = ("rb", MIME.get(ext, "application/octet-stream"))
        with open(path, mode) as fh:
            return self._send(200, fh.read(), ctype)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                return self._serve_file(os.path.join(UI, "index.html"))

            # ---- live coverage recomputation (the only computed endpoint) ----
            if u.path == "/api/coverage":
                from mikania.config import load_config
                from mikania.economics import (coverage_model, programme_cost,
                                               three_tier_funnel)
                cfg = load_config()
                # Shallow-copy so a query never mutates the cached config.
                cfg = json.loads(json.dumps(cfg))
                for key, cast in [("swath_m", float), ("ground_speed_ms", float),
                                  ("sidelap_frac", float),
                                  ("operational_efficiency", float),
                                  ("hours_per_field_day", float)]:
                    if key in q:
                        cfg["platform"][key] = cast(q[key][0])
                area = float(q.get("area_ha", ["3000"])[0])
                return self._send(200, {
                    "coverage": coverage_model(cfg),
                    "programme": programme_cost(area, cfg),
                    "funnel": three_tier_funnel(cfg),
                })

            if u.path == "/api/health":
                bp = os.path.join(UI, "data", "bundle.json")
                return self._send(200, {
                    "ok": True,
                    "bundle_present": os.path.exists(bp),
                    "bundle_mb": round(os.path.getsize(bp) / 1e6, 2) if os.path.exists(bp) else 0,
                })

            # ---- deliverables (GeoTIFF / GeoJSON / CSV downloads) ----
            if u.path.startswith("/deliverables/"):
                p = _safe_join(os.path.join(ROOT, "outputs", "deliverables"),
                               u.path[len("/deliverables/"):])
                if p and os.path.isfile(p):
                    return self._serve_file(p)
                return self._send(404, {"error": "not found"})

            if u.path.startswith("/figures/"):
                p = _safe_join(os.path.join(ROOT, "outputs", "figures"),
                               u.path[len("/figures/"):])
                if p and os.path.isfile(p):
                    return self._serve_file(p)
                return self._send(404, {"error": "not found"})

            # ---- static UI ----
            p = _safe_join(UI, u.path)
            if p and os.path.isfile(p):
                return self._serve_file(p)

            return self._send(404, {"error": "not found", "path": u.path})

        except FileNotFoundError:
            return self._send(404, {"error": "not found"})
        except Exception as e:                                    # pragma: no cover
            traceback.print_exc()
            return self._send(500, {"error": str(e)})


if __name__ == "__main__":
    bundle = os.path.join(UI, "data", "bundle.json")
    if not os.path.exists(bundle):
        print("!! platform/ui/data/bundle.json is missing.")
        print("   Run the pipeline first:  python scripts/15_export_platform.py")
    print(f"Biomescan platform  ->  http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
