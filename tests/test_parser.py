"""Тесты парсера GEDCOM, inject-блока 1834 года и фильтра приватности.

Все данные — вымышленные (tests/fixtures/minimal.ged); реальные ПДн в тестах
запрещены политикой проекта (см. docs/architecture.md).
"""

import shutil
import subprocess
import sys
from pathlib import Path

from parse_gedcom import Person, direct_lines, parse_gedcom

REPO = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "minimal.ged"


def parse(path=FIXTURE):
    return parse_gedcom(path)


def build_in_tmp(tmp_path, with_gedcom=True):
    """Полная сборка в копии репозитория; возвращает (exit_code, stderr, html)."""
    dst = tmp_path / "repo"
    shutil.copytree(REPO, dst, ignore=shutil.ignore_patterns(".git"))
    (dst / "data").mkdir(exist_ok=True)
    if with_gedcom:
        shutil.copy(FIXTURE, dst / "data" / "skiba.ged")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(dst / "scripts" / "build_site.py")],
        capture_output=True, text=True, encoding="utf-8", cwd=dst, timeout=300,
    )
    html = ""
    if proc.returncode == 0:
        html = (dst / "index.html").read_text(encoding="utf-8")
    return proc.returncode, proc.stderr + proc.stdout, html


# --- Парсер -----------------------------------------------------------------


def test_fixture_parses():
    """Тест 1: фикстура читается, все записи на месте."""
    people, families, meta = parse()
    assert "@I1@" in people and "@I2@" in people and "@I3@" in people
    assert {"@F0@", "@F1@", "@F2@", "@F3@", "@F59@"} <= set(families)
    assert people["@I1@"].surname == "Testin"
    assert meta.get("date")


def test_inject_1834():
    """Тест 2: inject-блок привязывает @I155@ к архивным родителям Мокрого."""
    people, families, _ = parse()
    fedot = people["@I155@"]
    assert fedot.famc == "@F_MOKROE_26_CHILD@"
    assert fedot.givn == "Федот"
    assert fedot.surn == ""  # фамилия в ревизии 1834 г. не записана
    assert fedot.deceased
    # Федот удалён из гипотетической семьи @F59@
    assert "@I155@" not in families["@F59@"].chil
    # Архивная цепочка достраивается вглубь: Григорий → Илья → Матвей
    assert "@I_MOKROE_GRIGORY@" in people and "@I_MOKROE_ILYA@" in people
    assert families["@F_MOKROE_26_CHILD@"].husb == "@I_MOKROE_GRIGORY@"
    assert families["@F_MOKROE_26_PARENT@"].husb == "@I_MOKROE_ILYA@"
    line = [p.id for p in direct_lines("@I1@", people, families)["father"]]
    assert line[:6] == ["@I1@", "@I107@", "@I155@",
                        "@I_MOKROE_GRIGORY@", "@I_MOKROE_ILYA@", "@I_MOKROE_MATVEY@"]


def test_inject_skipped_without_anchor(tmp_path):
    """Замена GEDCOM без якоря @I155@: сборка не падает, архивные персоны
    создаются, но остаются вне прямой линии (задокументированный риск)."""
    text = FIXTURE.read_text(encoding="utf-8")
    stripped = "\n".join(
        line for line in text.splitlines()
        if "@I155@" not in line and not line.startswith("0 @I155@ INDI")
    )
    broken = tmp_path / "no_anchor.ged"
    broken.write_text(stripped, encoding="utf-8")
    people, families, _ = parse(broken)
    # Персоны Мокрого создаются безусловно…
    assert "@I_MOKROE_GRIGORY@" in people
    # …но Федота в базе нет, и прямая линия обрывается на @I107@
    assert "@I155@" not in people
    line = [p.id for p in direct_lines("@I1@", people, families)["father"]]
    assert line == ["@I1@", "@I107@"]


# --- Приватность ------------------------------------------------------------


def test_living_exact_date_filtered():
    """Тест 3: у живого с полной датой публикуются только имя и год рождения."""
    people, _, _ = parse()
    living = people["@I6@"]  # BIRT 17 APR 1975, PLAC Тестовый город
    assert living.is_living
    assert living.public_years == "р. 1975"
    assert "17" not in living.public_years.split("р. ")[1]
    assert living.public_place == ""  # место рождения скрыто


def test_living_year_only_stays_public():
    """Год рождения живого разрешён политикой публикации."""
    people, _, _ = parse()
    assert people["@I1@"].public_years == "р. 1971"
    assert people["@I3@"].public_years == "р. 2001"


def test_fail_safe_no_dates_treated_as_living():
    """Нет ни года рождения, ни отметки о смерти → считаем живым."""
    ghost = Person(id="@GHOST@")
    assert ghost.is_living
    assert ghost.public_years == "ныне живущий"
    assert ghost.public_place == ""


def test_deceased_precision_preserved():
    """У умерших полные даты остаются в модели (фильтр касается только живых)."""
    people, _, _ = parse()
    dead = people["@I4@"]  # BIRT 1940, DEAT 2010
    assert not dead.is_living
    assert dead.public_years == dead.years


# --- Интеграционные: полная сборка ------------------------------------------


def test_build_on_fixture(tmp_path):
    """Сборка на фикстуре: HTML цел, точные даты живых не утекли."""
    code, log, html = build_in_tmp(tmp_path)
    assert code == 0, log
    assert html.count("<svg") >= 1
    assert 'id="page2"' in html
    living = parse()[0]["@I6@"]
    assert living.birt not in html           # '17 APR 1975'
    assert "17 апреля 1975" not in html      # форматированный вариант
    assert "Тестовый город" not in html      # место живого скрыто
    assert "р. 1975" not in html             # @I6@ вне прямых линий и не рендерится вовсе
    assert "р. 1971" in html                 # год живого корня разрешён политикой


def test_build_fails_cleanly_without_gedcom(tmp_path):
    """Нет data/skiba.ged → exit 1, понятное сообщение, без трейсбека."""
    code, log, _ = build_in_tmp(tmp_path, with_gedcom=False)
    assert code == 1
    assert "Ошибка" in log
    assert "Traceback" not in log
