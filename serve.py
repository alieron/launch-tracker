from http.server import SimpleHTTPRequestHandler, HTTPServer
import os
import socket

HOST = "0.0.0.0"
PORT = 8081
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split("?", 1)[0].lstrip("/")

        # .json -> data/*.json
        if path.endswith(".json"):
            return os.path.join(BASE_DIR, "data", path)

        # everything else -> site/
        return os.path.join(BASE_DIR, "site", path)


def local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "<your-lan-ip>"


httpd = HTTPServer((HOST, PORT), Handler)
print(f"Serving on: http://localhost:{PORT}")
print(f"LAN URL:    http://{local_ip()}:{PORT}")
httpd.serve_forever()
