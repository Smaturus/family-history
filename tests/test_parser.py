"""Тесты загрузчика YAML-данных (parse_data.py) и приватного предохранителя.

Все данные — вымышленные (tests/fixtures/minimal.yaml); реальные ПДн в тестах
запрещены политикой проекта (см. docs/architecture.md). Якорная логика
идентификаторов прежней выгрузки (@I155@/@F59@) упразднена вместе с ней — см. ADR
«Отказ от внешнего формата в пользу YAML» (ведётся локально).
"""

import shutil
import subprocess
import sys
from pathlib import Path

import yaml

import pytest

from parse_data import Person, direct_lines, load_family

REPO = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "minimal.yaml"


def load(path=FIXTURE):
    return load_family(path)


def fixture_data():
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def build_in_tmp(tmp_path, with_data=True):
    """Полная сборка в копии репозитория; возвращает (exit_code, stderr, html)."""
    dst = tmp_path / "repo"
    shutil.copytree(REPO, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    (dst / "data").mkdir(exist_ok=True)
    if with_data:
        shutil.copy(FIXTURE, dst / "data" / "family.yaml")
    else:
        # В рабочей копии data/family.yaml теперь коммитится — для негативного
        # сценария убираем и его.
        (dst / "data" / "family.yaml").unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(dst / "scripts" / "build_site.py")],
        capture_output=True, text=True, encoding="utf-8", cwd=dst, timeout=300,
    )
    html = ""
    if proc.returncode == 0:
        html = (dst / "index.html").read_text(encoding="utf-8")
    return proc.returncode, proc.stderr + proc.stdout, html


# --- Загрузка фикстуры и структура модели ------------------------------------


def test_fixture_loads():
    """Тест 1: фикстура читается, все персон и семьи на месте."""
    people, families, meta = load()
    assert set(people) == {f"t0{i}" for i in range(1, 9)}
    assert people["t01"].surname == "Тестов"
    assert meta["root"] == "t01"
    assert meta["date"] == "17 июля 2026"


def test_parent_links_become_families():
    """Ссылки отец/мать собираются в семьи: общие родители — общая famc-семья."""
    people, families, _ = load()
    # t04+t05 — родители корня t01
    fam = families[people["t01"].famc]
    assert fam.husb == "t04" and fam.wife == "t05" and "t01" in fam.chil
    # якорная семья объединена с автоматической: t03 в той же семье, что t01/t02
    anchor = people["t01"].fams[0]
    assert families[anchor].husb == "t01" and families[anchor].wife == "t02"
    assert families[anchor].chil == ["t03"]
    # t08 — отец t02 без матери: семья с пустой женой
    fam2 = families[people["t02"].famc]
    assert fam2.husb == "t08" and fam2.wife == ""


def test_direct_lines_walk_the_chain():
    """Прямая отцовская линия корня доходит до предка без дат."""
    people, families, meta = load()
    line = [p.id for p in direct_lines(meta["root"], people, families)["father"]]
    assert line == ["t01", "t04", "t06", "t07"]


def test_status_matches_birth_date_shape():
    """Статус карточки выводится из даты: «ок.»/нет года → гипотеза."""
    people, _, _ = load()
    assert people["t04"].birth_precision == "year"
    assert not people["t04"].is_reconstructed
    assert people["t06"].is_reconstructed          # «ок. 1910»
    assert people["t07"].is_reconstructed          # дат нет вовсе


# --- Приватность -------------------------------------------------------------


def test_living_year_only_stays_public():
    """Год рождения живого разрешён политикой публикации."""
    people, _, _ = load()
    assert people["t01"].is_living
    assert people["t01"].public_years == "р. 1971"
    assert people["t01"].public_place == ""


def test_living_exact_date_rejected(tmp_path):
    """Приватный предохранитель: точная дата живого отклоняется при загрузке."""
    data = fixture_data()
    data["persons"][0]["birth"] = "17 апреля 1975"
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        load(bad)
    assert "только год" in str(excinfo.value)


def test_living_place_rejected(tmp_path):
    """Живым место рождения не публикуется — загрузка падает с ошибкой."""
    data = fixture_data()
    data["persons"][0]["place"] = "город Тестов"
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        load(bad)
    assert "место" in str(excinfo.value)


def test_dangling_parent_reference_rejected(tmp_path):
    """Ссылка на несуществующего родителя — понятная ошибка, не тихая потеря."""
    data = fixture_data()
    data["persons"][3]["father"] = "t99"
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        load(bad)
    assert "t99" in str(excinfo.value)


def test_fail_safe_no_dates_treated_as_living():
    """Нет ни года рождения, ни отметки о смерти → считаем живым."""
    ghost = Person(id="@GHOST@")
    assert ghost.is_living
    assert ghost.public_years == "ныне живущий"
    assert ghost.public_place == ""


def test_deceased_precision_preserved():
    """У умерших полные даты остаются в модели (фильтр касается только живых)."""
    people, _, _ = load()
    dead = people["t04"]
    assert not dead.is_living
    assert dead.public_years == dead.years == "1940 – 2010"


# --- Интеграционные: полная сборка ------------------------------------------


def test_build_on_fixture(tmp_path):
    """Сборка на фикстуре: HTML цел, точные даты живых не утекли."""
    code, log, html = build_in_tmp(tmp_path)
    assert code == 0, log
    assert html.count("<svg") >= 1
    assert 'id="page2"' in html
    assert "р. 1971" in html                 # год живого корня разрешён политикой
    assert "р. 2001" in html                 # год живого ребёнка-якоря тоже
    assert "Гипотеза" in html                # бейдж гипотезы рендерится
    assert "мать не найдена" in html         # заглушка для отсутствующей матери t02
    assert "Древо прямых предков" in html


def test_build_fails_cleanly_without_data(tmp_path):
    """Нет data/family.yaml → exit 1, понятное сообщение, без трейсбека."""
    code, log, _ = build_in_tmp(tmp_path, with_data=False)
    assert code == 1
    assert "Ошибка" in log
    assert "Traceback" not in log
