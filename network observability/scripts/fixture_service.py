"""Local service-response fixture for the network experience pilot."""

import argparse
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthy":
            status, payload = 200, b"pilot healthy\n"
        elif self.path == "/slow":
            time.sleep(1)
            status, payload = 200, b"pilot slow\n"
        elif self.path == "/unavailable":
            status, payload = 503, b"pilot unavailable\n"
        else:
            status, payload = 404, b"unknown fixture path\n"
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        # Avoid storing access logs for this deterministic fixture.
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"Pilot fixture listening on http://127.0.0.1:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
