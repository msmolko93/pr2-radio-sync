#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jednorazowa autoryzacja OAuth (Authorization Code).
Otwiera w przegladarce strone zgody Spotify, przechwytuje kod na
127.0.0.1:8888/callback, wymienia go na refresh_token i zapisuje do secrets.env.
"""
import http.server, urllib.parse, urllib.request, webbrowser, secrets as pysecrets
import json, base64, os, sys, threading, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
ENVF = os.path.join(HERE, "secrets.env")
SCOPES = "playlist-modify-private playlist-modify-public playlist-read-private user-read-email"
STATE = pysecrets.token_urlsafe(16)

def load_env(path):
    d = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            d[k] = v
    return d

def save_env_kv(path, key, value):
    lines = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []
    out, found = [], False
    for l in lines:
        if l.startswith(key + "="):
            out.append(f"{key}={value}"); found = True
        else:
            out.append(l)
    if not found:
        out.append(f"{key}={value}")
    open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")

env  = load_env(ENVF)
CID  = env.get("SPOTIFY_CLIENT_ID")
CSEC = env.get("SPOTIFY_CLIENT_SECRET")
REDIR = env.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
if not CID or not CSEC:
    print("FAILED: brak SPOTIFY_CLIENT_ID/SECRET w secrets.env", flush=True); sys.exit(1)

auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
    "client_id": CID, "response_type": "code", "redirect_uri": REDIR,
    "scope": SCOPES, "state": STATE, "show_dialog": "true",
})
result = {}

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # cisza
        pass
    def _html(self, msg):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(("<html><body style='font-family:sans-serif;text-align:center;"
                          "padding-top:60px'><h2>%s</h2></body></html>" % msg).encode("utf-8"))
    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        if p.path != "/callback":
            self.send_response(404); self.end_headers(); return
        if q.get("state", [None])[0] != STATE:
            result["error"] = "state_mismatch"; self._html("Blad: zly state.");
            threading.Thread(target=self.server.shutdown, daemon=True).start(); return
        if "error" in q:
            result["error"] = q["error"][0]
            self._html("Autoryzacja odrzucona. Mozesz zamknac te karte.")
            threading.Thread(target=self.server.shutdown, daemon=True).start(); return
        code = q.get("code", [None])[0]
        data = urllib.parse.urlencode({
            "grant_type": "authorization_code", "code": code, "redirect_uri": REDIR}).encode()
        hdr = {"Authorization": "Basic " + base64.b64encode(f"{CID}:{CSEC}".encode()).decode(),
               "Content-Type": "application/x-www-form-urlencoded"}
        try:
            req = urllib.request.Request("https://accounts.spotify.com/api/token", data=data, headers=hdr)
            result.update(json.load(urllib.request.urlopen(req, timeout=30)))
            self._html("Gotowe! Autoryzacja zakonczona. Wroc do Claude Code.")
        except Exception as e:
            result["error"] = f"token_exchange: {e}"
            self._html("Blad wymiany tokena. Wroc do Claude Code.")
        threading.Thread(target=self.server.shutdown, daemon=True).start()

try:
    srv = http.server.HTTPServer(("127.0.0.1", 8888), Handler)
except Exception as e:
    print(f"FAILED: nie moge otworzyc 127.0.0.1:8888 ({e})", flush=True); sys.exit(1)

def watchdog():
    time.sleep(300)
    result.setdefault("error", "timeout_5min")
    try: srv.shutdown()
    except Exception: pass
threading.Thread(target=watchdog, daemon=True).start()

print("AUTH_URL: " + auth_url, flush=True)
opened = False
for opener in (["open", auth_url], ["xdg-open", auth_url]):
    try:
        subprocess.Popen(opener, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); opened = True; break
    except Exception:
        continue
if not opened:
    try: webbrowser.open(auth_url)
    except Exception: pass

srv.serve_forever()  # konczy sie po shutdown() z handlera lub watchdoga

if "refresh_token" in result:
    save_env_kv(ENVF, "SPOTIFY_REFRESH_TOKEN", result["refresh_token"])
    try:
        req = urllib.request.Request("https://api.spotify.com/v1/me",
                                     headers={"Authorization": "Bearer " + result["access_token"]})
        me = json.load(urllib.request.urlopen(req, timeout=30))
        save_env_kv(ENVF, "SPOTIFY_USER_ID", me.get("id", ""))
        print(f"SUCCESS user={me.get('id')} name={me.get('display_name')} product={me.get('product')}", flush=True)
    except Exception as e:
        print(f"SUCCESS token zapisany, ale /me nie zadzialalo: {e}", flush=True)
else:
    print("FAILED: " + str(result.get("error", "brak refresh_token")), flush=True)
