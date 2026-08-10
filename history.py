#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trwała historia 7 dni (JSON w repo). Klucz = data (YYYY-MM-DD),
wartość = lista utworów {name, uri, time}. Trzymamy tylko DOPASOWANE (z uri)."""
import json, os, datetime

def load(path):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)

def prune(hist, end_date, lookback_days):
    """Zostaw tylko dni z okna [end-(lookback-1) .. end]."""
    cutoff = (end_date - datetime.timedelta(days=lookback_days - 1)).isoformat()
    end = end_date.isoformat()
    return {d: v for d, v in hist.items() if cutoff <= d <= end}

def known_uri(hist, name):
    """Jeśli ten sam utwór był już kiedyś dopasowany — zwróć uri (bez ponownego szukania)."""
    k = name.strip().lower()
    for day in hist.values():
        for t in day:
            if t["name"].strip().lower() == k:
                return t["uri"]
    return None

def all_uris(hist):
    """URI-e do playlisty: dedup po nazwie, najnowsze dni na górze."""
    seen, uris = set(), []
    for d in sorted(hist.keys(), reverse=True):
        for t in hist[d]:
            k = t["name"].strip().lower()
            if k in seen:
                continue
            seen.add(k)
            uris.append(t["uri"])
    return uris
