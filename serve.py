from http.server import SimpleHTTPRequestHandler, HTTPServer
import os

PORT = 8000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split("?", 1)[0].lstrip("/")

        # .json -> data/*.json
        if path.endswith(".json"):
            return os.path.join(BASE_DIR, "data", path)

        # everything else -> site/
        return os.path.join(BASE_DIR, "site", path)


httpd = HTTPServer(("localhost", PORT), Handler)
print(f"Serving on http://localhost:{PORT}")
httpd.serve_forever()
