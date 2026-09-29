# Publikacja: propozycja

Status: 2026-09-29, propozycja, niewdrożone.

## Propozycja

Projekt zostaje lokalnym narzędziem CLI uruchamianym ręcznie w sezonie; nie ma interfejsu WWW, więc nie potrzebuje domeny ani hostingu. Opcjonalnie, tylko w fazie ligowej pucharów UEFA, scraper kursów soccer-rating.com może działać na współdzielonym serwerze `vps-waw` jako timer systemd o niskiej częstotliwości (np. raz dziennie), z wynikami w `/var/lib/uefa-cups-predictor`. Analiza (`analyze.py`, raport Excel) zostaje lokalna. Poza sezonem timer jest wyłączony.

## Kroki wdrożenia

Tylko wariant opcjonalny (serwer), według konwencji z `/opt/SERVER.md`:

1. Przed wdrożeniem: sprawdzić `robots.txt` i regulamin soccer-rating.com oraz zastąpić nagłówek `User-Agent` przeglądarki w `src/scraping/fetcher.py` jawnym identyfikatorem narzędzia (ze wspólnego adresu serwera podszywanie się pod przeglądarkę jest trudniejsze do obrony niż z adresu domowego).
2. Użytkownik systemowy `uefa-cups-predictor`, checkout w `/opt/uefa-cups-predictor` przez klucz wdrożeniowy tylko do odczytu (alias `github-uefa-cups-predictor`), venv jako administrator: `sudo apt install -y python3-venv` (Debian 13 nie ma `ensurepip`), `python3 -m venv /opt/uefa-cups-predictor/.venv`, `.venv/bin/pip install -r requirements.txt`.
3. Usługa `uefa-cups-predictor-scrape.service` (`Type=oneshot`, `StateDirectory=uefa-cups-predictor`, `WorkingDirectory=/opt/uefa-cups-predictor`, utwardzenie według konwencji serwera), polecenie: `.venv/bin/python -m src.scraping.soccer_rating_cli --all-leagues --skip-cups --separate-snapshots --min-start 20 --max-start 700 --delay 3 --output-dir /var/lib/uefa-cups-predictor/soccer-rating`.
4. Timer `uefa-cups-predictor-scrape.timer`: raz dziennie w godzinie, która nie nakłada się na inne zadania okresowe serwera (rejestr w `/opt/SERVER.md`; proponowany termin rossmann-scraper: środa wieczorem) ani na restart po aktualizacjach (03:30 UTC), np. `OnCalendar=*-*-* 10:30 Europe/Warsaw`, `Persistent=true`, `RandomizedDelaySec=10min`.
5. Budżet zasobów (drop-in): `MemoryHigh=256M`, `MemoryMax=384M`, `TasksMax=32`, `CPUWeight=30` (założenie do weryfikacji pierwszym przebiegiem).
6. Pobieranie wyników na komputer lokalny do analizy: `scp` lub `rsync` z `/var/lib/uefa-cups-predictor/soccer-rating/`.
7. Wpis w rejestrze `/opt/SERVER.md`; włączanie timera na fazę ligową i wyłączanie po niej (`systemctl enable --now` / `disable --now`).

## Wymagane decyzje właściciela

- Czy wariant serwerowy jest potrzebny, czy wystarcza ręczny przebieg lokalny w sezonie (rekomendacja: lokalnie, dopóki ręczny przebieg nie jest uciążliwy).
- Częstotliwość przebiegów w sezonie.
- Domena: niepotrzebna.

## Ryzyka i koszty

- Koszt: brak dodatkowego (serwer już opłacony).
- Wspólny adres IP: zbyt częste pobieranie może doprowadzić do blokady adresu serwera przez soccer-rating.com lub usługi antybotowe; ograniczają to odstęp między zapytaniami i jeden przebieg dziennie.
- Precedens z 2026-09-29: sklep alexandria-fragrances (za Cloudflare) odpowiadał z adresu tego serwera kodem 429 na około 40-50% zapytań, nawet przy 1 zapytaniu na 25 s. Przed włączeniem timera sprawdzić ręcznym przebiegiem, czy soccer-rating.com nie ogranicza adresu serwera.
- Regulamin źródła niesprawdzony (punkt 1).
- Parsery zależą od markupu strony; nieudany przebieg na serwerze trzeba zauważyć (check w Healthchecks.io zgodnie z konwencją serwera).
