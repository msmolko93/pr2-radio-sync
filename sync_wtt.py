#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W tonacji Trójki — pon–pt 14:00-16:00, okno kroczące 7 dni (cache historii).
Cienki wrapper na rolling.py.

  python3 sync_wtt.py            # dziś (Europe/Warsaw)
  python3 sync_wtt.py --dry-run
"""
import sys, os, datetime, zoneinfo
import spotify, rolling

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = {
    "station": "trojka",
    "weekdays": {0, 1, 2, 3, 4},      # pon–pt
    "time_window": ("14:00", "16:00"),
    "use_classifier": False,          # audycja muzyczna — zostawiamy wszystko
    "lookback_days": 7,
    "end_offset": 0,                  # okno kończy się DZIŚ
    "refresh_recent": 2,              # 2 najnowsze dni zawsze świeżo
    "playlist_name": "W tonacji Trójki",
    "playlist_id_key": "SPOTIFY_WTT_PLAYLIST_ID",
    "history_file": os.path.join(HERE, "state", "wtt_history.json"),
    "description": ("W tonacji Trójki (audycja Agnieszki Szydłowskiej) — utwory z "
                    "ostatniego tygodnia (pon–pt). Krocząca aktualizacja. Źródło: radiospis.pl"),
    "match_threshold": 0.50,
}

def main():
    dry = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tz = zoneinfo.ZoneInfo("Europe/Warsaw")
    today = datetime.date.fromisoformat(args[0]) if args else datetime.datetime.now(tz).date()
    env = spotify.load_env()
    sp = spotify.Spotify(spotify.get_access_token(env))
    rolling.run(sp, env, CFG, today, dry=dry)

if __name__ == "__main__":
    main()
