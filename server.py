"""Good Idea / Bad Idea — tiny local server.

Serves index.html and a JSON API backed by data.json, so votes persist and are
shared by every browser that hits this server (including phones on your Wi-Fi).
No accounts: each browser gets a random voter id stored in localStorage.
"""
import json
import os
import threading
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 8037
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(ROOT, "data.json")
LOCK = threading.Lock()

SEED = [
    ("Pineapple belongs on pizza", "Sweet + salty. Fight me.", 41, 38),
    ("A 4-day work week for everyone", "Same pay, one more day of weekend.", 63, 12),
    ("Replace all stairs with slides", "Faster going down. Going up is your problem.", 22, 30),
    ("Socks with sandals, but make it fashion", "", 9, 27),
    ("Downtown food truck park with live music on Fridays", "", 48, 6),
    ("Ban reply-all on company email", "Only managers get the button.", 35, 14),
]


def load():
    if not os.path.exists(DATA_FILE):
        now = time.time()
        ideas = [
            {"id": uuid.uuid4().hex[:10], "text": t, "desc": d, "up": u, "down": n,
             "created": now - (i + 1) * 3600 * 5, "votes": {}}
            for i, (t, d, u, n) in enumerate(SEED)
        ]
        save(ideas)
        return ideas
    with open(DATA_FILE) as f:
        return json.load(f)


def save(ideas):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(ideas, f, indent=1)
    os.replace(tmp, DATA_FILE)


def public(idea, voter):
    out = {k: idea[k] for k in ("id", "text", "desc", "up", "down", "created")}
    out["myVote"] = idea["votes"].get(voter, 0)
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/ideas":
            voter = parse_qs(url.query).get("voter", [""])[0]
            with LOCK:
                ideas = load()
            return self.send_json([public(i, voter) for i in ideas])
        if url.path.endswith((".json", ".py", ".tmp")):
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        data = self.read_json()
        voter = str(data.get("voter", ""))[:64]

        if path == "/api/ideas":
            text = str(data.get("text", "")).strip()[:140]
            desc = str(data.get("desc", "")).strip()[:280]
            if len(text) < 3:
                return self.send_json({"error": "Idea is too short."}, 400)
            idea = {"id": uuid.uuid4().hex[:10], "text": text, "desc": desc,
                    "up": 0, "down": 0, "created": time.time(), "votes": {}}
            with LOCK:
                ideas = load()
                ideas.append(idea)
                save(ideas)
            return self.send_json(public(idea, voter))

        if path == "/api/vote":
            value = data.get("vote")
            if not voter or value not in (1, -1, 0):
                return self.send_json({"error": "Bad vote."}, 400)
            with LOCK:
                ideas = load()
                idea = next((i for i in ideas if i["id"] == data.get("id")), None)
                if not idea:
                    return self.send_json({"error": "No such idea."}, 404)
                prev = idea["votes"].pop(voter, 0)
                if prev == 1:
                    idea["up"] -= 1
                elif prev == -1:
                    idea["down"] -= 1
                if value == 1:
                    idea["up"] += 1
                elif value == -1:
                    idea["down"] += 1
                if value:
                    idea["votes"][voter] = value
                save(ideas)
            return self.send_json(public(idea, voter))

        self.send_error(404)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"Good Idea / Bad Idea running at http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
