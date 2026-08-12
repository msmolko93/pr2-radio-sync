#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wspólny silnik playlist kroczących z cache historii.
Każdy bieg scrapuje tylko dni, których NIE ma w historii (+ zawsze najnowszy dzień),
resztę bierze z zapisanej historii → mało zapytań, brak throttlingu."""
import datetime
import prlist, spotify, history

def log(*a): print(*a, flush=True)

# ---- playlista (endpointy z lutego 2026) ----------------------------------
def find_or_create(sp, env, cfg):
    uid = env.get("SPOTIFY_USER_ID")
    pid = env.get(cfg["playlist_id_key"])
    if pid:
        st, js = sp.get(f"/playlists/{pid}", fields="id")
        if st == 200 and js.get("id"):
            return js["id"], False
    offset = 0
    while True:
        st, js = sp.get("/me/playlists", limit=50, offset=offset)
        if st != 200:
            break
        for pl in js.get("items", []):
            if pl and pl.get("name") == cfg["playlist_name"] and \
               (uid is None or (pl.get("owner") or {}).get("id") == uid):
                return pl["id"], False
        if js.get("next"):
            offset += 50
        else:
            break
    st, js = sp.post("/me/playlists", {"name": cfg["playlist_name"], "public": False,
                                       "description": cfg["description"]})
    if st not in (200, 201):
        raise RuntimeError(f"Nie udalo sie utworzyc playlisty: {st} {js}")
    pid = js["id"]
    sp.put(f"/playlists/{pid}", {"public": False})
    return pid, True

def replace_items(sp, pid, uris):
    st, js = sp.put(f"/playlists/{pid}/items", {"uris": uris[:100]})
    if st not in (200, 201):
        raise RuntimeError(f"PUT items blad: {st} {js}")
    for i in range(100, len(uris), 100):
        st, js = sp.post(f"/playlists/{pid}/items", {"uris": uris[i:i+100]})
        if st not in (200, 201):
            raise RuntimeError(f"POST items blad: {st} {js}")

# ---- silnik ----------------------------------------------------------------
def run(sp, env, cfg, today, dry=False):
    prlist.STATION = cfg["station"]
    end = today - datetime.timedelta(days=cfg.get("end_offset", 0))
    window = [end - datetime.timedelta(days=i) for i in range(cfg["lookback_days"])]  # [0]=najnowszy
    hist = history.load(cfg["history_file"])

    scraped_days, searched, from_cache = 0, 0, 0
    for idx, d in enumerate(window):
        ds = d.isoformat()
        weekdays = cfg.get("weekdays")
        if weekdays is not None and d.weekday() not in weekdays:
            continue                      # nie dzień audycji — pomijamy (bez scrapowania)
        if ds in hist and idx >= cfg.get("refresh_recent", 2):
            from_cache += 1               # starszy dzień już w cache
            continue
        # scrapujemy świeżo (brakujący dzień albo najnowszy)
        entries = []
        for tr in prlist.scrape_day(ds):
            tw = cfg.get("time_window")
            if tw and not (tw[0] <= tr["time"] < tw[1]):
                continue
            if cfg.get("use_classifier") and prlist.classify(tr["name"])[0] != "keep":
                continue
            name = tr["name"]
            uri = history.known_uri(hist, name)      # reużyj dopasowania jeśli było
            if uri is None:
                a, t = prlist.split_artist_title(name)
                u, cand, aids, score = spotify.search_track(sp, a, t or name)
                searched += 1
                uri = u if (u and score >= cfg["match_threshold"]) else None
            if uri:
                entries.append({"name": name, "uri": uri, "time": tr["time"]})
        hist[ds] = entries
        scraped_days += 1

    hist = history.prune(hist, end, cfg["lookback_days"])
    uris = history.all_uris(hist)
    log(f"{cfg['playlist_name']}: dni świeżo={scraped_days}, z cache={from_cache}, "
        f"nowych wyszukiwań Spotify={searched} → {len(uris)} utworów na playliście")
    if dry:
        return {"tracks": len(uris)}

    history.save(cfg["history_file"], hist)
    pid, created = find_or_create(sp, env, cfg)
    replace_items(sp, pid, uris)
    sp.put(f"/playlists/{pid}", {"description": cfg["description"]})
    st, js = sp.get(f"/playlists/{pid}", fields="external_urls")
    log(f"{'Utworzono' if created else 'Zaktualizowano'} '{cfg['playlist_name']}': "
        f"{(js.get('external_urls') or {}).get('spotify')} ({len(uris)} utw.)")
    return {"tracks": len(uris), "pid": pid}
