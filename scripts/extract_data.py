#!/usr/bin/env python3
"""Extract family data from the generated index.html into data/family.yaml.

The original export of the former base is lost; the published index.html
is the only remaining source. Everything that is mechanically verifiable in
the HTML is transferred into a local YAML file (never committed — it holds
names and birth years of living people; see docs/decisions.md):

- persons   — from the pedigree card groups (name, years, status by class);
- parent edges — from the connector paths (generation columns + `path.ln`
  brackets, reconstructed purely by geometry);
- database  — the published aggregates of the lost 243-person export (hero
  stats, surname/place cards, precision buckets) that cannot be recomputed
  from the chart alone;
- gaps      — facts mentioned in the HTML text that have no structured form
  (side relatives, marriages outside the chart).

Anything that cannot be verified mechanically goes into `gaps`, never into
silent assumptions. Privacy fuse: the source HTML already publishes only
names and birth years for living people; parse_data.py rejects exact dates
for living persons if they are ever added by hand.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "index.html"
OUTPUT_PATH = ROOT / "data" / "family.yaml"

# Chart geometry mirrors build_site.py: BOX_W=214, COL_W=242, BOX_H=78.
BOX_W = 214
HALF_H = 39.0
COLUMN_X = [18, 260, 502, 744, 986, 1228, 1470, 1712]
MID_X = {x + BOX_W + 14 for x in COLUMN_X[:-1]}

# Archival persons of the 1834 revision list (yard No. 26, sheet 689, frame
# 0168). They are named in the «Матюхины» branch text but have no chart card.
# Birth/death years are computed from the ages stated in the text — the same
# computation the old injection performed. «Григорий» и «Степанида» —
# родители по ревизии, они уже есть в древе.
ARCHIVAL_PERSONS = [
    {
        "name": "Пётр",
        "birth": "ок. 1814", "death": "ок. 1815",
        "father": "Григорий", "mother": "Степанида",
        "sex": "M",
        "note": "Сын Григория по ревизской сказке 1834 г. (19 лет в 1834 г.); умер в младенчестве.",
    },
    {
        "name": "Матвей",
        "birth": "ок. 1826", "death": "ок. 1827",
        "father": "Григорий", "mother": "Степанида",
        "sex": "M",
        "note": "Сын Григория по ревизской сказке 1834 г. (7 лет в 1834 г.); умер в младенчестве. Не путать с прапрапрапрапрадедом Матвеем, отцом Ильи.",
    },
    {
        "name": "Иван",
        "birth": "ок. 1827", "death": "ок. 1828",
        "father": "Григорий", "mother": "Степанида",
        "sex": "M",
        "note": "Сын Григория по ревизской сказке 1834 г. (6 лет в 1834 г.); умер в младенчестве.",
    },
    {
        "name": "Анна",
        "birth": "ок. 1820", "death": "",
        "father": "Григорий", "mother": "Степанида",
        "sex": "F",
        "note": "Дочь Григория по ревизской сказке 1834 г. (14 лет в 1834 г.).",
    },
    {
        "name": "Агафья",
        "birth": "ок. 1833", "death": "",
        "father": "Григорий", "mother": "Степанида",
        "sex": "F",
        "note": "Дочь Григория по ревизской сказке 1834 г. (1 год в 1834 г.).",
    },
    {
        "name": "Параскева Петрова",
        "birth": "", "death": "",
        "father": "", "mother": "",
        "sex": "F",
        "note": "Жена Федота Григорьева, мать Андрея Федотовича — подтверждена в тексте ветви «Матюхины». В древе связей с ней нет (у Андрея Федотовича там заглушка «мать не найдена»), поэтому ребро в YAML не проведено; см. gaps.",
    },
]


def parse_cards(html: str) -> list[dict]:
    cards = []
    for group in re.findall(r'<g class="bx[^"]*">.*?</g>', html):
        cls = re.match(r'<g class="([^"]*)"', group).group(1)
        rect = re.search(r'<rect class="fr" x="(\d+)" y="([\d.]+)"', group)
        t1 = re.search(r'class="t1"[^>]*>([^<]*)<', group)
        t2 = re.search(r'class="t2"[^>]*>([^<]*)<', group)
        t3 = re.search(r'class="t3"[^>]*>([^<]*)<', group)
        badge = re.search(r'class="bdg"[^>]*>([^<]*)<', group)
        cards.append({
            "cls": cls,
            "x": int(rect.group(1)),
            "y": float(rect.group(2)),
            "cy": float(rect.group(2)) + HALF_H,
            "t1": t1.group(1) if t1 else "",
            "t2": t2.group(1) if t2 else "",
            "t3": t3.group(1) if t3 else "",
            "badge": badge.group(1) if badge else "",
        })
    return cards


def parse_edges(html: str, cards: list[dict]) -> list[tuple[dict, dict | None, dict | None]]:
    """Rebuild (child, father, mother) triples from connector geometry.

    Each bracket consists of: a horizontal stub from the child card, a
    vertical spanning the two parent rows, and a horizontal into each parent
    column. The upper parent row is the father, the lower is the mother.
    Placeholders («мать не найдена») resolve to None.
    """
    by_col: dict[int, list[dict]] = {}
    for card in cards:
        by_col.setdefault(card["x"], []).append(card)

    def card_at(col_x: int, cy: float) -> dict | None:
        for card in by_col.get(col_x, []):
            if abs(card["cy"] - cy) < 0.01:
                return None if card["t1"] == "—" else card
        return None

    child_h, verticals = [], []
    for d in re.findall(r'<path class="ln" d="([^"]+)"/>', html):
        m = re.match(r"M([-\d.]+) ([-\d.]+) ([HV])([-\d.]+)$", d)
        x1, y1, cmd, c2 = float(m.group(1)), float(m.group(2)), m.group(3), float(m.group(4))
        if cmd == "H" and x1 in {c["x"] + BOX_W for c in cards}:
            child_h.append((x1, y1, c2))
        elif cmd == "V" and x1 in MID_X:
            verticals.append((x1, y1, c2))

    edges = []
    for x_right, cy, mid in child_h:
        child = card_at(x_right - BOX_W, cy)
        assert child is not None, f"коннектор M{x_right} {cy} не ведёт к карточке"
        spanning = [
            v for v in verticals
            if abs(v[0] - mid) < 0.01 and min(v[1], v[2]) - 0.01 <= cy <= max(v[1], v[2]) + 0.01
        ]
        assert len(spanning) == 1, f"у карточки {child['t1']} {child['t2']} нет вертикали скобки"
        top, bottom = sorted(spanning[0][1:3])
        parent_col = int(mid) + 14
        assert parent_col in COLUMN_X, f"неизвестная колонка {parent_col}"
        edges.append((child, card_at(parent_col, top), card_at(parent_col, bottom)))
    return edges


def split_years(t3: str) -> tuple[str, str]:
    """Split the card date line into (birth, death) exactly as displayed.

    '1 октября 1931 – 10 мая 1996' -> ('1 октября 1931', '10 мая 1996')
    '† зима 1961'                  -> ('', 'зима 1961')
    'ок. 1818'                     -> ('ок. 1818', '')
    '1971'                         -> ('1971', '')
    """
    t3 = t3.strip()
    if not t3:
        return "", ""
    if t3.startswith("† "):
        return "", t3[len("† "):]
    if " – " in t3:
        birth, death = t3.split(" – ", 1)
        return birth, death
    return t3, ""


def derived_status(birth: str) -> str:
    """The chart derives card status from the birth date (is_reconstructed):
    a missing or qualified («ок.», «до», «после») birth means «гипотеза»."""
    head = birth.split(" ", 1)[0] if birth else ""
    if not birth or head in {"ок.", "до", "после", "между"}:
        return "hyp"
    return "ok"


def is_living(birth: str, death: str, today: int) -> bool:
    """A person is published as living only with a bare 4-digit birth year
    recent enough (same 110-year rule as the model, PRESUMED_DECEASED_AGE)."""
    if death:
        return False
    if not birth:
        return False
    year = re.search(r"\d{4}", birth)
    return bool(year) and int(year.group(0)) > today - 110


def parse_timeline_places(html: str) -> dict[tuple[str, str], str]:
    """(label, years) -> published place, from the «цепочка поколений» block."""
    match = re.search(r"Матюхины: цепочка поколений(.*?)Ономастика", html, re.S)
    assert match, "не найден раздел «цепочка поколений»"
    text = re.sub(r"<[^>]+>", "\n", match.group(1))
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    fallback = "Место уточняется по метрикам и семейным записям."
    places: dict[tuple[str, str], str] = {}
    i = 0
    while i < len(lines):
        if re.match(r"Поколение \d+ · линия Матюхиных$", lines[i]):
            label, yrs = lines[i + 1], lines[i + 2]
            place = lines[i + 3] if i + 3 < len(lines) and not re.match(
                r"(Поколение \d+|Ономастика)", lines[i + 3]
            ) else ""
            if place and place != fallback:
                places[(label, yrs)] = place
            i += 3
        i += 1
    return places


def parse_database(html: str) -> dict:
    """Published aggregates of the lost export, parsed from the page text."""
    def number(pattern: str, label: str) -> int:
        m = re.search(pattern, html, re.S)
        assert m, f"не найдено число: {label}"
        return int(m.group(1))

    surnames = [
        (name, int(count))
        for name, count in re.findall(
            r'<div class="card"><h4>([^<]+)</h4><p>[^<]*</p>'
            r'<div class="mini">(\d+) носител', html
        )
    ]
    places = [
        (name, int(count))
        for count, name in re.findall(
            r'География · (\d+) запис(?:ь|и|ей)</div><h4>([^<]+)</h4>', html
        )
    ]
    return {
        "note": (
            "Агрегаты утерянной выгрузки от 17 июля 2026 "
            "(243 человека), публикуемые на сайте как есть: перечислить все "
            "243 персоны по index.html невозможно."
        ),
        "people": number(r"<b>(243)</b><span>", "человек в базе"),
        "families": number(r": 243 человека, (\d+) семейн", "семейные записи"),
        "deaths": number(r"(\d+) дат смерти", "даты смерти"),
        "surnames_total": number(r"<b>(40)</b><span>", "родовых фамилий"),
        "earliest_birth": number(r"<b>(1768)</b><span>", "самое раннее рождение"),
        "with_birth": number(r"запись о рождении есть у (\d+)", "с датой рождения"),
        "birth_full": number(r"<b>День, месяц и год</b> — (\d+) запис", "полные даты"),
        "birth_year_only": number(r"<b>Только год</b> — (\d+);", "только год"),
        "birth_month_year": number(r"месяц и год — (\d+)</li>", "месяц и год"),
        "birth_qualified": number(r"«между»</b> — (\d+):", "с пометой"),
        "birth_missing": number(r"<b>Дата рождения отсутствует</b> — (\d+) человек", "без даты"),
        "matches": number(r"<b>(\d+) запис(?:ь|и|ей)</b> связаны с совпадением", "совпадения с чужими деревьями"),
        "with_parents": number(r"<b>(177)</b><span>", "с указанными родителями"),
        "top_surnames": [{"name": n, "count": c} for n, c in surnames],
        "places": [{"name": n, "count": c} for n, c in places],
    }


def main() -> None:
    if not HTML_PATH.exists():
        sys.exit(f"Ошибка: не найден {HTML_PATH} — запускать из корня репозитория.")
    html = HTML_PATH.read_text(encoding="utf-8")

    cards = parse_cards(html)
    placeholders = [c for c in cards if c["t1"] == "—"]
    person_cards = [c for c in cards if c["t1"] != "—"]
    print(f"Карточки: {len(cards)} (персоны: {len(person_cards)}, заглушки: {len(placeholders)})")

    edges = parse_edges(html, cards)
    father_edges = sum(1 for _, f, _ in edges if f)
    mother_edges = sum(1 for _, _, m in edges if m)
    print(f"Скобок родительства: {len(edges)} (отец: {father_edges}, мать: {mother_edges})")

    # --- assign local ids in chart reading order (column, then top-down) ---
    person_cards.sort(key=lambda c: (c["x"], c["y"]))
    persons = []
    for index, card in enumerate(person_cards, 1):
        surname, name = (card["t1"], card["t2"]) if card["t2"] else ("", card["t1"])
        birth, death = split_years(card["t3"])
        persons.append({
            "id": f"p{index:02d}",
            "surname": surname,
            "name": name,
            "birth": birth,
            "death": death,
            "sex": "",
            "deceased": not is_living(birth, death, date.today().year),
            "status": derived_status(birth),
            "father": "",
            "mother": "",
            "place": "",
            "note": "",
            "_card": card,
        })
    key_of = {(p["_card"]["x"], p["_card"]["y"]): p["id"] for p in persons}
    by_card = {(p["_card"]["x"], p["_card"]["y"]): p for p in persons}

    # --- parent edges; bracket roles also give the sex of every endpoint ---
    sex_roles: dict[tuple[int, float], str] = {}
    for child, father, mother in edges:
        child_p = by_card[(child["x"], child["y"])]
        if father:
            child_p["father"] = key_of[(father["x"], father["y"])]
            sex_roles[(father["x"], father["y"])] = "M"
        if mother:
            child_p["mother"] = key_of[(mother["x"], mother["y"])]
            sex_roles[(mother["x"], mother["y"])] = "F"

    # --- verify card statuses against the derivation used by the generator ---
    for card in person_cards:
        p = by_card[(card["x"], card["y"])]
        expected = "hyp" if "hyp" in card["cls"] else "ok"
        assert p["status"] == expected, (
            f"статус {p['id']} {p['name']}: карточка {card['cls']}, выведено {p['status']}"
        )
        assert card["badge"] == ("Гипотеза" if expected == "hyp" else ""), (
            f"бейдж не согласован с классом карточки: {card}"
        )
    assert all(c["badge"] == "Нет данных" for c in placeholders)

    # --- anchor family: marriage bracket + «родители Анны (р. 2002)» ---
    def by_name(name: str) -> dict:
        matches = [p for p in persons if p["name"] == name or p["surname"] == name]
        assert len(matches) == 1, f"персона «{name}» не найдена однозначно: {matches}"
        return matches[0]

    sergey = by_name("Сергей Андреевич")
    anna = by_name("Анна Сергеевна")
    nadezhda = by_name("Надежда Эдуардовна")
    assert sergey["father"] and sergey["mother"] and not anna["father"]
    anna["father"] = sergey["id"]
    anna["mother"] = nadezhda["id"]
    sergey["sex"] = "M"
    nadezhda["sex"] = "F"
    anna["sex"] = "F"

    # --- timeline places (published birthplaces of the Matyukhin chain) ---
    places = parse_timeline_places(html)
    matched = 0
    for p in persons:
        label = f"{p['surname']} {p['name']}".strip()
        if p["birth"] and p["death"]:
            years = f"{p['birth']} – {p['death']}"
        elif p["birth"]:
            years = f"р. {p['birth']}"
        elif p["death"]:
            years = f"ум. {p['death']}"
        else:
            years = "? – ?"
        for (name_part, yrs_part), place in places.items():
            if (label == name_part or p["name"] == name_part) and yrs_part == years:
                p["place"] = place
                matched += 1
    print(f"Мест из таймлайна привязано: {matched} из {len(places)}")
    assert matched == len(places), "не все места таймлайна нашли персону"

    # --- sex: bracket roles cover every card except the anchor trio ---
    for card in person_cards:
        p = by_card[(card["x"], card["y"])]
        role = sex_roles.get((card["x"], card["y"]), "")
        assert p["sex"] or role, f"пол не определён: {p['id']} {p['name']}"
        p["sex"] = p["sex"] or role

    # --- archival persons of the 1834 revision list ---
    next_index = len(persons) + 1
    for arch in ARCHIVAL_PERSONS:
        father = by_name(arch["father"]) if arch["father"] else None
        mother = by_name(arch["mother"]) if arch["mother"] else None
        persons.append({
            "id": f"p{next_index:02d}",
            "surname": "",
            "name": arch["name"],
            "birth": arch["birth"],
            "death": arch["death"],
            "sex": arch["sex"],
            "deceased": not is_living(arch["birth"], arch["death"], date.today().year),
            "status": derived_status(arch["birth"]),
            "father": father["id"] if father else "",
            "mother": mother["id"] if mother else "",
            "place": "село Мокрое Тульской области",
            "note": arch["note"],
            "_card": None,
        })
        next_index += 1

    # --- privacy fuse: living people carry a bare birth year only ---
    for p in persons:
        if p["death"] or not p["birth"]:
            continue
        year = re.search(r"\d{4}", p["birth"])
        if year and int(year.group(0)) > date.today().year - 110:
            assert re.fullmatch(r"\d{4}", p["birth"]), (
                f"ошибка приватности: {p['id']} {p['name']} — возможно живой, "
                f"но дата не голый год: «{p['birth']}»"
            )
            p["place"] = ""
            p["note"] = ""

    # --- database aggregates of the lost export ---
    database = parse_database(html)
    print(
        f"База: {database['people']} человек, {database['families']} семей, "
        f"{database['deaths']} дат смерти, фамилий: {database['surnames_total']}, "
        f"ранний год: {database['earliest_birth']}"
    )
    assert len(database["top_surnames"]) == 10, "ожидалось 10 карточек фамилий"
    assert len(database["places"]) == 9, "ожидалось 9 карточек мест"

    # --- verification 1: every extracted date exists verbatim in the HTML ---
    archival_years = {p["birth"] for p in persons if not p["_card"]} | {
        p["death"] for p in persons if not p["_card"]
    }
    missing_dates = [
        (p["id"], field, p[field])
        for p in persons
        for field in ("birth", "death")
        if p[field] and p[field] not in archival_years and p[field] not in html
    ]
    assert not missing_dates, f"даты, которых нет в HTML: {missing_dates}"

    # --- verification 2: not a single card lost or mangled ---
    # A card displays the surname in t1 (or the bare name when there is no
    # surname) and the given name in t2; compare in display form.
    def display_pair(p: dict) -> tuple[str, str]:
        return (p["surname"] or p["name"], p["name"] if p["surname"] else "")

    html_pairs = {(c["t1"], c["t2"]) for c in person_cards}
    yaml_pairs = {display_pair(p) for p in persons if p["_card"]}
    assert html_pairs == yaml_pairs, f"расхождение имён: {html_pairs ^ yaml_pairs}"
    assert len({p["name"] for p in persons if not p["_card"]}) == len(
        [p for p in persons if not p["_card"]]
    ), "дубликаты имён среди архивных персон"

    gaps = [
        {
            "what": "Боковые сыновья Григория Спиридоновича и Зинаиды Елисеевой: Василий (остался Захаровым), Александр, Иван, Константин — стали Алексеевыми.",
            "where": "index.html, раздел «Две ветви Алексеевых» → «Захаровы-Алексеевы», абзац 2.",
        },
        {
            "what": "Восемь детей Василия Васильевича Алексеева и Агафьи Андреевны (в древе из них только Маргарита).",
            "where": "index.html, раздел «Две ветви Алексеевых» → «Алексеевы донбасские», абзац 1.",
        },
        {
            "what": "Мать Андрея Федотовича — Параскева Петрова: ребро в YAML не проведено, чтобы древо совпадало с опубликованным (там заглушка «мать не найдена»). Персона внесена с note.",
            "where": "index.html, раздел «Четыре родительские линии» → «Матюхины», абзац 1.",
        },
        {
            "what": "Родня по браку из утерянной базы (Никитины, Сахаровы, Цыгановы, Игнатьевы, Черновы, Васильевы, Букины, Успенские, Яковлевы) — персоны не публиковались в древе и не восстановимы.",
            "where": "index.html, раздел «Фамилии рода» (карточки заметок).",
        },
        {
            "what": "Места рождения и смерти персон древа, кроме опубликованных в таймлайне «цепочка поколений», — в HTML не структурированы.",
            "where": "index.html, раздел «География записей» (только агрегаты).",
        },
        {
            "what": "Персональный состав утерянной базы (243 человека, 93 семьи, 50 дат смерти, 82 совпадения с чужими деревьями) — не восстановим; перенесён только агрегатами в database.",
            "where": "index.html, разделы «Источник» и «Что откуда взято».",
        },
    ]

    for p in persons:
        p.pop("_card", None)

    fedot = by_name("Федот")
    paraskeva = by_name("Параскева Петрова")
    data = {
        "meta": {
            "source": (
                "Извлечено механически из сгенерированного index.html скриптом "
                "scripts/extract_data.py: карточки древа, коннекторы, таймлайн. "
                "Исходная выгрузка (экспорт 17 июля 2026) утеряна."
            ),
            "export_date": "17 июля 2026",
            "extracted_at": date.today().isoformat(),
        },
        "root": sergey["id"],
        "persons": persons,
        "families": [
            {
                "husb": sergey["id"],
                "wife": nadezhda["id"],
                "chil": [anna["id"]],
                "note": "Семья, от которой ведётся отсчёт (скобка брака и якорь древа).",
            },
            {
                "husb": fedot["id"],
                "wife": paraskeva["id"],
                "chil": [],
                "note": "Брак из текста ветви «Матюхины»; в древе общих детей нет (у Андрея Федотовича заглушка матери).",
            },
        ],
        "database": database,
        "gaps": gaps,
    }

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    total_dates = sum(1 for p in persons for f in ("birth", "death") if p[f])
    print(
        f"Записано {OUTPUT_PATH}: персон {len(persons)}, дат {total_dates}, "
        f"рёбер {father_edges + mother_edges + 2} (25 отец + 16 мать + 2 якорных Анны)"
    )


if __name__ == "__main__":
    main()
