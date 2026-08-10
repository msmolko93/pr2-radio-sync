#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
"W tonacji Trójki" — krocząca playlista z ostatnich 7 dni.
Audycja Agnieszki Szydłowskiej: poniedziałki ~14:00-16:00 na Trójce.
Zbiera utwory z okna audycji z ostatnich 7 dni (rolling), dopasowuje do Spotify
i podmienia zawartość playlisty. Reużywa prlist.py (scraper) i spotify.py (klient).

Użycie:
  python3 sync_wtt.py            # dziś (Europe/Warsaw), okno 7 dni wstecz
  python3 sync_wtt.py --dry-run  # bez zapisu na Spotify
  python3 sync_wtt.py 2026-08-10 # udawany "dziś"
"""
import sys, os, datetime, zoneinfo
import prlist, spotify

# --- konfiguracja audycji ---------------------------------------------------
STATION = "trojka"
AIR_WEEKDAYS = {0, 1, 2, 3, 4}  # dni audycji: pon–pt (0=pon ... 4=pt)
WINDOW = ("14:00", "16:00")    # godziny audycji (od–do)
LOOKBACK_DAYS = 7              # okno kroczące
PLAYLIST_NAME = "W tonacji Trójki"
PLAYLIST_ID_KEY = "SPOTIFY_WTT_PLAYLIST_ID"
MATCH_THRESHOLD = 0.50
ENVF = spotify.ENVF

def log(*a): print(*a, flush=True)

def collect_window(today):
    """Utwory z okna audycji z ostatnich LOOKBACK_DAYS dni (dedup, chronologicznie)."""
    prlist.STATION = STATION
    seen, out = set(), []
    for delta in range(LOOKBACK_DAYS, -1, -1):
        d = today - datetime.timedelta(days=delta)
        if d.weekday() not in AIR_WEEKDAYS:
            continue
        for tr in prlist.scrape_day(d.isoformat()):
            if WINDOW[0] <= tr["time"] < WINDOW[1]:
                key = tr["name"].strip().lower()
                if key not in seen:
                    seen.add(key)
                    out.append({"date": d.isoformat(), **tr})
    return out

# --- playlista (te same wzorce co sync.py, endpointy z lutego 2026) ---------
def save_env_kv(key, value, path=ENVF):
    if not os.path.exists(path):
        return
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
        out, found = [], False
        for l in lines:
            if l.startswith(key + "="):
                out.append(f"{key}={value}"); found = True
            else:
                out.append(l)
        if not found: out.append(f"{key}={value}")
        open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
    except Exception:
        pass

def find_or_create_playlist(sp, env):
    uid = env.get("SPOTIFY_USER_ID")
    pid = env.get(PLAYLIST_ID_KEY)
    if pid:
        st, js = sp.get(f"/playlists/{pid}", fields="id")
        if st == 200 and js.get("id"):
            return js["id"], False
    offset = 0
    while True:
        st, js = sp.get("/me/playlists", limit=50, offset=offset)
        if st != 200: break
        for pl in js.get("items", []):
            if pl and pl.get("name") == PLAYLIST_NAME and (pl.get("owner") or {}).get("id") == uid:
                return pl["id"], False
        if js.get("next"): offset += 50
        else: break
    st, js = sp.post("/me/playlists", {
        "name": PLAYLIST_NAME, "public": False,
        "description": "W tonacji Trójki (aud. A. Szydłowskiej) — krocząco, auto.",
    })
    if st not in (200, 201):
        raise RuntimeError(f"Nie udalo sie utworzyc playlisty: {st} {js}")
    new_pid = js["id"]
    sp.put(f"/playlists/{new_pid}", {"public": False})
    return new_pid, True

def replace_tracks(sp, pid, uris):
    st, js = sp.put(f"/playlists/{pid}/items", {"uris": uris[:100]})
    if st not in (200, 201):
        raise RuntimeError(f"PUT items blad: {st} {js}")
    for i in range(100, len(uris), 100):
        st, js = sp.post(f"/playlists/{pid}/items", {"uris": uris[i:i+100]})
        if st not in (200, 201):
            raise RuntimeError(f"POST items blad: {st} {js}")

def main():
    dry = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tz = zoneinfo.ZoneInfo("Europe/Warsaw")
    today = datetime.date.fromisoformat(args[0]) if args else datetime.datetime.now(tz).date()

    log(f"== W tonacji Trójki — okno {LOOKBACK_DAYS} dni do {today} {'(DRY-RUN)' if dry else ''} ==")
    tracks = collect_window(today)
    log(f"Utworów ze slotu 14-16 (pon–pt) w oknie: {len(tracks)}")
    if not tracks:
        log("Brak utworów w oknie — nie ruszam playlisty."); return

    env = spotify.load_env()
    sp = spotify.Spotify(spotify.get_access_token(env))
    uris, matched, missed = [], [], []
    for t in tracks:
        a, ti = prlist.split_artist_title(t["name"])
        uri, cand, aids, score = spotify.search_track(sp, a, ti or t["name"])
        if uri and score >= MATCH_THRESHOLD and uri not in uris:
            uris.append(uri); matched.append((t, cand, score))
        else:
            missed.append((t, cand, score))

    log(f"Dopasowano na Spotify: {len(uris)} / {len(tracks)}\n")
    log("-- DOPASOWANE --")
    for t, cand, score in matched:
        log(f"  [{score:.2f}] {t['date']} {t['time']}  {cand}")
    if missed:
        log("\n-- NIEDOPASOWANE (pominięte) --")
        for t, cand, score in missed:
            log(f"  [{score:.2f}] {t['time']}  {t['name']}")

    if dry:
        log("\n(DRY-RUN) — nic nie zapisuję."); return

    pid, created = find_or_create_playlist(sp, env)
    if not env.get(PLAYLIST_ID_KEY):
        save_env_kv(PLAYLIST_ID_KEY, pid)
    replace_tracks(sp, pid, uris)
    desc = (f"W tonacji Trójki (audycja Agnieszki Szydłowskiej) — utwory z ostatniego "
            f"tygodnia. Krocząca aktualizacja. Źródło: radiospis.pl")
    sp.put(f"/playlists/{pid}", {"description": desc})
    st, js = sp.get(f"/playlists/{pid}", fields="external_urls")
    st2, it = sp.get(f"/playlists/{pid}/items", fields="total", limit=1)
    log(f"\n{'Utworzono' if created else 'Zaktualizowano'} '{PLAYLIST_NAME}': "
        f"{(js.get('external_urls') or {}).get('spotify')}")
    log(f"Utworów na playliscie: {it.get('total')}")

if __name__ == "__main__":
    main()
