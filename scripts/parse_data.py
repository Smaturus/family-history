#!/usr/bin/env python3
"""Load data/family.yaml and expose the Person/Family model used by the
render_* functions in build_site.py.

The YAML file is the native data source: it stays LOCAL — .gitignore excludes
it, because it holds names and birth years of living people. The privacy fuse
below rejects anything more detailed if it is ever added by hand.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml


# People born more than this many years ago are treated as deceased when no
# death date is recorded (same rule as the former import pipeline).
PRESUMED_DECEASED_AGE = 110

ALLOWED_STATUS = {"ok", "hyp"}


def fail(message: str) -> None:
    """Report a YAML data error with a human-readable pointer."""
    sys.exit(f"Ошибка данных: {message}\nПроверьте data/family.yaml и запустите сборку снова.")


# External exports spell the same locality differently; show one full label.
# Kept so that place strings already stored in family.yaml render unchanged.
PLACE_CANONICAL = {
  # Мокрое
    "с.мокрое": "село Мокрое Тульской области",
    "село мокрое": "село Мокрое Тульской области",
    "село мокрое тульской области": "село Мокрое Тульской области",
    "с.мокрое, белевский уезд тульской губернии": "село Мокрое Тульской области",
  # Химки
    "химки": "город Химки, Московская область",
    "гхимки": "город Химки, Московская область",
    "химки, московская область, россия": "город Химки, Московская область",
  # Москва
    "москва": "Москва",
    "гмосква": "Москва",
    "россия москва": "Москва",
    "moscow": "Москва",
    "moscow, russia": "Москва",
  # Дмитров
    "дмитров": "город Дмитров, Московская область",
    "город дмитров": "город Дмитров, Московская область",
    "город дмитров, старовнуковское кладбище": "город Дмитров, Московская область",
    "город дмитров, стародмитровское кладбище": "город Дмитров, Московская область",
    "город дмитров красная гора": "город Дмитров, Московская область",
  # Долгопрудный
    "долгопрудный": "город Долгопрудный, Московская область",
    "город долгопрудный": "город Долгопрудный, Московская область",
  # Чистополь
    "чистополь": "город Чистополь, Татария",
    "гчистополь": "город Чистополь, Татария",
  # Толкиш
    "толкиш, татария": "село Толкиш, Татария",
    "малый толкиш": "село Толкиш, Татария",
  # Новошешминск
    "новошешминск": "село Новошешминск, Татария",
  # Лозовая Павловка
    "село лозовая павловка": "село Лозовая Павловка, Донбасс",
    "ворошиловградская область, сергинский/сергеевский/серговский (коневский) район, село лозовая павловка": "село Лозовая Павловка, Донбасс",
  # Валдай / Серганиха
    "дер.серганиха валдайского уезда новгородской губернии": "деревня Серганиха, Валдайский уезд, Новгородская губерния",
    "г.валдай": "город Валдай, Новгородская губерния",
  # Солнечногорск
    "солнечногорск": "город Солнечногорск, Московская область",
    "гсолнечногорск": "город Солнечногорск, Московская область",
  # Борисоглебск
    "борисоглебск": "город Борисоглебск",
    "гборисоглебск": "город Борисоглебск",
  # Астрахань
    "астрахань": "Астрахань",
    "астраххань": "Астрахань",
  # Донбасс
    "донецкая область": "Донецкая область",
    "константиновка донецкой обл": "город Константиновка, Донецкая область",
    "с.внуково": "село Внуково",
    "г.сороки": "город Сороки",
}


def canonical_place(place: str) -> str:
    """Return a single full place label for display."""
    place = (place or "").strip()
    if not place:
        return ""
    return PLACE_CANONICAL.get(place.casefold(), place)


def format_date(value: str) -> str:
    """Pass dates through unchanged: family.yaml stores them already
    formatted in Russian, exactly as they are shown on the site."""
    return (value or "").strip()


def clean_name(value: str) -> str:
    """Strip research artefacts from names: 'Иван(1)', '??????', trailing '?'."""
    value = re.sub(r"\(\d+\)", "", value or "")
    value = re.sub(r"\?{2,}", "", value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip()


def plural(count: int, forms: tuple[str, str, str]) -> str:
    """Pick the Russian form for a count: forms are (1, 2-4, 5+)."""
    tail = abs(int(count)) % 100
    if 11 <= tail <= 14:
        return forms[2]
    tail %= 10
    if tail == 1:
        return forms[0]
    if 2 <= tail <= 4:
        return forms[1]
    return forms[2]


def counted(count: int, forms: tuple[str, str, str]) -> str:
    """Render a number with the correctly declined noun: '3 записи'."""
    return f"{count} {plural(count, forms)}"


# After these consonants a feminine genitive takes -и instead of -ы (Ольга → Ольги).
_HUSHING = set("жчшщгкх")


def genitive_given_name(name: str, sex: str = "") -> str:
    """Decline a Russian given name into the genitive: 'Анна' -> 'Анны'."""
    first = (name or "").split()
    if not first:
        return ""
    word = first[0]
    stem, last = word[:-1], word[-1].lower()

    if last == "я":
        return stem + "и"
    if last == "а":
        return stem + ("и" if stem and stem[-1].lower() in _HUSHING else "ы")
    if last == "й":
        return stem + "я"
    if last == "ь":
        return stem + ("и" if sex == "F" else "я")
    if last in "оеуюыиэ":
        return word
    return word + "а"


@dataclass
class Person:
    id: str
    givn: str = ""
    surn: str = ""
    sex: str = ""
    birt: str = ""
    birt_plac: str = ""
    deat: str = ""
    deat_plac: str = ""
    deceased: bool = False
    occu: str = ""
    note: str = ""
    fams: list[str] = field(default_factory=list)
    famc: str = ""
    email: str = ""
    sources: list[str] = field(default_factory=list)
    # Anchor year for age-based privacy checks, defaults to date.today().year
    reference_year: int = field(default_factory=lambda: date.today().year)

    @property
    def name(self) -> str:
        return clean_name(self.givn)

    @property
    def surname(self) -> str:
        return clean_name(self.surn)

    @property
    def label(self) -> str:
        if self.surname and self.name:
            return f"{self.surname} {self.name}"
        return self.name or self.surname or "неизвестный"

    @property
    def display_name(self) -> str:
        """Name in natural reading order: 'Алексей Петрович Астафьев'."""
        if self.surname and self.name:
            return f"{self.name} {self.surname}"
        return self.name or self.surname or "неизвестный"

    @property
    def short(self) -> str:
        parts = self.name.split()
        if parts and self.surname:
            return f"{self.surname} {parts[0]}"
        return self.label

    @property
    def years(self) -> str:
        birth = format_date(self.birt)
        death = format_date(self.deat)
        if birth and death:
            return f"{birth} – {death}"
        if birth:
            return f"р. {birth}"
        if death:
            return f"ум. {death}"
        return "? – ?"

    @property
    def is_living(self) -> bool:
        """True only for people without a death record who could plausibly be alive."""
        if self.deat or self.deceased:
            return False
        birth_year = year_only(self.birt)
        if birth_year:
            return int(birth_year) > self.reference_year - PRESUMED_DECEASED_AGE
        # Fail-safe: if birth year is unknown and there is no death record,
        # treat them as living to avoid accidental disclosure of details.
        return True

    @property
    def public_years(self) -> str:
        """Years safe to publish: living people are reduced to a birth year."""
        if self.is_living:
            year = year_only(self.birt)
            return f"р. {year}" if year else "ныне живущий"
        return self.years

    @property
    def public_place(self) -> str:
        """Birthplace is hidden for living people."""
        if self.is_living:
            return ""
        return canonical_place(self.birt_plac or self.deat_plac)

    @property
    def has_match(self) -> bool:
        """A match with another researcher's tree — a lead, not evidence."""
        return bool(self.sources)

    @property
    def has_derived_date(self) -> bool:
        """Date was computed from relatives rather than read from a record."""
        head = (self.birt or "").split(" ", 1)[0]
        return head in {"ок.", "до", "после", "между"}

    @property
    def birth_precision(self) -> str:
        """How exactly the birth date is known: missing/qualified/full/month/year."""
        value = (self.birt or "").strip()
        if not value:
            return "missing"
        if self.has_derived_date:
            return "qualified"
        if re.fullmatch(r"\d{1,2}\s+[а-яё]+\s+\d{4}", value, re.IGNORECASE):
            return "full"
        if re.fullmatch(r"[а-яё]+\.\s+\d{4}", value, re.IGNORECASE):
            return "month_year"
        if re.fullmatch(r"\d{4}", value):
            return "year"
        return "other"

    @property
    def is_reconstructed(self) -> bool:
        """Date was derived rather than recorded: treat the entry as a hypothesis."""
        return self.has_derived_date or not self.birt


def year_only(date: str) -> str:
    """Extract a four-digit year from a date value."""
    match = re.search(r"\b(\d{4})\b", date or "")
    return match.group(1) if match else ""


@dataclass
class Family:
    id: str
    husb: str = ""
    wife: str = ""
    chil: list[str] = field(default_factory=list)
    marr: str = ""
    marr_plac: str = ""


def ancestors(
    person_id: str,
    people: dict[str, Person],
    families: dict[str, Family],
    max_depth: int = 8,
) -> list[tuple[int, Person, str]]:
    """Return (depth, person, side) where side is self/father/mother lineage marker."""

    result: list[tuple[int, Person, str]] = []

    def walk(pid: str, depth: int, side: str) -> None:
        if depth > max_depth or pid not in people:
            return
        person = people[pid]
        result.append((depth, person, side))
        if not person.famc or person.famc not in families:
            return
        family = families[person.famc]
        if family.husb:
            walk(family.husb, depth + 1, "father" if depth == 0 else side)
        if family.wife:
            walk(family.wife, depth + 1, "mother" if depth == 0 else side)

    walk(person_id, 0, "self")
    return result


def direct_lines(
    root_id: str,
    people: dict[str, Person],
    families: dict[str, Family],
    generations: int = 8,
) -> dict[str, list[Person]]:
    """Build paternal and maternal ancestor chains."""

    def chain(pid: str, follow: str, depth: int = 0) -> list[Person]:
        out: list[Person] = []
        current = pid
        while depth < generations and current in people:
            person = people[current]
            out.append(person)
            if not person.famc or person.famc not in families:
                break
            family = families[person.famc]
            parent = family.husb if follow == "father" else family.wife
            if not parent:
                break
            current = parent
            depth += 1
        return out

    root = people[root_id]
    lines: dict[str, list[Person]] = {
        "father": chain(root_id, "father"),
        "mother": chain(root_id, "mother"),
    }

    if root.famc in families:
        family = families[root.famc]
        if family.wife:
            lines["mother_branch"] = chain(family.wife, "mother")
        if family.husb:
            lines["father_branch"] = chain(family.husb, "father")

    return lines


def canonical_surname(surname: str, known: set[str]) -> str:
    """Fold feminine surname forms into masculine ones (Матюхина → Матюхин)."""
    if surname.endswith("ая"):
        masculine = surname[:-2] + "ий"
        if masculine in known:
            return masculine
    if surname.endswith("а") and surname[:-1] in known:
        return surname[:-1]
    return surname


def stats(
    people: dict[str, Person],
    families: dict[str, Family],
    database: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate counts for the published statistics blocks.

    The chart persons alone cannot reproduce the aggregates of the lost
    243-person export, so published values from family.yaml (`database`)
    override the computed ones; everything not overridden is computed.
    """
    raw_surnames = {p.surname for p in people.values() if p.surname}
    surnames = Counter(
        canonical_surname(p.surname, raw_surnames) for p in people.values() if p.surname
    )
    birth_years = [int(y) for y in (year_only(p.birt) for p in people.values()) if y]
    precision = Counter(p.birth_precision for p in people.values())
    result: dict[str, Any] = {
        "people": len(people),
        "families": len(families),
        "surnames": len(surnames),
        "top_surnames": surnames.most_common(12),
        "top_places": [],
        "with_birth": sum(1 for p in people.values() if p.birt),
        "with_death": sum(1 for p in people.values() if p.deat),
        "matched": sum(1 for p in people.values() if p.has_match),
        # Birth-date precision: these five buckets add up to the whole database.
        "birth_full": precision["full"],
        "birth_year_only": precision["year"],
        "birth_month_year": precision["month_year"] + precision["other"],
        "birth_qualified": precision["qualified"],
        "birth_missing": precision["missing"],
        "earliest_year": min(birth_years, default=0),
    }
    if database:
        for key in (
            "people", "families", "surnames", "with_birth", "with_death",
            "birth_full", "birth_year_only", "birth_month_year",
            "birth_qualified", "birth_missing",
        ):
            if key in database:
                result[key] = database[key]
        if "earliest_birth" in database:
            result["earliest_year"] = database["earliest_birth"]
        if "matches" in database:
            result["matched"] = database["matches"]
        if "deaths" in database:
            result["with_death"] = database["deaths"]
        if "surnames_total" in database:
            result["surnames"] = database["surnames_total"]
        if database.get("top_surnames"):
            result["top_surnames"] = [
                (entry["name"], entry["count"]) for entry in database["top_surnames"]
            ]
    return result


def _validate(data: dict[str, Any], path: Path) -> None:
    """Fail fast with a clear message when family.yaml is malformed.

    Mirrors the spirit of the former validate_inputs(): wrong shape, dangling
    references or privacy violations stop the build before anything renders.
    """
    for key in ("meta", "root", "persons"):
        if key not in data:
            fail(f"в {path.name} нет обязательного раздела «{key}».")

    persons = data["persons"]
    if not isinstance(persons, list) or not persons:
        fail("раздел «persons» пуст или не список.")

    seen: set[str] = set()
    for index, raw in enumerate(persons, 1):
        where = f"персона №{index}"
        if not isinstance(raw, dict):
            fail(f"{where} — не словарь.")
        pid = str(raw.get("id", "")).strip()
        if not pid:
            fail(f"{where} — нет id.")
        where = f"персона {pid}"
        if pid in seen:
            fail(f"{where} — id не уникален.")
        seen.add(pid)
        if not (raw.get("name") or raw.get("surname")):
            fail(f"{where} — нет ни имени, ни фамилии.")
        status = raw.get("status", "hyp")
        if status not in ALLOWED_STATUS:
            fail(f"{where} — статус «{status}»; допустимо {' / '.join(sorted(ALLOWED_STATUS))}.")

        birth = str(raw.get("birth", "") or "")
        death = str(raw.get("death", "") or "")
        deceased = bool(raw.get("deceased", False))
        if birth and death and not deceased:
            fail(f"{where} — есть дата смерти, но deceased не выставлен.")
        if not deceased:
            if birth and not re.fullmatch(r"\d{4}", birth):
                fail(
                    f"{where} ({raw.get('name', '')}) — возможно живой, но дата рождения "
                    f"«{birth}» не голый год. Для живых публикуется только год."
                )
            if raw.get("place"):
                fail(f"{where} ({raw.get('name', '')}) — живым место рождения не публикуется.")

    root = data["root"]
    if root not in seen:
        fail(f"root «{root}» не найден среди персон.")

    for index, raw in enumerate(persons, 1):
        pid = raw["id"]
        for role in ("father", "mother"):
            ref = raw.get(role) or ""
            if ref and ref not in seen:
                fail(f"персона {pid}: {role} «{ref}» не найден среди персон.")
        if raw.get("father") and raw.get("father") == raw.get("mother"):
            fail(f"персона {pid}: отец и мать — один и тот же id.")

    for index, fam in enumerate(data.get("families") or [], 1):
        if not isinstance(fam, dict):
            fail(f"семья №{index} — не словарь.")
        for role in ("husb", "wife"):
            ref = fam.get(role) or ""
            if ref and ref not in seen:
                fail(f"семья №{index}: {role} «{ref}» не найден среди персон.")
        for child in fam.get("chil") or []:
            if child not in seen:
                fail(f"семья №{index}: ребёнок «{child}» не найден среди персон.")

    # A person must not be their own ancestor.
    parents: dict[str, tuple[str, str]] = {
        raw["id"]: (raw.get("father") or "", raw.get("mother") or "") for raw in persons
    }
    for pid in parents:
        current, steps = pid, 0
        while steps <= len(parents):
            father, mother = parents.get(current, ("", ""))
            nxt = father or mother
            if not nxt:
                break
            if nxt == pid:
                fail(f"персона {pid} — цикл в ссылках отец/мать.")
            current = nxt
            steps += 1


def load_family(path: Path) -> tuple[dict[str, Person], dict[str, Family], dict[str, Any]]:
    """Read family.yaml, validate it and build the Person/Family model."""
    if not path.exists():
        sys.exit(
            f"Ошибка: файл данных не найден ({path}).\n"
            "family.yaml хранится только локально и не коммитится; при необходимости "
            "восстановите его скриптом scripts/extract_data.py из опубликованного index.html."
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        sys.exit(f"Ошибка: {path.name} не читается как YAML:\n{exc}")

    _validate(data, path)
    reference_year = date.today().year

    people: dict[str, Person] = {}
    raw_by_id: dict[str, dict[str, Any]] = {}
    for raw in data["persons"]:
        person = Person(
            id=str(raw["id"]),
            givn=str(raw.get("name", "") or ""),
            surn=str(raw.get("surname", "") or ""),
            sex=str(raw.get("sex", "") or ""),
            birt=str(raw.get("birth", "") or ""),
            deat=str(raw.get("death", "") or ""),
            birt_plac=str(raw.get("place", "") or ""),
            deceased=bool(raw.get("deceased", False)),
            note=str(raw.get("note", "") or ""),
            reference_year=reference_year,
        )
        people[person.id] = person
        raw_by_id[person.id] = raw

    # Parent links from the chart become families, the way the former export stored them:
    # children sharing the same (father, mother) pair share one famc family.
    families: dict[str, Family] = {}
    pair_of: dict[str, tuple[str, str]] = {}
    children_by_pair: dict[tuple[str, str], list[str]] = {}
    for person in people.values():
        pair = (raw_by_id[person.id].get("father") or "", raw_by_id[person.id].get("mother") or "")
        pair_of[person.id] = pair
        if pair != ("", ""):
            children_by_pair.setdefault(pair, []).append(person.id)

    explicit: list[dict[str, Any]] = list(data.get("families") or [])
    next_family = 1

    def new_family_id() -> str:
        nonlocal next_family
        fid = f"f{next_family:02d}"
        next_family += 1
        return fid

    family_by_pair: dict[tuple[str, str], str] = {}
    for fam in explicit:
        fid = new_family_id()
        family = Family(
            id=fid,
            husb=str(fam.get("husb") or ""),
            wife=str(fam.get("wife") or ""),
            chil=[str(c) for c in (fam.get("chil") or [])],
        )
        families[fid] = family
        pair = (family.husb, family.wife)
        family_by_pair[pair] = fid
        for child in children_by_pair.pop(pair, []):
            if child not in family.chil:
                family.chil.append(child)
        if family.husb:
            people[family.husb].fams.append(fid)
        if family.wife:
            people[family.wife].fams.append(fid)

    for (father, mother), children in sorted(children_by_pair.items()):
        fid = new_family_id()
        families[fid] = Family(id=fid, husb=father, wife=mother, chil=children)
        family_by_pair[(father, mother)] = fid
        if father:
            people[father].fams.append(fid)
        if mother:
            people[mother].fams.append(fid)

    for person in people.values():
        pair = pair_of[person.id]
        if pair != ("", ""):
            person.famc = family_by_pair.get(pair, "")

    meta: dict[str, Any] = {
        "file": path.name,
        "date": str((data.get("meta") or {}).get("export_date", "") or ""),
        "root": str(data["root"]),
        "database": data.get("database") or {},
        "gaps": data.get("gaps") or [],
    }
    return people, families, meta


if __name__ == "__main__":
    yaml_path = Path(__file__).resolve().parents[1] / "data" / "family.yaml"
    people, families, meta = load_family(yaml_path)
    root = people[meta["root"]]
    from pprint import pprint

    pprint({
        "persons": len(people),
        "families": len(families),
        "root": root.label,
        "years": root.years,
        "father_line": [p.short for p in direct_lines(meta["root"], people, families)["father"]],
    })
