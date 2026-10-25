#!/usr/bin/env python3
"""Enrich data/family.yaml from the recovered (partial) GEDCOM export.

The migration itself (HTML -> YAML) is done by extract_data.py; this script is
a one-off bridge for the partial GEDCOM found later (data/partial.ged,
MyHeritage SKIBA export dated 17 JUL 2026, 233 INDI / 90 FAM — the published
aggregates say 243 / 93, so the file is incomplete and has a few corrupted
bytes inside one NOTE). Rules:

- match by cleaned (surname, given name); ambiguity is resolved by birth year,
  otherwise the person is skipped and reported;
- dates: a more precise date wins only when the year agrees; a different year
  is a conflict (index.html stays the visible reference) — and living people
  never receive exact dates (privacy fuse);
- structure: parent/child links of persons already in YAML are never added or
  changed, because the published tree (index.html) is the visual reference;
  side relatives are added wholesale with `source: ged` and linked among
  themselves and to the existing people;
- every contradiction is recorded in the `conflicts:` section of family.yaml.

The script can be deleted after the migration (see ADR «Миграция на YAML с
использованием частичного GEDCOM»).
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "family.yaml"

PRESUMED_DECEASED_AGE = 110
THIS_YEAR = date.today().year

# Documented identity from the former parse_gedcom.py «Inject from 1834» block:
# the export's @I155@ (Федот Матюхин, BEF 1852) is the same person the chart
# shows as bare «Федот» (ок. 1818 — the injected research value). The YAML
# keeps the published dates; the GEDCOM ones go to conflicts.
ALIAS_GED_IDS = {"@I155@": "Федот"}

# Service records inside the export that are not people (MyHeritage photo
# attachments get a pseudo-INDI with this fixed id).
SERVICE_GED_IDS = {"@I88888888@"}

MONTHS_RU = {
    "JAN": "января", "FEB": "февраля", "MAR": "марта", "APR": "апреля",
    "MAY": "мая", "JUN": "июня", "JUL": "июля", "AUG": "августа",
    "SEP": "сентября", "OCT": "октября", "NOV": "ноября", "DEC": "декабря",
}
MONTHS_RU_SHORT = {
    "JAN": "янв.", "FEB": "фев.", "MAR": "мар.", "APR": "апр.",
    "MAY": "мая", "JUN": "июн.", "JUL": "июл.", "AUG": "авг.",
    "SEP": "сен.", "OCT": "окт.", "NOV": "ноя.", "DEC": "дек.",
}
DATE_QUALIFIERS = {"ABT": "ок.", "BEF": "до", "AFT": "после", "EST": "ок.", "CAL": "ок."}


def format_date(value: str) -> str:
    """Render a GEDCOM date in Russian — same rules as the former
    parse_gedcom.format_date, so values match the published card texts."""
    value = (value or "").strip()
    if not value:
        return ""
    range_match = re.match(r"^BET\s+(.+?)\s+AND\s+(.+)$", value, re.IGNORECASE)
    if range_match:
        return f"между {format_date(range_match.group(1))} и {format_date(range_match.group(2))}"
    prefix = ""
    head = value.split(" ", 1)[0].upper()
    if head in DATE_QUALIFIERS:
        prefix = DATE_QUALIFIERS[head] + " "
        value = value[len(head):].strip()
    full = re.match(r"^(\d{1,2})\s+([A-Z]{3})\s+(\d{4})$", value, re.IGNORECASE)
    if full:
        day, month, year = full.groups()
        return f"{prefix}{int(day)} {MONTHS_RU.get(month.upper(), month)} {year}"
    month_year = re.match(r"^([A-Z]{3})\s+(\d{4})$", value, re.IGNORECASE)
    if month_year:
        month, year = month_year.groups()
        return f"{prefix}{MONTHS_RU_SHORT.get(month.upper(), month)} {year}"
    return f"{prefix}{value}"


def clean_name(value: str) -> str:
    value = re.sub(r"\(\d+\)", "", value or "")
    value = re.sub(r"\?{2,}", "", value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip()


def year_of(value: str) -> str:
    m = re.search(r"\b(\d{4})\b", value or "")
    return m.group(1) if m else ""


def find_ged_file() -> Path:
    """Locate the partial GEDCOM; several candidates → ask the user."""
    candidates = sorted(
        {p for p in ROOT.rglob("*.ged") if "_rebuild_check" not in p.parts}
    )
    if not candidates:
        sys.exit("Ошибка: *.ged не найден в проекте — обогащать нечем.")
    if len(candidates) > 1:
        listing = "\n".join(f"  - {p}" for p in candidates)
        sys.exit(f"Ошибка: найдено несколько *.ged, выберите нужный:\n{listing}")
    return candidates[0]


def parse_ged(path: Path) -> tuple[dict[str, dict], dict[str, dict], int]:
    """Minimal GEDCOM reader for the enrichment; returns (indis, fams, bad_chars).

    The file has a handful of corrupted bytes inside one NOTE; those decode to
    U+FFFD and the affected text is simply not imported.
    """
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
        bad = 0
    except UnicodeDecodeError:
        text = raw.decode("utf-8-sig", errors="replace")
        bad = text.count("\ufffd")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    indis: dict[str, dict] = {}
    fams: dict[str, dict] = {}
    current: dict | None = None
    for line in text.split("\n"):
        m = re.match(r"^(\d+)\s+(?:(@[^@]+@)\s+)?(\S+)(?:\s+(.*))?$", line)
        if not m:
            continue
        level, xref, tag, value = int(m.group(1)), m.group(2), m.group(3), m.group(4) or ""
        if level == 0:
            if current and current["_kind"] == "INDI":
                indis[current["id"]] = current
            elif current and current["_kind"] == "FAM":
                fams[current["id"]] = current
            kind = "INDI" if tag == "INDI" else "FAM" if tag == "FAM" else None
            current = {"_kind": kind, "id": xref or ""} if kind else None
            continue
        if current is None:
            continue
        if tag == "GIVN" and not current.get("givn"):
            current["givn"] = value
        elif tag == "SURN" and not current.get("surn"):
            current["surn"] = value
        elif tag == "SEX":
            current["sex"] = value
        elif tag == "BIRT":
            current["_ctx"] = "BIRT"
        elif tag == "DEAT":
            current["_ctx"] = "DEAT"
            current["deceased"] = True
        elif tag == "DATE" and current.get("_ctx") in ("BIRT", "DEAT"):
            key = "BIRT" if current["_ctx"] == "BIRT" else "DEAT"
            if not current.get(key):
                current[key] = value
        elif tag == "PLAC" and current.get("_ctx") in ("BIRT", "DEAT"):
            key = "birt_plac" if current["_ctx"] == "BIRT" else "deat_plac"
            if not current.get(key):
                current[key] = value
        elif tag == "FAMC":
            current["famc"] = value
        elif tag == "FAMS":
            current.setdefault("fams", []).append(value)
        elif tag == "HUSB":
            current["husb"] = value
        elif tag == "WIFE":
            current["wife"] = value
        elif tag == "CHIL":
            current.setdefault("chil", []).append(value)
    return indis, fams, bad


def main() -> None:
    ged_path = find_ged_file()
    indis, fams, bad_chars = parse_ged(ged_path)
    print(f"GED: {ged_path.name}: {len(indis)} INDI, {len(fams)} FAM, битых символов: {bad_chars}")

    data = yaml.safe_load(DATA_PATH.read_text(encoding="utf-8"))
    persons: list[dict] = data["persons"]
    yaml_by_name: dict[tuple[str, str], dict] = {}
    for p in persons:
        yaml_by_name.setdefault((p["surname"], p["name"]), p)

    def display(p: dict) -> str:
        return f"{p['surname']} {p['name']}".strip()

    # --- index GEDCOM people by cleaned name ---------------------------------
    ged_by_name: dict[tuple[str, str], list[str]] = {}
    skipped_ged: list[str] = []
    for iid, ged in indis.items():
        surn, givn = clean_name(ged.get("surn", "")), clean_name(ged.get("givn", ""))
        if "\ufffd" in surn + givn or not (surn or givn):
            skipped_ged.append(iid)  # безымянные заглушки («??????») и битые записи
            continue
        ged_by_name.setdefault((surn, givn), []).append(iid)

    ged_to_pid: dict[str, str] = {}
    conflicts: list[dict] = list(data.get("conflicts") or [])
    updated_dates = date_skipped_living = 0
    matched: set[str] = set()

    def try_match(p: dict) -> str:
        """Resolve a YAML person to a GEDCOM id: primary (surname, given name),
        fallback for published mononyms — a unique GED person with the same
        given name but an extra surname (the chart shows «Федот», the export
        has «Федот Матюхин»)."""
        candidates = list(ged_by_name.get((p["surname"], p["name"]), []))
        if not candidates and p["surname"] == "" and p["name"]:
            own_year = year_of(p.get("birth", ""))
            mononym = [
                i for i, g in indis.items()
                if i not in matched
                and clean_name(g.get("givn", "")) == p["name"]
                and year_of(format_date(g.get("BIRT", ""))) in ("", own_year)
            ]
            if len(mononym) == 1:
                ged = indis[mononym[0]]
                conflicts.append({
                    "kind": "name-form",
                    "id": p["id"],
                    "who": p["name"],
                    "detail": (
                        f"в GED персона значится как «{clean_name(ged.get('givn', ''))} "
                        f"{clean_name(ged.get('surn', ''))}», на сайте опубликована без фамилии; "
                        "считаем одним человеком."
                    ),
                })
                return mononym[0]
            if len(mononym) > 1:
                conflicts.append({
                    "kind": "ambiguity",
                    "id": p["id"],
                    "who": p["name"],
                    "detail": f"в GED несколько персон с именем «{p['name']}» — не сопоставлено.",
                })
                return ""
        if len(candidates) > 1:
            ged_years = {c: year_of(format_date(indis[c].get("BIRT", ""))) for c in candidates}
            own = year_of(p.get("birth", ""))
            by_year = [c for c in candidates if ged_years[c] == own]
            if len(by_year) != 1:
                conflicts.append({
                    "kind": "ambiguity",
                    "id": p["id"],
                    "who": f"{p['surname']} {p['name']}".strip(),
                    "detail": f"в GED несколько одноимённых персон {candidates} — не сопоставлено.",
                })
                return ""
            candidates = by_year
        if not candidates:
            return ""
        # Годовой фильтр: совпадающие ключи с разными годами рождения — разные
        # люди (архивная Анна ок. 1820 ≠ Анна 1915 из базы). Совпадение отдаём
        # pass 2, которая внесёт одноимённого человека отдельно.
        ged = indis[candidates[0]]
        own = year_of(p.get("birth", ""))
        ged_year = year_of(format_date(ged.get("BIRT", "")))
        if own and ged_year and own != ged_year:
            return ""
        return candidates[0]

    matched: set[str] = set()

    # --- pass 1: enrich persons already in the YAML ---------------------------
    for p in persons:
        if p.get("source") == "ged":
            # Idempotency: an added person records its GEDCOM id in the note.
            m = re.search(r"id в выгрузке (@I\d+@)", p.get("note", ""))
            if m and m.group(1) in indis:
                matched.add(m.group(1))
                ged_to_pid[m.group(1)] = p["id"]
                continue
        iid = try_match(p)
        if not iid:
            continue
        matched.add(iid)
        ged = indis[iid]
        ged_to_pid[iid] = p["id"]

        living = not p.get("deceased", False)
        for field, src in (("birth", "BIRT"), ("death", "DEAT")):
            ged_display = format_date(ged.get(src, ""))
            if not ged_display:
                continue
            yaml_value = p.get(field, "")
            if not yaml_value:
                if living and not re.fullmatch(r"\d{4}", ged_display):
                    date_skipped_living += 1  # privacy fuse
                else:
                    p[field] = ged_display
                    if field == "death":
                        p["_ged_death"] = True
                    updated_dates += 1
            elif yaml_value == ged_display:
                pass
            elif year_of(yaml_value) == year_of(ged_display) and not living:
                p[field] = ged_display  # тот же год, точнее дата
                if field == "death":
                    p["_ged_death"] = True
                updated_dates += 1
            elif year_of(yaml_value) == year_of(ged_display):
                date_skipped_living += 1  # живому точную дату не публикуем
            else:
                conflicts.append({
                    "kind": "date-mismatch",
                    "id": p["id"],
                    "who": display(p),
                    "field": field,
                    "yaml": yaml_value,
                    "ged": ged_display,
                    "decision": "оставлено значение из index.html",
                })
        if not p.get("sex") and ged.get("sex"):
            p["sex"] = ged["sex"]

    # --- documented alias: merge GED identities into published mononyms -------
    for iid, mononym in ALIAS_GED_IDS.items():
        if iid in matched or iid not in indis:
            continue
        alias = next((p for p in persons if p["surname"] == "" and p["name"] == mononym), None)
        if alias is None:
            continue
        matched.add(iid)
        ged_to_pid[iid] = alias["id"]
        conflicts.append({
            "kind": "name-form",
            "id": alias["id"],
            "who": mononym,
            "detail": (
                f"персона GED {iid} «{clean_name(indis[iid].get('givn', ''))} "
                f"{clean_name(indis[iid].get('surn', ''))}» объединена с {alias['id']} "
                f"«{mononym}» по документированной связи старого inject-блока; даты GED "
                "в конфликтах ниже."
            ),
        })
        ged = indis[iid]
        for field, src in (("birth", "BIRT"), ("death", "DEAT")):
            ged_display = format_date(ged.get(src, ""))
            if ged_display and alias.get(field, "") != ged_display:
                conflicts.append({
                    "kind": "date-mismatch",
                    "id": alias["id"],
                    "who": mononym,
                    "field": field,
                    "yaml": alias.get(field, ""),
                    "ged": ged_display,
                    "decision": "оставлено значение из index.html",
                })

    # --- pass 2: add side people that exist only in the GEDCOM ----------------
    next_index = len(persons) + 1
    existing_ged_names = {
        (p["surname"], p["name"]) for p in persons if p.get("source") == "ged"
    }
    for iid, ged in indis.items():
        if iid in matched or iid in skipped_ged or iid in SERVICE_GED_IDS:
            continue
        surn, givn = clean_name(ged.get("surn", "")), clean_name(ged.get("givn", ""))
        key = (surn, givn)
        if key in existing_ged_names:
            continue  # идемпотентность повторного запуска
        if key in yaml_by_name:
            # Имя занято: это тот же человек, если годы совпадают (или оба
            # неизвестны); иначе в GED свой одноимённый человек — добавляем.
            ged_year = year_of(format_date(ged.get("BIRT", "")))
            same = [
                p for p in persons
                if (p["surname"], p["name"]) == key
                and year_of(p.get("birth", "")) in ("", ged_year)
            ]
            if same:
                conflicts.append({
                    "kind": "name-collision",
                    "id": same[0]["id"],
                    "who": f"{surn} {givn}".strip(),
                    "detail": (
                        f"одноимённая персона GED ({iid}, р. {ged_year or '?'}) не добавлена: "
                        "считаем совпадающей с уже внесённой."
                    ),
                })
                continue
        birth_display = format_date(ged.get("BIRT", ""))
        death_display = format_date(ged.get("DEAT", ""))
        deceased = bool(ged.get("deceased")) or bool(death_display)
        if not deceased:
            by = year_of(birth_display)
            deceased = bool(by) and int(by) <= THIS_YEAR - PRESUMED_DECEASED_AGE
        if not deceased:
            # Privacy fuse: living side relatives keep only the birth year.
            birth_display = year_of(birth_display)
            death_display = ""
        pid = f"p{next_index:03d}"
        next_index += 1
        ged_to_pid[iid] = pid
        person = {
            "id": pid,
            "surname": surn,
            "name": givn,
            "birth": birth_display,
            "death": death_display,
            "sex": ged.get("sex", ""),
            "deceased": deceased,
            "status": "hyp" if (not birth_display or re.match(r"^(ок\.|до|после|между)", birth_display)) else "ok",
            "father": "",
            "mother": "",
            "place": (ged.get("birt_plac", "") or ged.get("deat_plac", "")) if deceased else "",
            "note": f"Добавлен из частичного GEDCOM ({ged_path.name}, экспорт 17 июля 2026); id в выгрузке {iid}.",
            "source": "ged",
        }
        if death_display:
            person["_ged_death"] = True
        persons.append(person)
    added = sum(1 for p in persons if p.get("source") == "ged")

    # --- pass 3: parent links for added people only ---------------------------
    # Persons already in the YAML keep exactly the links extracted from
    # index.html; side people get their FAMC parents wherever those resolve.
    linked = 0
    unresolved = []
    for iid, ged in indis.items():
        child_pid = ged_to_pid.get(iid)
        if not child_pid:
            continue
        child = next(p for p in persons if p["id"] == child_pid)
        if child.get("source") != "ged":
            continue
        famc = fams.get(ged.get("famc", ""))
        if not famc:
            continue
        for role, key in (("father", "husb"), ("mother", "wife")):
            parent_iid = famc.get(key, "")
            if not parent_iid:
                continue
            parent_pid = ged_to_pid.get(parent_iid)
            if not parent_pid:
                parent_ged = indis.get(parent_iid)
                if parent_ged:
                    parent_key = (
                        clean_name(parent_ged.get("surn", "")),
                        clean_name(parent_ged.get("givn", "")),
                    )
                    parent = yaml_by_name.get(parent_key)
                    parent_pid = parent["id"] if parent else ""
            if parent_pid:
                child[role] = parent_pid
                linked += 1
            else:
                unresolved.append(f"{child_pid} ← {role} {parent_iid}")

    # Gaps that this import closes (side relatives are now in the YAML).
    RESOLVED_GAP_PREFIXES = (
        "Боковые сыновья Григория Спиридоновича",
        "Восемь детей Василия Васильевича",
        "Родня по браку",
    )
    for gap in data.get("gaps") or []:
        if any(gap.get("what", "").startswith(prefix) for prefix in RESOLVED_GAP_PREFIXES):
            gap["resolved"] = (
                "закрыто обогащением из частичного GEDCOM: персоны внесены с source: ged; "
                "для родни по браку — частично (состав перенесён, детали — как в выгрузке)."
            )

    # --- pass 4: plausibility check on death dates ----------------------------
    # The export contains obvious record-merge errors (Спиридон, р. 1861,
    # с датой смерти 2016 — 155 лет). Дата смерти не может отстоять от года
    # рождения (или от рождения старшего ребёнка, если год рождения неизвестен)
    # больше чем на 110 лет; такие даты не переносятся и попадают в conflicts.
    by_id: dict[str, dict] = {p["id"]: p for p in persons}
    children_of: dict[str, list[str]] = {}
    for p in persons:
        for role in ("father", "mother"):
            if p.get(role):
                children_of.setdefault(p[role], []).append(p["id"])

    def child_years(pid: str) -> list[int]:
        years = []
        for cid in children_of.get(pid, []):
            y = year_of(by_id[cid].get("birth", ""))
            if y:
                years.append(int(y))
        return years

    implausible = 0
    for p in persons:
        if not p.get("_ged_death"):
            continue  # опубликованные в HTML даты не трогаем
        death_year = year_of(p.get("death", ""))
        if not death_year:
            continue
        own = year_of(p.get("birth", ""))
        if own:
            ref = int(own)
            basis = "года рождения"
        else:
            kids = child_years(p["id"])
            if not kids:
                continue
            ref = min(kids)
            basis = "рождения старшего ребёнка"
        if int(death_year) - ref > PRESUMED_DECEASED_AGE:
            conflicts.append({
                "kind": "implausible-date",
                "id": p["id"],
                "who": display(p),
                "field": "death",
                "yaml": "",
                "ged": p["death"],
                "detail": (
                    f"дата смерти на {int(death_year) - ref} лет позже {basis} — "
                    "очевидная склейка записей в выгрузке; не перенесена."
                ),
            })
            p["death"] = ""
            implausible += 1

    for p in persons:
        p.pop("_ged_death", None)  # служебная пометка не попадает в YAML

    # Один и тот же конфликт не должен плодиться при повторных прогонах.
    unique_conflicts: list[dict] = []
    seen_conflicts: set[tuple] = set()
    for c in conflicts:
        key = tuple(sorted((k, str(v)) for k, v in c.items()))
        if key not in seen_conflicts:
            seen_conflicts.add(key)
            unique_conflicts.append(c)
    data["conflicts"] = unique_conflicts
    data.setdefault("meta", {})["enriched_from"] = (
        f"частичный GEDCOM {ged_path.name} ({len(indis)} INDI / {len(fams)} FAM, "
        f"экспорт MyHeritage SKIBA от 17 июля 2026); файл не коммитится"
    )
    DATA_PATH.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    print(
        f"Сопоставлено: {len(ged_to_pid) - added} персон YAML, добавлено: {added}, "
        f"дат обновлено: {updated_dates}, дат не перенесено (живые): {date_skipped_living}, "
        f"связей добавлено: {linked}, конфликтов: {len(conflicts)}"
    )
    if unresolved:
        print("Неразрешённые родители добавленных персон:")
        for line in unresolved:
            print("  ", line)


if __name__ == "__main__":
    main()
