#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PR2 (Dwójka) — krocząca playlista 7 dni bez klasyki (cache historii).
Cienki wrapper na rolling.py.

  python3 sync.py            # dziś (Europe/Warsaw)
  python3 sync.py --dry-run
  python3 sync.py 2026-08-10 # udawany "dziś"
"""
import sys, os, datetime, zoneinfo
import spotify, rolling

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = {
    "station": "dwojka",
    "weekdays": None,                 # wszystkie dni tygodnia
    "time_window": None,              # cały dzień
    "use_classifier": True,           # wytnij muzykę klasyczną
    "lookback_days": 7,
    "end_offset": 1,                  # okno kończy się na WCZORAJ
    "refresh_recent": 2,              # 2 najnowsze dni zawsze świeżo
    "playlist_name": "PR2",
    "playlist_id_key": "SPOTIFY_PLAYLIST_ID",
    "history_file": os.path.join(HERE, "state", "pr2_history.json"),
    "description": ("Dwojka (Program 2 PR) — utwory z ostatnich 7 dni bez muzyki "
                    "klasycznej. Krocząca aktualizacja. Zrodlo: radiospis.pl"),
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
