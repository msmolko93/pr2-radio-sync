#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pobiera z radiospis.pl utwory zagrane na Dwójce (Program 2 PR) danego dnia
i klasyfikuje je na: KEEP (jazz / film / pop / etno / piosenki) vs
CLASSICAL (symfonie, koncerty, opery, kameralistyka) — którą usuwamy.

Uwaga: to na razie moduł do TESTÓW rdzenia (bez Spotify).
"""
import urllib.request
import re
import html
import sys
import unicodedata
import datetime
import zoneinfo
import time

BASE = "https://radiospis.pl"
STATION = "dwojka"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HOUR_BLOCKS = [23, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]

TRACK_RE = re.compile(
    r'href="(/piosenka/[^"]+)"[^>]*>([^<]*)</a>'      # 1=slug 2=text
    r'(?:(?!/piosenka/).)*?'                            # nie przeskakuj do kolejnego utworu
    r'<span[^>]*>(\d{2}-\d{2}-\d{4})</span>\s*'         # 3=DD-MM-YYYY
    r'<span[^>]*>(\d{2}:\d{2})</span>',                 # 4=HH:MM
    re.S,
)

# ----------------------- KLASYFIKATOR --------------------------------------
def deburr(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()

# Formy / markery muzyki klasycznej (po deburr, więc bez ogonków)
CLASSICAL_FORMS = [
    "symfonia", "symphony", "symfoniczn", "sinfonia", "sinfonietta",
    "koncert fortepianow", "koncert skrzypcow", "koncert wiolonczelow",
    "concerto", "koncert na ",
    "kwartet smyczkow", "string quartet", "streichquartett",
    "kwintet smyczkow", "kwartet fortepian", "kwintet fortepian",
    "piano quintet", "string quintet", "sinfonica",
    "sonata", "sonatina", "sonate", "partita", "suita", "suite",
    "etiuda", "etude", "preludium", "prelude", "fuga", "fugue",
    "nokturn", "nocturne", "mazurek", "polonez", "polonaise",
    "scherzo", "rondo", "kantata", "cantata", "oratorium", "oratorio",
    "requiem", " msza", " mass ", "uwertura", "overture",
    "wariacj", "variation", "bagatela", "bagatelle", "impromptu",
    "barkarola", "capriccio", "toccata", "passacaglia", "choral",
    "menuet", "minuet", "gawot", "gigue", "allemande", "courante", "sarabande",
    "kolysanka na fortepian", "wiolonczel", "klarnetow", "obojow",
    "fortepian solo", "na fortepian", "na skrzypce", "na orkiestre",
    "orkiestra symf", "filharmoni", "philharmon", "operowy", " opera",
    "smyczkow",
]
# Markery katalogowe / tonacje / części
CLASSICAL_MARKERS = [
    r"\bop\.?\s?\d", r"\bopus\b", r"\bbwv\b", r"\bkv\b", r"\bk\.\s?\d",
    r"\bhob\b", r"\brv\b", r"\bwq\b", r"\bd\.\s?\d", r"\bwoo\b",
    r"\bcz\.?\s?(i{1,3}v?|vi{0,3}|ix|x)\b",     # cz. I / II / III / IV ...
    r"\b(allegro|andante|adagio|moderato|vivace|presto|largo|larghetto|"
    r"lento|grave|andantino|allegretto|maestoso)\b",
    r"\b[a-h](-| )?(dur|moll)\b",               # C-dur, a-moll, Es-dur
    r"\b(major|minor)\b",
    r"\bnr\s?\d+\b.*\b(op|bwv|kv)\b",
    r"\baria\b", r"\bklawesyn\b", r"\bharpsichord\b",
]
# Znani kompozytorzy klasyczni (surname fragments, po deburr)
CLASSICAL_COMPOSERS = [
    "bach", "mozart", "beethoven", "chopin", "schubert", "brahms", "haydn",
    "handel", "haendel", "vivaldi", "liszt", "wagner", "czajkowski",
    "tchaikovsky", "dvorak", "debussy", "ravel", "mahler", "schumann",
    "mendelssohn", "grieg", "sibelius", "rachmanin", "prokofiew", "prokofiev",
    "szostakowicz", "shostakovich", "lutoslawski", "penderecki", "gorecki",
    "szymanowski", "bacewicz", "moniuszko", "paganini", "rossini", "verdi",
    "puccini", "bizet", "saint-saens", "faure", "poulenc", "bartok",
    "janacek", "elgar", "holst", "britten", "purcell", "telemann",
    "scarlatti", "monteverdi", "corelli", "albinoni", "pachelbel", "bruckner",
    "berlioz", "weber", "hummel", "clementi", "czerny", "musorgski",
    "mussorgsky", "rimski", "borodin", "smetana", "franck", "gounod",
    "massenet", "offenbach", "donizetti", "bellini", "wieniawski",
    "paderewski", "schoenberg", "schonberg", "webern", "messiaen", "ligeti",
    "part ", "silvestrov", "skoryk", "bujarski", "leoncavallo", "faure",
    "tallis", "palestrina", "byrd", "gluck", "boccherini", "cherubini",
    "dowland", "couperin", "rameau", "lully", "buxtehude", "krenek",
    "hindemith", "stravinsky", "strawinski", "berg ", "kilar",
    "respighi", "moszkowski", "stamitz", "wajnberg", "weinberg",
    "panufnik", "mykietyn", "kisielewski", "szeligowski", "spisak",
    "bloch ", "enescu", "granados", "albeniz", "turina", "villa-lobos",
]
# Nadpisania KEEP — nawet jeśli brzmi klasycznie, zostaw (film/jazz)
KEEP_OVERRIDES = [
    "z filmu", "muzyka z filmu", "soundtrack", "ost ", " ost", "theme from",
    "motyw z", "sciezka dzwiekowa", "film music", "muzyka filmowa",
    "temat z", "czolowka",
]

def classify(text: str):
    """Zwraca ('classical'|'keep', powod)."""
    t = " " + deburr(text) + " "
    # 1) KEEP override (film) — ma pierwszenstwo
    for kw in KEEP_OVERRIDES:
        if kw in t:
            return ("keep", f"film-override:{kw.strip()}")
    # 2) sygnaly klasyczne
    for kw in CLASSICAL_FORMS:
        if kw in t:
            return ("classical", f"forma:{kw.strip()}")
    for pat in CLASSICAL_MARKERS:
        m = re.search(pat, t)
        if m:
            return ("classical", f"marker:{m.group(0).strip()}")
    for comp in CLASSICAL_COMPOSERS:
        if comp in t:
            return ("classical", f"kompozytor:{comp.strip()}")
    # 3) domyslnie zostaw (jazz/pop/etno/piosenki nie maja tych markerow)
    return ("keep", "brak-sygnalow-klasycznych")

# ----------------------- SCRAPER -------------------------------------------
def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", "replace")

def scrape_day(date_iso: str):
    dd, mm, yyyy = date_iso.split("-")[2], date_iso.split("-")[1], date_iso.split("-")[0]
    dmy = f"{dd}-{mm}-{yyyy}"
    seen = {}
    for H in HOUR_BLOCKS:
        url = f"{BASE}/stacja/{STATION}/playlista/data/{date_iso}/godzina/{H}"
        try:
            page = fetch(url)
        except Exception as e:
            print(f"  ! blad pobierania {url}: {e}", file=sys.stderr)
            continue
        for slug, txt, d, tm in TRACK_RE.findall(page):
            if d != dmy:
                continue
            name = html.unescape(txt).strip()
            key = (tm, name.lower())
            if key not in seen:
                seen[key] = {"time": tm, "name": name, "slug": slug}
        time.sleep(0.35)   # grzeczność wobec radiospis (unikamy throttlingu)
    return sorted(seen.values(), key=lambda x: x["time"])

def split_artist_title(name: str):
    if " - " in name:
        a, t = name.split(" - ", 1)
        return a.strip(), t.strip()
    return name.strip(), ""

# ----------------------- MAIN (test) ---------------------------------------
def main():
    if len(sys.argv) > 1:
        date_iso = sys.argv[1]
    else:
        tz = zoneinfo.ZoneInfo("Europe/Warsaw")
        y = datetime.datetime.now(tz).date() - datetime.timedelta(days=1)
        date_iso = y.isoformat()

    print(f"== Dwojka — playlista {date_iso} (radiospis.pl) ==\n")
    tracks = scrape_day(date_iso)
    if not tracks:
        print("Brak utworow (dzien poza archiwum lub pusto).")
        return
    times = [t["time"] for t in tracks]
    kept, removed = [], []
    for tr in tracks:
        verdict, reason = classify(tr["name"])
        (kept if verdict == "keep" else removed).append((tr, reason))

    print(f"Wszystkich utworow: {len(tracks)}  (zakres {times[0]}–{times[-1]})")
    print(f"  ZOSTAJE (jazz/film/pop/etno): {len(kept)}")
    print(f"  USUNIETE (klasyka):           {len(removed)}\n")

    print("----- ZOSTAJE (trafi na Spotify) -----")
    for tr, reason in kept:
        a, t = split_artist_title(tr["name"])
        print(f"  {tr['time']}  {a}  ||  {t}    [{reason}]")

    print("\n----- USUNIETE (klasyka, odfiltrowane) -----")
    for tr, reason in removed[:40]:
        print(f"  {tr['time']}  {tr['name'][:70]}   [{reason}]")
    if len(removed) > 40:
        print(f"  ... i {len(removed)-40} wiecej")

if __name__ == "__main__":
    main()
