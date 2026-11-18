"""The results page's Polish texts and the helpers that write numbers, dates and links the way Polish text does.

Texts that hold HTML (the hint, the key points, the footer) are trusted page markup; every value from the inputs goes
through `html.escape` before it joins them.
"""

import re
import unicodedata
from collections.abc import Sequence
from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo

from analyzer.config import PAGE_TIMEZONE, SITE_TIMEZONE, SOCCER_RATING_SITE
from analyzer.page.model import Level

# Characters ruff takes for look-alikes of ASCII ones (RUF001), so they are built from their code points
MINUS = chr(0x2212)  # U+2212 MINUS SIGN
EN_DASH = chr(0x2013)  # U+2013 EN DASH, for ranges of days
_DOTLESS_I = chr(0x131)  # U+0131 LATIN SMALL LETTER DOTLESS I (Turkish names)
# Weekdays from Monday, as `date.weekday()` counts them
WEEKDAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")
# "On <weekday>" in the same order, with the preposition the weekday takes
ON_WEEKDAYS = ("w poniedziałek", "we wtorek", "w środę", "w czwartek", "w piątek", "w sobotę", "w niedzielę")
# Month names in the genitive, as a date writes them ("18 listopada")
MONTHS = (
    "stycznia",
    "lutego",
    "marca",
    "kwietnia",
    "maja",
    "czerwca",
    "lipca",
    "sierpnia",
    "września",
    "października",
    "listopada",
    "grudnia",
)

# Report label suffix -> level; the report labels carry a coloured marker before the suffix
_LABEL_LEVELS: dict[str, Level] = {
    "STRONG BUY": "strong",
    "CONSIDER": "consider",
    "NEUTRAL": "neutral",
    "CAUTION": "caution",
    "AVOID": "avoid",
}
# The order is the ranking order
LEVEL_NAMES: dict[Level, str] = {
    "strong": "mocny",
    "consider": "do rozważenia",
    "neutral": "neutralny",
    "caution": "ostrożnie",
    "avoid": "unikaj",
}
LEVEL_RANKS = {level: rank for rank, level in enumerate(LEVEL_NAMES)}
CUP_NAMES = {"cl": "Liga Mistrzów", "el": "Liga Europy", "ecl": "Liga Konferencji"}
# Report prefix -> the cup's path on theanalyst.com, for the link to its predictions
ANALYST_SLUGS = {"cl": "uefa-champions-league", "el": "uefa-europa-league", "ecl": "uefa-conference-league"}
STATUS_NAMES = {
    "IN_PLAY": "gra o awans",
    "LOCKED_DIRECT_RO16": "pewny awans do 1/8",
    "LOCKED_PLAYOFFS": "pewne baraże",
    "OUT": "bez szans",
}
# Signal text in a report -> key of its explanation in TERMS
SIGNAL_TERMS = (
    ("Sure Bet Pattern", "sure"),
    ("Strong Expert Signal", "strongsig"),
    ("Positive Signal", "possig"),
    ("Steam (+)", "steamup"),
    ("Steam (-)", "steamdown"),
    ("Strange Odds", "strange"),
    ("SR Edge", "edge"),
    ("Market Confidence", "market"),
    ("(Risk: Rising Odds)", "rising"),
    ("(No Steam Confirmation)", "nosteam"),
    ("Out of contention", "outsig"),
    ("High rotation risk", "rotsig"),
    ("Status LOCKED", "lockedsig"),
    ("High Value", "highval"),
    ("Good Value", "goodval"),
    ("Close(", "aofair"),
)
# Signal key -> its name in the signal filter
SIGNAL_NAMES = {
    "sure": "Sure Bet Pattern",
    "strongsig": "Strong Expert Signal",
    "possig": "Positive Signal",
    "steamup": "Steam (+)",
    "steamdown": "Steam (" + MINUS + ")",
    "strange": "Strange Odds",
    "edge": "SR Edge",
    "market": "Market Confidence",
    "rising": "Risk: Rising Odds",
    "nosteam": "No Steam Confirmation",
    "outsig": "Out of contention",
    "rotsig": "High rotation risk",
    "lockedsig": "Status LOCKED",
    "highval": "High Value",
    "goodval": "Good Value",
    "aofair": "Close / Fair",
}
# Raw status codes in signals are long and unbreakable; the page shows them short (the explanation names them)
SIGNAL_SHORT = {
    "Status LOCKED_DIRECT_RO16": "Status LOCKED: 1/8",
    "Status LOCKED_PLAYOFFS": "Status LOCKED: baraże",
}
# Explanations shown on tap: key -> (title, text); the page script reads them as JSON. In "levels", a [level] before
# a quoted name stands for that level's marker.
TERMS: dict[str, tuple[str, str]] = {
    "pick": (
        "Typ",
        (
            "Wynik, na który wskazuje model. 1 to wygrana gospodarzy. X to remis. 2 to wygrana gości. Obok stoi "
            "drużyna, której dotyczy typ. W europejskich pucharach typem jest drużyna z lepszą rekomendacją. Przy "
            "równej rekomendacji wybierana jest drużyna z wyższą wartością."
        ),
    ),
    "score": (
        "Ocena",
        (
            "Ocena soccer-rating dla drużyny z typu. Łączy różnicę ratingów, kurs zamknięcia, ruch kursów i "
            "różnicę szans. W europejskich pucharach dochodzą składy. Powyżej 0 model wskazuje tę drużynę. "
            "Powyżej 0,50 to wyraźny sygnał. Powyżej 1,50 to mocny sygnał. Ocena zależy głównie od kursu. Wysoka "
            "ocena zwykle oznacza faworyta, a nie okazję. Okazję pokazuje „Przewaga modelu” w szczegółach meczu."
        ),
    ),
    "signals": ("Sygnały tego meczu", ""),
    "levels": (
        "Rekomendacja",
        (
            "Poziomy: [strong]„mocny”, [consider]„do rozważenia”, „neutralny” bez znacznika. W europejskich "
            "pucharach także [caution]„ostrożnie” i [avoid]„unikaj”. Dotknij poziomu przy meczu, aby zobaczyć, "
            "skąd się wziął."
        ),
    ),
    "strong": (
        "Mocny",
        (
            "Najwyższy poziom. W europejskich pucharach daje go wysoka wartość albo mocny sygnał, jeśli spełnione "
            "są jeszcze trzy warunki. Model wskazuje tę drużynę. Kurs na nią nie rośnie. Jej motywacja wynosi co "
            "najmniej 50 i jest wyższa niż motywacja rywala. Daje go też wzorzec „Sure Bet Pattern”, w pucharach "
            "tylko wtedy, gdy model wskazuje tę drużynę i spełniony jest ten sam warunek motywacji. Zakładka "
            "„Soccer-rating” nie zna motywacji, więc tam poziom „mocny” daje tylko „Sure Bet Pattern”. Dlatego "
            "typ „mocny” może mieć niższą ocenę niż typ „do rozważenia”."
        ),
    ),
    "consider": (
        "Do rozważenia",
        (
            "Model wskazuje tę drużynę i spełniony jest co najmniej jeden warunek. Ocena powyżej 0,50. Przewaga "
            "modelu powyżej 4 punktów procentowych. W europejskich pucharach także wartość co najmniej 50. Tu "
            "trafia też mocny sygnał, którego rynek nie potwierdza."
        ),
    ),
    "neutral": (
        "Neutralny",
        "Typ nie spełnia warunków poziomów „mocny” ani „do rozważenia”. Sygnały obok mówią, co model jednak widzi.",
    ),
    "sure": (
        "Sure Bet Pattern",
        (
            "Trzy warunki naraz. Kurs zamknięcia jest niższy niż 2,00. Kurs uczciwy według modelu jest niższy niż "
            "2,20. Kurs na typ spadł od otwarcia wyraźniej niż kurs na rywala. W zakładce „Soccer-rating” zawsze "
            "daje poziom „mocny”. W europejskich pucharach tylko wtedy, gdy model wskazuje tę drużynę, a jej "
            "motywacja wynosi co najmniej 50 i jest wyższa niż motywacja rywala."
        ),
    ),
    "strongsig": (
        "Strong Expert Signal",
        (
            "Ocena drużyny przekracza 1,50. To mocny sygnał modelu na jej korzyść. Drużyna, przeciw której "
            "przemawia ocena, go nie dostaje."
        ),
    ),
    "possig": (
        "Positive Signal",
        (
            "Ocena drużyny przekracza 0,50. To wyraźny sygnał modelu na jej korzyść. Drużyna, przeciw której "
            "przemawia ocena, go nie dostaje."
        ),
    ),
    "steamup": (
        "Steam (+)",
        (
            "Kurs na tę drużynę spadł od otwarcia wyraźniej niż kurs na rywala. Rynek coraz mocniej na nią "
            "stawia. To dobry znak dla typu."
        ),
    ),
    "steamdown": (
        SIGNAL_NAMES["steamdown"],
        "Kurs na tę drużynę wzrósł względem kursu na rywala. Rynek się od niej odwraca. To zły znak dla typu.",
    ),
    "strange": (
        "Strange Odds",
        (
            "Wskaźnik AO z soccer-rating.com jest nietypowy: przekracza 30 w jedną lub drugą stronę. Liczba w "
            "nawiasie to jego wartość. Może wskazywać ukryty czynnik, np. kontuzję. Nie wiadomo, której drużyny "
            "dotyczy. W europejskich pucharach podnosi ryzyko rotacji obu drużyn o 10%."
        ),
    ),
    "edge": (
        "SR Edge",
        (
            "„Przewaga modelu” przekracza 4 punkty procentowe. Model ocenia szansę typu wyżej niż rynek. To dobry "
            "znak dla typu."
        ),
    ),
    "market": (
        "Market Confidence",
        (
            f"„Przewaga modelu” jest niższa niż {MINUS}5 punktów procentowych. Rynek ocenia szansę typu wyżej "
            "niż model. Kurs jest raczej za niski. To zły znak dla opłacalności typu."
        ),
    ),
    "nosteam": (
        "No Steam Confirmation",
        (
            "Ocena jest wysoka, ale kurs na typ nie spada wyraźnie. Rynek jej nie potwierdza. Dlatego typ nie "
            "dostaje poziomu „mocny”."
        ),
    ),
    "rising": (
        "Risk: Rising Odds",
        (
            "Model widzi wysoką wartość albo mocny sygnał. Kurs na typ jednak rośnie. Dlatego typ dostaje "
            "najwyżej poziom „do rozważenia”."
        ),
    ),
    "edgeval": (
        "Przewaga modelu",
        (
            "Szansa według modelu soccer-rating minus szansa wynikająca z kursu zamknięcia, w punktach "
            "procentowych. Dodatnia jest dobra: model ocenia typ wyżej niż rynek. Ujemna oznacza, że kurs jest "
            "raczej za niski."
        ),
    ),
    "steamval": (
        "Ruch kursu",
        (
            "O ile kurs na typ spadł od otwarcia bardziej niż kurs na rywala. Skala logarytmiczna: 0,10 to około "
            "10%. Dodatni jest dobry: rynek stawia na typ. Ujemny oznacza, że rynek się od typu odwraca."
        ),
    ),
    "aoval": (
        "Wskaźnik AO",
        (
            "Wskaźnik AO z soccer-rating.com. Strona pokazuje go tylko wtedy, gdy przekracza 30 w jedną lub drugą "
            "stronę. Wtedy pojawia się sygnał „Strange Odds”. Napis „brak” oznacza wartość w normie."
        ),
    ),
    "odds": (
        "Kurs",
        (
            "Kurs zamknięcia na typ, dziesiętny. Przy kursie 1,13 za każdą postawioną złotówkę wraca 1,13 zł "
            "razem ze stawką. Niski kurs oznacza faworyta i małą wygraną."
        ),
    ),
    "oddsmove": (
        "Kurs",
        (
            "Kurs na typ przy otwarciu rynku i przy zamknięciu. Spadek jest dobry dla typu: rynek coraz mocniej "
            "na niego stawia."
        ),
    ),
    "fair": (
        "Kurs uczciwy",
        (
            "Kurs wynikający z szans według modelu soccer-rating, bez marży bukmachera. Jeśli jest niższy niż "
            "kurs rynkowy, typ jest wart więcej, niż płaci rynek. Jeśli jest wyższy, model ocenia typ niżej niż "
            "rynek."
        ),
    ),
    "caution": (
        "Ostrożnie",
        (
            "Drużyna ma już pewny awans albo wysokie ryzyko rotacji. Może zagrać rezerwami. Typ jest ryzykowny "
            "niezależnie od szans."
        ),
    ),
    "avoid": ("Unikaj", "Drużyna praktycznie nie ma już szans na awans: najwyżej 1,5%. Zwykle nie gra już o nic."),
    "winprob": (
        "Szansa",
        (
            "Szansa wygranej drużyny z typu według prognozy The Analyst. Wyższa jest lepsza. Szczegóły meczu "
            "pokazują też szansę remisu i porażki."
        ),
    ),
    "value": (
        "Wartość",
        (
            "Indeks wartości modelu, od 0 do 140. Wyższy jest lepszy. Rośnie z szansą wygranej i z motywacją "
            "drużyny. Rośnie też, gdy rywal ma pewny awans, odpadł albo ma niską motywację. Spada przy ryzyku "
            "rotacji drużyny. Od 70 to wysoka wartość, od 50 dobra. Nie uwzględnia kursów ani ryzyka rotacji "
            "rywala."
        ),
    ),
    "motivation": (
        "Motywacja",
        (
            "Ile drużyna ma do ugrania w meczu, od 0 do 100. Wyższa jest lepsza dla typu. Najwyższa jest wtedy, "
            "gdy ważą się awans, miejsce w ósemce albo rozstawienie. Pewny awans albo brak szans ją obniża."
        ),
    ),
    "rotation": (
        "Ryzyko rotacji",
        (
            "Wskaźnik ryzyka, że drużyna wystawi rezerwy, od 1,0 do 2,3. Niższy jest lepszy. 1,0 oznacza brak "
            "ryzyka. Od 1,39 rekomendacja to „ostrożnie”."
        ),
    ),
    "status": (
        "Status",
        (
            "Sytuacja drużyny według prognozy The Analyst sprzed kolejki. Status „gra o awans”: wynik jeszcze się "
            "waży. Status „pewny awans do 1/8”: miejsce w ósemce ma co najmniej 98,5% szans. Status „pewne "
            "baraże”: awans jest pewny, ale bez ósemki. Status „bez szans”: awans ma najwyżej 1,5% szans."
        ),
    ),
    "outsig": ("Out of contention", "Drużyna praktycznie nie może już awansować. Rekomendacja to zawsze „unikaj”."),
    "rotsig": ("High rotation risk", "Ryzyko rotacji wynosi co najmniej 1,39. Rekomendacja to „ostrożnie”."),
    "lockedsig": (
        "Status LOCKED",
        (
            "Awans do 1/8 albo do baraży jest już pewny. Drużyna może oszczędzać zawodników. Rekomendacja to "
            "„ostrożnie”."
        ),
    ),
    "highval": ("High Value", "Wartość wynosi co najmniej 70. To wysoka wartość."),
    "goodval": ("Good Value", "Wartość wynosi co najmniej 50, ale mniej niż 70. To dobra wartość."),
    "aofair": (
        "Close / Fair",
        (
            "Pojawia się przy wysokiej wartości, jeśli znane są kursy. Pokazuje kurs zamknięcia (Close) i kurs "
            "uczciwy według modelu (Fair). Znak między nimi mówi, który jest wyższy. Kurs zamknięcia wyższy od "
            "uczciwego oznacza wartość według rynku."
        ),
    ),
    "quality": (
        "Jakość danych",
        (
            "Pewność dopasowania kursów do meczu. 1,0: dane są pełne i pewne. 0,5: dane są, ale dopasowanie jest "
            "mniej pewne. 0: brak danych soccer-rating."
        ),
    ),
}

HINT = (
    "<p><small>Słowa podkreślone kropkami mają objaśnienie. Dotknij ich albo najedź na nie myszą. "
    'Znak <span class="mk mk-more" role="img" aria-label="strzałka w prawo"></span> przy meczu otwiera'
    " jego szczegóły. Pogrubiona drużyna to typ.</small></p>"
)
# Key points under each tab's heading, one list item each
_START_WITH_LEVELS = (
    '<b>Rekomendacja</b>: zacznij od <span class="nw"><span class="mk mk-strong" aria-hidden="true"></span>'
    '„mocny”</span>, potem <span class="nw"><span class="mk mk-consider" aria-hidden="true"></span>'
    "„do rozważenia”</span>."
)
KEY_POINTS_FULL = (
    _START_WITH_LEVELS,
    "<b>Wartość</b>: im wyższa, tym lepiej. Od 70 jest wysoka, od 50 dobra.",
    "<b>Kurs</b>: niski oznacza faworyta i małą wygraną.",
)
KEY_POINTS_SR = (
    _START_WITH_LEVELS,
    "<b>Ocena</b>: powyżej 0,50 to wyraźny sygnał. Zależy jednak głównie od kursu.",
    "<b>Przewaga modelu</b> w szczegółach meczu: dodatnia oznacza okazję.",
)

# Footer paragraphs' contents: the top link stands alone, the others are small print; footer_sources() comes second
FOOTER_TOP = '<a href="#top" class="top">Do góry</a>'
FOOTER_GAMBLING = (
    "To wynik modelu, a nie pewny typ: każdy zakład może przegrać. Graj tylko u legalnych bukmacherów, tylko jeśli "
    "masz ukończone 18 lat, i tylko za kwoty, których stratę możesz przyjąć. Jeśli granie przestaje być rozrywką "
    "albo martwi cię, ile na nie wydajesz, możesz porozmawiać z kimś anonimowo i bezpłatnie: Ogólnopolski Telefon "
    'Zaufania Uzależnienia, <a href="tel:800199990">800 199 990</a>. Placówki i poradnia online: '
    '<a href="https://uzaleznieniabehawioralne.pl/" target="_blank" rel="noopener" '
    'title="uzaleznieniabehawioralne.pl, otwiera się w nowej karcie">uzaleznieniabehawioralne.pl</a>.'
)
FOOTER_INDEPENDENCE = (
    "Projekt niezależny, bez związku z UEFA, soccer-rating.com i The Analyst. Strona zapamiętuje filtry tylko "
    "w twojej przeglądarce; nie używa ciasteczek ani statystyk odwiedzin."
)
FOOTER_LICENCE = (
    "© 2026 visvaya · kod na licencji "
    '<a href="https://github.com/visvaya/uefa-cups-predictor/blob/main/LICENSE" target="_blank" rel="noopener" '
    'title="Licencja MIT na GitHubie, otwiera się w nowej karcie">MIT</a> · '
    '<a href="https://github.com/visvaya/uefa-cups-predictor/blob/main/interpretation.md" target="_blank" '
    'rel="noopener" title="Opis modelu na GitHubie, otwiera się w nowej karcie">jak działa model</a> · '
    '<a href="https://github.com/visvaya/uefa-cups-predictor/issues" target="_blank" rel="noopener" '
    'title="Zgłoszenia na GitHubie, otwiera się w nowej karcie">zgłoś błąd</a>'
)

# Column heads by sort key; the card strip shows the same words
HEADS = {
    "time": "Godz.",
    "match": "Mecz",
    "pick": "Typ",
    "odds": "Kurs",
    "ocena": "Ocena",
    "win": "Szansa",
    "mot": "Motyw.",
    "value": "Wartość",
    "level": "Rekomendacja",
}
# Sort buttons of the card layout by sort key
SORT_NAMES = {
    "time": "godzina",
    "match": "mecz",
    "pick": "typ",
    "odds": "kurs",
    "ocena": "ocena",
    "win": "szansa",
    "mot": "motywacja",
    "value": "wartość",
    "level": "rekomendacja",
}
PICK_NAMES = {"1": "(1) gospodarze", "X": "(X) remis", "2": "(2) goście"}
# Words of the page's controls, details and notices
LABELS = {
    "show_details": "Pokaż szczegóły meczu",
    "signals": "Sygnały",
    "from": "od",
    "to": "do",
    "less": "mniej",
    "more": "więcej",
    "signal_note": (
        "Zaznaczenie pokaże tylko mecze z którymkolwiek z wybranych sygnałów; bez zaznaczenia widać wszystkie."
    ),
    "clear_choice": "Wyczyść wybór",
    "search_team": "Szukaj drużyny",
    "search_team_example": "np. Guadeloupe",
    "competitions": "Rozgrywki",
    "search_competition": "Szukaj rozgrywek",
    "search_competition_example": "np. Lega",
    "no_competition": "Żadne rozgrywki nie pasują.",
    "choose": "Wybierz:",
    "all": "wszystkie",
    "no_option": "żadne",
    "time": "Czas",
    "hide_started": "ukryj mecze, które już się zaczęły",
    "status_filter": "Status typu",
    "win_pct": "Szansa (%)",
    "sorting": "Sortowanie:",
    "about": "W skrócie",
    "filters": "Filtry:",
    "all_matches": "wszystkie mecze",
    "clear_filters": "Wyczyść filtry",
    "draw": "remis",
    "no_data": "brak danych",
    "none": "brak",
    "no_row": "brak wiersza",
    "start": "Początek",
    "open": "otwarcie",
    "close": "zamknięcie",
    "fair": "Kurs uczciwy",
    "edge": "Przewaga modelu",
    "points": "pp",
    "steam": "Ruch kursu",
    "ao": "Wskaźnik AO",
    "quality": "Jakość danych",
    "clubs": "Strony klubów",
    "chances": "Szanse meczu",
    "pick_odds": "Kurs typu",
    "win_prob": "Szansa wygranej",
    "motivation": "Motywacja",
    "status": "Status",
    "rotation": "Ryzyko rotacji",
    "value_short": "Wart.",
    "indicator": "Wskaźnik",
    "both_teams": "Mecz i obie drużyny",
}

# Tab headings, intros and notices; {placeholders} take generated values
SR_TITLE = "Soccer-rating: typy"
SR_TITLE_ON = "Soccer-rating: typy na"
SR_NO_DATA = "Brak danych: nie ma pobranych meczów z soccer-rating.com."
SR_COUNT = "{matches} z soccer-rating.com."
SR_FIRST_LAST = "Pierwszy zaczyna się: {first}. Ostatni: {last}."
SR_PAGE_TIME = "Godziny są w czasie polskim."
SR_SCRAPED = "Dane pobrano {stamp}."
CUPS_TITLE = "Pełna analiza: faza ligowa europejskich pucharów"
CUPS_COUNT = "Kolejka fazy ligowej: {matches}."
CUP_DAY = "{cup} gra {days}."
CUPS_ONE_TIME = "Wszystkie mecze zaczynają się o {time} czasu polskiego."
CUPS_TIMES = "Mecze zaczynają się o {times} czasu polskiego."
CUPS_KNOWN_TIMES = "Znane godziny (czas polski): {times} ({without})."
CUPS_NO_TIMES = "Godziny i kursy: brak danych soccer-rating dla tych meczów."
# The count of matches whose kickoff the inputs do not have
WITHOUT_TIME = "{matches} bez godziny"
# The count of matches whose day the inputs do not have
WITHOUT_DAY = "{matches} bez daty"
CUPS_SOURCES = (
    "Szanse, tabela i statusy pochodzą z prognozy The Analyst sprzed kolejki. Rekomendacje policzył analizator."
)
CUP_NO_DATA = (
    "Brak danych: prognozy The Analyst dla tych rozgrywek nie zostały jeszcze pobrane. Prognozy są na "
    '<a href="https://theanalyst.com/competition/{slug}/predictions" target="_blank" rel="noopener" '
    'title="theanalyst.com, otwiera się w nowej karcie">theanalyst.com</a>.'
)
# Browser tab titles: short, the project name last so the tab is recognisable among others
TAB_SR = f"Soccer-rating {{days}} {EN_DASH} uefa-cups-predictor"
TAB_SR_EMPTY = f"Soccer-rating {EN_DASH} uefa-cups-predictor"
TAB_CUPS = f"Europejskie puchary {EN_DASH} uefa-cups-predictor"
GENERATED = "Strona wygenerowana {stamp}."

# Letters with no Unicode decomposition fold by hand (the page script's fold() uses the same table)
_LETTERS = str.maketrans({"ø": "o", "ł": "l", "æ": "ae", "ß": "ss", "đ": "d", _DOTLESS_I: "i", "œ": "oe"})
# A club page path on soccer-rating.com: one leading slash (two would name another host), then safe URL characters
_CLUB_PATH = re.compile(r"/(?!/)[A-Za-z0-9._~%/-]*")
_SITE_ZONE = ZoneInfo(SITE_TIMEZONE)
_PAGE_ZONE = ZoneInfo(PAGE_TIMEZONE)


def level_of(label: str) -> Level:
    """The level of a report label such as the STRONG BUY one; an unknown label raises ValueError."""
    for suffix, level in _LABEL_LEVELS.items():
        if label.endswith(suffix):
            return level
    raise ValueError(f"Unknown recommendation label: {label!r}")


def pl_number(value: float, digits: int = 2, sign: bool = False) -> str:
    """A number as Polish text writes it: decimal comma and a real minus sign."""
    text = f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"
    return text.replace(".", ",").replace("-", MINUS)


def matches_phrase(n: int) -> str:
    """A count of matches with the Polish plural: 1 mecz, 2 mecze, 5 meczów, 22 mecze."""
    if n == 1:
        word = "mecz"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        word = "mecze"
    else:
        word = "meczów"
    return f"{n} {word}"


def day_heading(day: date) -> str:
    """A day group's heading, such as "Środa, 18.11"."""
    return f"{WEEKDAYS[day.weekday()].capitalize()}, {day.day}.{day.month:02d}"


def _day_month(day: date) -> str:
    return f"{day.day} {MONTHS[day.month - 1]}"


def date_span(first: date, last: date) -> str:
    """The days of a set of matches, such as "18 listopada 2026"; a range joins its ends with an en dash."""
    end = f"{_day_month(last)} {last.year}"
    if first == last:
        return end
    if (first.year, first.month) == (last.year, last.month):
        return f"{first.day}{EN_DASH}{end}"
    start = _day_month(first) if first.year == last.year else f"{_day_month(first)} {first.year}"
    return f"{start} {EN_DASH} {end}"


def day_month_span(first: date, last: date) -> str:
    """Days without the year, such as "28.01", "20-21.01" or "30.11-2.12" with an en dash."""
    end = f"{last.day}.{last.month:02d}"
    if first == last:
        return end
    start = str(first.day) if first.month == last.month else f"{first.day}.{first.month:02d}"
    return f"{start}{EN_DASH}{end}"


def short_date_span(first: date, last: date) -> str:
    """The days of a set of matches in a tab title, such as "16-18.11.2026" with an en dash."""
    if first.year != last.year:
        return f"{first.day}.{first.month:02d}.{first.year}{EN_DASH}{last.day}.{last.month:02d}.{last.year}"
    return f"{day_month_span(first, last)}.{last.year}"


def and_list(items: Sequence[str]) -> str:
    """Items joined as Polish lists them: "a", "a i b", "a, b i c"."""
    return " i ".join([", ".join(items[:-1]), items[-1]]) if len(items) > 1 else "".join(items)


def stamp(moment: datetime) -> str:
    """A moment as "16.11.2026 o 17:57": an aware one in page time, a naive one as it is."""
    if moment.tzinfo is not None:
        moment = moment.astimezone(_PAGE_ZONE)
    return f"{moment:%d.%m.%Y} o {moment:%H:%M}"


def kickoff_at(day: date, time_local: str | float) -> datetime | None:
    """The kickoff in page time, from the day and the site's local time such as "21:00" or "9:05".

    Frames give NaN (a float) for an unknown time, so NaN, an empty text or an unreadable one gives None.
    """
    if not isinstance(time_local, str):
        return None
    try:
        clock = datetime.strptime(time_local.strip(), "%H:%M").time()
    except ValueError:
        return None
    return datetime.combine(day, clock, tzinfo=_SITE_ZONE).astimezone(_PAGE_ZONE)


def club_link(name: str, href: str | None) -> str:
    """A link to the club's soccer-rating.com page, or only the escaped name when the href is not a site path."""
    if href is None or not _CLUB_PATH.fullmatch(href):
        return escape(name)
    hint = f"Strona klubu {name} na soccer-rating.com, otwiera się w nowej karcie"
    return (
        f'<a href="{escape(SOCCER_RATING_SITE + href)}" target="_blank" rel="noopener" title="{escape(hint)}" '
        f'translate="no">{escape(name)}</a>'
    )


def footer_sources(scraped_at: datetime | None) -> str:
    """The footer's sources paragraph; it names the scrape time only when it is known."""
    scraped = f", pobrane {stamp(scraped_at)}" if scraped_at is not None else ""
    return (
        f'Zakładka „Soccer-rating”: mecze i kursy z <a href="{SOCCER_RATING_SITE}/" target="_blank" '
        f'rel="noopener" title="soccer-rating.com, otwiera się w nowej karcie">soccer-rating.com</a>{scraped}. '
        'Zakładka „Europejskie puchary”: szanse i tabela z <a href="https://theanalyst.com/" target="_blank" '
        'rel="noopener" title="The Analyst, otwiera się w nowej karcie">The Analyst</a>. '
        "Oceny i rekomendacje liczy model uefa-cups-predictor."
    )


def fold(name: str) -> str:
    """A team name without diacritics, in lower case, to match names across sources (Fenerbahce, Fenerbahçe)."""
    return (
        "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
        .lower()
        .translate(_LETTERS)
    )
