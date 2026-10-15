#!/usr/bin/env python3
"""Serve the taxonomy viewer on localhost so read marks and bins are saved to read.txt / bins.txt.

The page is rebuilt on every reload, so edits to the .bib, classification.txt or bins.txt
show up after a browser refresh.
"""
import argparse
import html
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from build import add_common_args, make_html, write_bins, write_read

LOCK = threading.Lock()


def handler_for(args):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            pass

        def _send(self, code, body, ctype):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.split("?")[0].split("#")[0] not in ("/", "/index.html"):
                return self._send(404, "not found", "text/plain")
            try:
                with LOCK:
                    page, _, _, warnings = make_html(args.bib, args.classification, args.read_file, args.bins_file)
                for w in warnings:
                    print("warning:", w, flush=True)
                self._send(200, page, "text/html")
            except Exception as e:  # show config errors in the browser instead of a blank page
                self._send(500, f"<h2>Build error</h2><pre>{html.escape(str(e))}</pre>", "text/html")

        def do_POST(self):
            if self.headers.get("Origin") not in (None, f"http://127.0.0.1:{self.server.server_port}",
                                                  f"http://localhost:{self.server.server_port}"):
                return self._send(403, "forbidden", "text/plain")
            try:
                payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                with LOCK:
                    if self.path == "/api/read":
                        write_read(args.read_file, [str(k) for k in payload])
                    elif self.path == "/api/bins":
                        write_bins(args.bins_file, [{"name": str(b["name"]), "keys": list(b["keys"]),
                                                     "note": str(b.get("note", ""))} for b in payload])
                    else:
                        return self._send(404, "not found", "text/plain")
                self._send(200, "ok", "text/plain")
            except Exception as e:
                self._send(400, str(e), "text/plain")

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    add_common_args(ap)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="don't open a browser")
    args = ap.parse_args()

    for port in range(args.port, args.port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), handler_for(args))
            break
        except OSError:
            continue
    else:
        sys.exit("no free port found")
    url = f"http://127.0.0.1:{srv.server_port}/"
    print(f"Tau taxonomy running at {url}  (Ctrl-C to stop)", flush=True)
    if not args.no_open:
        threading.Timer(0.3, webbrowser.open, [url]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
