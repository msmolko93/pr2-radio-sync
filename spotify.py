#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cienki klient Spotify Web API + dopasowywanie utworow i wykrywanie klasyki po gatunku."""
import urllib.request, urllib.parse, json, base64, os, sys, time, difflib, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ENVF = os.path.join(HERE, "secrets.env")
MARKET = "PL"

def load_env(path=ENVF):
    d = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); d[k] = v
    # Zmienne srodowiskowe maja pierwszenstwo (GitHub Actions / chmura)
    for k in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REFRESH_TOKEN",
              "SPOTIFY_USER_ID", "SPOTIFY_PLAYLIST_ID", "SPOTIFY_REDIRECT_URI"):
        if os.environ.get(k):
            d[k] = os.environ[k]
    return d

# ------------------------- HTTP ---------------------------------------------
def _req(method, url, headers=None, data=None, timeout=12):
    req = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    for attempt in range(3):
        time.sleep(0.08)   # lagodny globalny rate-limit (unikamy 429/throttlingu)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8")
                return r.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limit
                wait = int(e.headers.get("Retry-After", "2")) + 1
                time.sleep(wait); continue
            body = e.read().decode("utf-8", "replace")
            try: err = json.loads(body)
            except Exception: err = {"raw": body}
            return e.code, err
        except Exception as e:
            if attempt == 2:
                return 0, {"error": str(e)}
            time.sleep(1.0)
    return 0, {"error": "retry_exhausted"}

def get_access_token(env):
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": env["SPOTIFY_REFRESH_TOKEN"],
    }).encode()
    basic = base64.b64encode(f"{env['SPOTIFY_CLIENT_ID']}:{env['SPOTIFY_CLIENT_SECRET']}".encode()).decode()
    st, js = _req("POST", "https://accounts.spotify.com/api/token",
                  headers={"Authorization": "Basic " + basic,
                           "Content-Type": "application/x-www-form-urlencoded"}, data=data)
    if st != 200 or "access_token" not in js:
        raise RuntimeError(f"Nie udalo sie odswiezyc tokena: {st} {js}")
    return js["access_token"]

class Spotify:
    def __init__(self, token):
        self.h = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    def get(self, path, **params):
        url = "https://api.spotify.com/v1" + path
        if params: url += "?" + urllib.parse.urlencode(params)
        return _req("GET", url, headers=self.h)
    def post(self, path, payload):
        return _req("POST", "https://api.spotify.com/v1" + path, headers=self.h,
                    data=json.dumps(payload).encode())
    def put(self, path, payload):
        return _req("PUT", "https://api.spotify.com/v1" + path, headers=self.h,
                    data=json.dumps(payload).encode())

# ------------------------- dopasowanie --------------------------------------
def _norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    for ch in "()[]{}-_/.,:;!?\"'":
        s = s.replace(ch, " ")
    return " ".join(s.split())

def _sim(a, b):
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()

def _artist_match(query_artist, cand_artists):
    """Podobienstwo wykonawcy: max po kandydatach + bonus za zawieranie tokenow."""
    qa = _norm(query_artist)
    if not qa:
        return 0.0
    qt = set(qa.split())
    best = _sim(qa, _norm(", ".join(cand_artists)))
    for ca in cand_artists:
        cn = _norm(ca)
        best = max(best, _sim(qa, cn))
        ct = set(cn.split())
        if qt and ct and (qt <= ct or ct <= qt):   # jeden zbior nazw zawiera drugi
            best = max(best, 0.9)
    return best

def search_track(sp, artist, title):
    """Zwraca (uri, matched_name, artist_ids, score) albo (None, ...).
    Score = 0.6*tytul + 0.4*wykonawca, z boostem przy niemal-idealnym tytule."""
    title = title or ""
    queries = []
    if title and artist:
        queries.append(f'track:"{title}" artist:"{artist}"')
    queries.append(" ".join(x for x in [artist, title] if x))
    best = None
    for q in queries:
        st, js = sp.get("/search", q=q, type="track", limit=5, market=MARKET)
        items = (js.get("tracks") or {}).get("items") or []
        for it in items:
            cand_artists = [a["name"] for a in it.get("artists", [])]
            cand = (", ".join(cand_artists) + " " + it.get("name", "")).strip()
            title_s = _sim(title, it.get("name", "")) if title else 0.0
            artist_s = _artist_match(artist, cand_artists)
            score = 0.6 * title_s + 0.4 * artist_s
            if title_s >= 0.85 and artist_s >= 0.5:
                score = max(score, 0.90)
            if best is None or score > best[3]:
                best = (it["uri"], cand, [a["id"] for a in it.get("artists", [])], score)
        if best and best[3] >= 0.80:
            break
    return best or (None, None, [], 0.0)

CLASSICAL_GENRES = ("classical", "opera", "early music", "baroque", "romanticism",
                    "choral", "orchestra", "compositional", "chamber", "cello",
                    "polish classical", "contemporary classical", "post-romantic era")
NONCLASSICAL_GENRES = ("jazz", "soundtrack", "film", "score", "folk", "world",
                       "klezmer", "blues", "funk", "soul", "pop", "rock", "hip hop",
                       "reggae", "electronic", "ambient", "singer-songwriter")

def genres_for_artists(sp, artist_ids):
    if not artist_ids: return []
    st, js = sp.get("/artists", ids=",".join(artist_ids[:50]))
    gs = []
    for a in js.get("artists", []) or []:
        gs += a.get("genres", []) or []
    return [g.lower() for g in gs]

def is_classical_by_genre(genres):
    if not genres: return None  # nieznane
    has_c = any(any(c in g for c in CLASSICAL_GENRES) for g in genres)
    has_n = any(any(n in g for n in NONCLASSICAL_GENRES) for g in genres)
    if has_c and not has_n: return True
    if has_n: return False
    return None

# ------------------------- self-test ----------------------------------------
if __name__ == "__main__":
    env = load_env()
    tok = get_access_token(env)
    sp = Spotify(tok)
    st, me = sp.get("/me")
    print(f"/me -> {st} user={me.get('id')} name={me.get('display_name')}\n")
    samples = [
        ("Mongo Santamaria", "Summertime"),
        ("Ray Lema", "Mimouna"),
        ("Bester Quartet", "Two Men And A Wardrobe"),
        ("Kapela Maliszów", "Dziwok"),
        ("Masecki-Młynarski Jazz Band Yo-Yo", "Yo - Yo"),
        ("Chopin Mazurek D-Dur Op. 33 Nr 2 - Paderewski", "Mazurek D-Dur Op. 33 Nr 2"),
        ("Wojciech Kilar", "Polonez z Pana Tadeusza"),
    ]
    for artist, title in samples:
        uri, cand, aids, score = search_track(sp, artist, title)
        if not uri:
            print(f"[BRAK ] {artist} — {title}")
            continue
        genres = genres_for_artists(sp, aids)
        cls = is_classical_by_genre(genres)
        tag = "KLASYKA" if cls else ("nie-klas" if cls is False else "nieznany")
        print(f"[{score:.2f}] {cand}\n        genre={genres[:4]} -> {tag}")
