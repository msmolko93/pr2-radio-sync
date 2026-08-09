# PR2 Radio Sync

Codziennie rano buduje prywatną playlistę **PR2** na Spotify z utworów zagranych
poprzedniego dnia w **Dwójce** (Program 2 Polskiego Radia) — **z wyłączeniem muzyki
klasycznej** (zostają jazz, muzyka filmowa, folk/etno, pop).

## Jak to działa

1. **Pobieranie** (`prlist.py`) — ściąga listę utworów Dwójki z danego dnia z
   serwisu **radiospis.pl** (12 dwugodzinnych bloków, filtrowane po dokładnej dacie).
   *Uwaga:* oficjalne API Polskiego Radia (`apipr.polskieradio.pl`) było w trakcie
   budowy wyłączone — dlatego źródłem jest radiospis.pl.
2. **Filtr klasyki** (`prlist.py: classify`) — heurystyka po formach (symfonia,
   koncert, sonata, opus/BWV, „Cz. II"…), tonacjach i nazwiskach kompozytorów.
   Zostawia jazz i muzykę filmową. Nie jest idealna — patrz „Dostrajanie".
3. **Dopasowanie do Spotify** (`spotify.py: search_track`) — wyszukiwarka + scoring
   (0.6·tytuł + 0.4·wykonawca), próg `MATCH_THRESHOLD = 0.50`. Utwory spoza Spotify
   są pomijane.
4. **Aktualizacja playlisty** (`sync.py`) — podmienia całą zawartość PR2
   (`PUT /playlists/{id}/items`). Playlista jest **prywatna**.

Kod używa wyłącznie biblioteki standardowej Pythona — **zero zależności**.

## Uruchomienie w chmurze (GitHub Actions)

Workflow `.github/workflows/pr2-sync.yml` odpala się codziennie o **05:00 UTC**
(≈ 07:00 czasu polskiego latem, 06:00 zimą) oraz na żądanie (zakładka *Actions →
Run workflow*).

Wymagane **sekrety** repozytorium (*Settings → Secrets and variables → Actions*):

| Nazwa | Opis |
|------|------|
| `SPOTIFY_CLIENT_ID` | Client ID aplikacji Spotify |
| `SPOTIFY_CLIENT_SECRET` | Client Secret aplikacji Spotify |
| `SPOTIFY_REFRESH_TOKEN` | Token odświeżający (z jednorazowej autoryzacji) |
| `SPOTIFY_PLAYLIST_ID` | ID playlisty PR2 |

> **Token żyje 180 dni.** Po tym czasie trzeba go odnowić: uruchom lokalnie
> `python3 auth_once.py`, zaloguj się i podmień sekret `SPOTIFY_REFRESH_TOKEN`.

## Uruchomienie lokalne

```bash
# jednorazowa autoryzacja -> zapisuje token do secrets.env
python3 auth_once.py

# podgląd bez zapisu na Spotify
python3 sync.py --dry-run

# konkretny dzień
python3 sync.py 2026-08-08

# domyślnie: wczoraj (Europe/Warsaw)
python3 sync.py
```

Lokalnie konfiguracja czytana jest z pliku `secrets.env` (nie commitować!).
W chmurze — ze zmiennych środowiskowych (sekrety GitHub mają pierwszeństwo).

## Dostrajanie filtra klasyki

W `prlist.py`:
- `CLASSICAL_FORMS`, `CLASSICAL_MARKERS`, `CLASSICAL_COMPOSERS` — sygnały „to klasyka".
- `KEEP_OVERRIDES` — wyjątki „zostaw mimo wszystko" (np. muzyka filmowa).

Próg dopasowania do Spotify: `MATCH_THRESHOLD` w `sync.py`.
