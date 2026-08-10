#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PR2 sync — glowny pipeline.
1) pobierz utwory Dwojki z poprzedniego dnia (radiospis.pl)
2) odfiltruj klasyke (heurystyka)
3) dopasuj do Spotify
4) znajdz/utworz prywatna playliste "PR2" i podmien jej zawartosc

Uzycie:
  python3 sync.py            # wczoraj (Europe/Warsaw)
  python3 sync.py 2026-08-08 # konkretny dzien
  python3 sync.py --dry-run  # bez zapisu na Spotify
"""
import sys, os, datetime, zoneinfo
import prlist
import spotify

PLAYLIST_NAME = "PR2"
MATCH_THRESHOLD = 0.50
LOOKBACK_DAYS = 7        # okno kroczące (dni wstecz)
ENVF = spotify.ENVF

def log(*a): print(*a, flush=True)

def save_env_kv(key, value, path=ENVF):
    # W chmurze (brak pliku) nie zapisujemy — ID przekazywane przez sekret.
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
    # 1) zapisany ID
    pid = env.get("SPOTIFY_PLAYLIST_ID")
    if pid:
        st, js = sp.get(f"/playlists/{pid}", fields="id,name,owner(id)")
        if st == 200 and js.get("id"):
            return js["id"], False
    # 2) szukaj wsrod playlist uzytkownika (paginacja przez offset)
    offset = 0
    while True:
        st, js = sp.get("/me/playlists", limit=50, offset=offset)
        if st != 200: break
        for pl in js.get("items", []):
            if pl and pl.get("name") == PLAYLIST_NAME and (pl.get("owner") or {}).get("id") == uid:
                return pl["id"], False
        if js.get("next"): offset += 50
        else: break
    # 3) utworz (endpoint od lutego 2026: POST /me/playlists)
    st, js = sp.post("/me/playlists", {
        "name": PLAYLIST_NAME, "public": False,
        "description": "Dwojka (Program 2 PR) bez klasyki — auto.",
    })
    if st not in (200, 201):
        raise RuntimeError(f"Nie udalo sie utworzyc playlisty: {st} {js}")
    new_pid = js["id"]
    sp.put(f"/playlists/{new_pid}", {"public": False})  # wymus prywatna
    return new_pid, True

def replace_tracks(sp, pid, uris):
    # PUT /items podmienia cala zawartosc; max 100 na request (endpoint od lutego 2026)
    first = uris[:100]
    st, js = sp.put(f"/playlists/{pid}/items", {"uris": first})
    if st not in (200, 201):
        raise RuntimeError(f"PUT items blad: {st} {js}")
    for i in range(100, len(uris), 100):
        st, js = sp.post(f"/playlists/{pid}/items", {"uris": uris[i:i+100]})
        if st not in (200, 201):
            raise RuntimeError(f"POST items blad: {st} {js}")

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    dry = "--dry-run" in flags
    tz = zoneinfo.ZoneInfo("Europe/Warsaw")
    end = datetime.date.fromisoformat(args[0]) if args else (
        datetime.datetime.now(tz).date() - datetime.timedelta(days=1))
    # okno kroczące: 'end' i wcześniejsze dni, łącznie LOOKBACK_DAYS
    dates = [(end - datetime.timedelta(days=i)).isoformat() for i in range(LOOKBACK_DAYS)]

    log(f"== PR2 sync — okno kroczące {LOOKBACK_DAYS} dni ({dates[-1]} .. {dates[0]}) "
        f"{'(DRY-RUN)' if dry else ''} ==")
    keep, seen_names, total = [], set(), 0
    for d in dates:
        day_tracks = prlist.scrape_day(d)
        total += len(day_tracks)
        for tr in day_tracks:
            verdict, reason = prlist.classify(tr["name"])
            if verdict != "keep":
                continue
            key = tr["name"].strip().lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            a, t = prlist.split_artist_title(tr["name"])
            keep.append({"time": tr["time"], "artist": a, "title": t,
                         "raw": tr["name"], "date": d})
    log(f"Pobrano {total} utworow z {LOOKBACK_DAYS} dni; "
        f"po filtrze klasyki i dedup zostaje {len(keep)}.")

    env = spotify.load_env()
    sp = spotify.Spotify(spotify.get_access_token(env))

    uris, seen, matched, missed = [], set(), [], []
    for k in keep:
        uri, cand, aids, score = spotify.search_track(sp, k["artist"], k["title"] or k["raw"])
        if uri and score >= MATCH_THRESHOLD:
            if uri not in seen:
                seen.add(uri); uris.append(uri)
                matched.append((k, cand, score))
        else:
            missed.append((k, cand, score))

    log(f"Dopasowano na Spotify: {len(uris)} / {len(keep)}")
    log("\n-- DOPASOWANE (ida na playliste) --")
    for k, cand, score in matched:
        log(f"  [{score:.2f}] {k['date']} {k['time']}  {cand}")
    if missed:
        log("\n-- NIEDOPASOWANE (pominiete) --")
        for k, cand, score in missed:
            log(f"  [{score:.2f}] {k['time']}  {k['artist']} — {k['title']}  (najblizsze: {cand})")

    if dry:
        log("\n(DRY-RUN) — nic nie zapisuje na Spotify.")
        return
    if not uris:
        log("\nBrak dopasowanych utworow — nie ruszam playlisty.")
        return

    pid, created = find_or_create_playlist(sp, env)
    if not env.get("SPOTIFY_PLAYLIST_ID"):
        save_env_kv("SPOTIFY_PLAYLIST_ID", pid)
    replace_tracks(sp, pid, uris)
    desc = (f"Dwojka (Program 2 PR) — utwory z ostatnich {LOOKBACK_DAYS} dni bez muzyki "
            f"klasycznej. Krocząca aktualizacja. Zrodlo: radiospis.pl")
    sp.put(f"/playlists/{pid}", {"description": desc})
    st, js = sp.get(f"/playlists/{pid}", fields="external_urls,name")
    url = (js.get("external_urls") or {}).get("spotify", f"spotify:playlist:{pid}")
    st2, it = sp.get(f"/playlists/{pid}/items", fields="total", limit=1)
    log(f"\n{'Utworzono' if created else 'Zaktualizowano'} playliste '{PLAYLIST_NAME}': {url}")
    log(f"Utworow na playliscie: {it.get('total')}")

if __name__ == "__main__":
    main()
