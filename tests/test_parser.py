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

from build_site import person_search_text, recorded_alternate_surnames
from parse_data import Person, direct_lines, format_date, load_family

REPO = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "minimal.yaml"


def load(path=FIXTURE):
    return load_family(path)


def fixture_data():
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def build_in_tmp(tmp_path, with_data=True, data=None):
    """Полная сборка в копии репозитория; возвращает (exit_code, stderr, html)."""
    dst = tmp_path / "repo"
    shutil.copytree(REPO, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    (dst / "data").mkdir(exist_ok=True)
    if data is not None:
        (dst / "data" / "family.yaml").write_text(
            yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
        )
    elif with_data:
        shutil.copy(FIXTURE, dst / "data" / "family.yaml")
    else:
        # В рабочей копии data/family.yaml может лежать локально — для
        # негативного сценария убираем и его.
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


def test_date_shape_and_hypothesis_status_are_independent():
    """Квалификатор даты не создаёт гипотезу о личности или родственной связи."""
    people, _, _ = load()
    assert people["t04"].birth_precision == "year"
    assert not people["t04"].is_reconstructed
    assert people["t06"].is_reconstructed          # «ок. 1910»
    assert people["t07"].is_reconstructed          # дат нет вовсе
    assert people["t06"].is_hypothesis             # явный status: hyp
    approximate = Person(id="ok-date", birt="ок. 1910", deceased=True, status="ok")
    assert approximate.is_reconstructed
    assert not approximate.is_hypothesis


def test_glued_month_and_year_are_separated_only_for_display():
    """Склейка разделяется пробелом без выбора между вариантами месяца."""
    assert format_date("ма1919") == "ма 1919"
    assert format_date("мар. 1919") == "мар. 1919"
    assert format_date("ок. 1818") == "ок. 1818"


def test_search_uses_recorded_and_gendered_surname_forms():
    """Двойная фамилия ищется целиком и по компонентам, без гибридных форм."""
    person = Person(id="names", givn="Григорий", surn="Захаров/Алексеев", sex="M")
    search = person_search_text(person)
    assert "Захаров/Алексеев" in search
    assert "Захарова" in search and "Алексеева" in search
    assert "Захаров/Алексеева" not in search


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
    assert html.count('<svg class="pedigree"') == 2
    assert 'id="page2"' in html
    assert 'id="page3"' in html
    assert "р. 1971" in html                 # год живого корня разрешён политикой
    assert "р. 2001" in html                 # год живого ребёнка-якоря тоже
    assert "Гипотеза" in html                # бейдж гипотезы рендерится
    assert "мать не найдена" in html         # заглушка для отсутствующей матери t02
    assert "Древо прямых предков" in html


def test_tree_controls_and_public_search_are_built_for_both_trees(tmp_path):
    """У каждого древа есть поиск, область поиска и четыре независимых действия."""
    code, log, html = build_in_tmp(tmp_path)
    assert code == 0, log
    assert html.count('data-search-tree=') == 2
    assert 'data-controls-tree="matyukhiny"' in html
    assert 'data-controls-tree="skiba"' in html
    for action in ("zoom-out", "zoom-in", "fit", "reset"):
        assert html.count(f'data-tree-action="{action}"') == 2
    assert 'data-tree="matyukhiny"' in html and 'data-tree="skiba"' in html
    assert 'id="pedigree-t01"' in html and 'id="pedigree-skiba-t01"' in html
    assert 'data-years="р. 1971"' in html
    assert "touch-action:none" in html
    assert "startPinch" in html


def test_search_excludes_people_outside_public_trees(tmp_path):
    """Персона вне обоих SVG не попадает даже в скрытый поисковый индекс."""
    data = fixture_data()
    data["persons"].append({
        "id": "t99", "surname": "Непубличный", "name": "Человек",
        "birth": "1900", "deceased": True, "status": "ok",
    })
    code, log, html = build_in_tmp(tmp_path, data=data)
    assert code == 0, log
    assert "Непубличный" not in html


def test_search_does_not_publish_private_notes(tmp_path):
    """В data-search и data-years нет note и иных закрытых полей живого человека."""
    data = fixture_data()
    data["persons"][0]["note"] = "Закрытая служебная пометка"
    code, log, html = build_in_tmp(tmp_path, data=data)
    assert code == 0, log
    assert "Закрытая служебная пометка" not in html


def test_recorded_alternate_surnames_use_only_written_forms():
    """Скобки и косая черта — уже записанные фамилии, не девичья фамилия из отчества."""
    maidenish = Person(id="alt1", givn="Зинаида", surn="Захарченкова(Захарченко?)", sex="F")
    assert recorded_alternate_surnames(maidenish) == ["Захарченко?"]
    compound = Person(id="alt2", givn="Григорий", surn="Захаров/Алексеев", sex="M")
    assert recorded_alternate_surnames(compound) == ["Захаров", "Алексеев"]
    several = Person(id="alt3", givn="Марта", surn="Чернова (Перова, Кузнецова)", sex="F")
    assert recorded_alternate_surnames(several) == ["Перова", "Кузнецова"]
    patronymic = Person(id="alt4", givn="Спиридон Ермилович(Ермолаевич)", surn="Захаров", sex="M")
    assert recorded_alternate_surnames(patronymic) == []


def test_home_cover_keeps_hero_and_drops_branch_blurbs(tmp_path):
    """Главная — обложка: первый экран и текст об основателе, без описания ветвей."""
    code, log, html = build_in_tmp(tmp_path)
    assert code == 0, log
    page = html.split('id="page1"', 1)[1].split('id="page-matyukhiny"', 1)[0]
    assert "Структура поколений" in page
    assert "Реконструкция<br>в пространстве и времени" in page
    assert "Исследовать архив" in page
    assert "Исследование семейной истории начал Эдуард Алексеевич Скиба в начале 2000-х годов." in page
    assert "Его работу продолжили дочь и внучка." in page
    assert "Мокрое, Дмитров и Долгопрудный." not in page
    assert "Донбасс, Валдай и Татария." not in page
    assert "Хроника" not in page
    assert 'type="search"' not in page


def test_family_parts_keep_direct_links_and_demote_chronicle(tmp_path):
    """Пять частей раздела — отдельные страницы; хроника остаётся, но не в основной навигации."""
    code, log, html = build_in_tmp(tmp_path)
    assert code == 0, log
    for key in ("matyukhiny", "skiba"):
        assert f'id="{key}"' in html
        for suffix in ("branches", "tree", "people", "sources", "places"):
            assert f'id="{key}-{suffix}"' in html
            assert f'href="#{key}-{suffix}"' in html
        assert f'id="{key}-timeline"' in html
        assert f'href="#{key}-timeline"' not in html
        assert f'id="{key}-gallery"' not in html
    assert "Связь семьи из ревизской сказки 1834 года" in html
    assert "Две семьи Алексеевых не являются родственными." in html
    assert "Архивные направления" not in html
    assert "Родина Надежды Астафьевой" not in html
    assert "Здесь родились Григорий Скиба" not in html
    assert "В записи прямой линии указаны" not in html
    assert 'id="page2"' in html and 'id="page3"' in html


def test_person_card_id_and_collateral_sibling(tmp_path):
    """Карточка адресуется id персоны. Брат вне древа публикуется, человек без связей — нет."""
    data = fixture_data()
    data["persons"].append({
        "id": "t09",
        "surname": "Тестов",
        "name": "Павел Иванович",
        "birth": "1942",
        "death": "2001",
        "sex": "M",
        "deceased": True,
        "status": "ok",
        "father": "t04",
        "mother": "t05",
        "place": "город Примерск",
    })
    data["persons"].append({
        "id": "t99",
        "surname": "Непубличный",
        "name": "Человек",
        "birth": "1900",
        "deceased": True,
        "status": "ok",
    })
    code, log, html = build_in_tmp(tmp_path, data=data)
    assert code == 0, log
    assert 'id="person-t01"' in html
    assert "Показать в древе" in html
    assert 'id="person-t09"' in html
    assert 'href="#person-t09"' in html
    assert "город Примерск" in html
    assert 'id="pedigree-t09"' not in html
    assert 'id="pedigree-skiba-t09"' not in html
    assert "Непубличный" not in html
    card = html.split('id="person-t01"', 1)[1].split('id="person-', 1)[0]
    assert "1971" in card
    assert "Место рождения" not in card
    assert "Смерть" not in card
    assert "Закрытая" not in card
    assert "Показать в древе" in card
    assert 'href="#person-t04"' in card
    assert 'data-card-id="pedigree-t01"' in card
    bare = html.split('id="person-t07"', 1)[1].split('id="person-', 1)[0]
    assert "даты неизвестны" not in bare
    assert "<dt></dt>" not in html
    sibling = html.split('id="person-t09"', 1)[1].split('id="person-', 1)[0]
    assert "Показать в древе" not in sibling
    assert "город Примерск" in sibling


def test_public_search_index_links_cards_and_keeps_private_fields_out(tmp_path):
    """Глобальный индекс: публичные люди, альтернативная фамилия, без мест и заметок."""
    data = fixture_data()
    data["persons"].append({
        "id": "t09",
        "surname": "Захаров/Алексеев",
        "name": "Григорий",
        "birth": "1912",
        "death": "1988",
        "sex": "M",
        "deceased": True,
        "status": "ok",
        "father": "t04",
        "mother": "t05",
        "place": "город Примерск",
        "note": "Закрытая служебная пометка",
    })
    code, log, html = build_in_tmp(tmp_path, data=data)
    assert code == 0, log
    page = html.split('id="page1"', 1)[1].split('id="page-matyukhiny"', 1)[0]
    assert 'type="search"' not in page
    assert 'id="archive-search"' in html
    assert 'data-person-search' in html
    blob = html.split('id="person-index">', 1)[1].split("</script>", 1)[0]
    import json
    records = json.loads(blob)
    by_id = {item["id"]: item for item in records}
    assert "t99" not in by_id
    assert "t09" in by_id
    assert "t01" in by_id
    allowed = {"id", "name", "search", "years", "sections", "trees"}
    assert set(by_id["t01"]) == allowed
    assert by_id["t01"]["years"] == "р. 1971"
    assert "Закрытая служебная пометка" not in html
    assert "Примерск" not in blob
    assert "Закрытая служебная пометка" not in blob
    assert "Захаров" in by_id["t09"]["search"]
    assert "Алексеев" in by_id["t09"]["search"]
    assert by_id["t09"]["trees"] == []
    assert any(tree["card"] == "pedigree-t01" for tree in by_id["t01"]["trees"])
    card = html.split('id="person-t09"', 1)[1].split('id="person-', 1)[0]
    assert 'href="#person-t01"' in card
    assert "Показать в древе" not in card
    assert "Место рождения" in card
    assert "город Примерск" in card
    css = (REPO / "assets" / "site.css").read_text(encoding="utf-8")
    face = css.split(".pedigree .fr{")[1].split("}")[0]
    assert "var(" not in face
    assert "#F8F9FB" in face
    assert "forced-color-adjust:none" in css
    assert "color-scheme:light" in css
    assert "applyTreeScale(view, 1)" in html
    assert 'stroke="#22252B"' not in html
    assert 'fill="#22252B"' in html


def test_build_fails_cleanly_without_data(tmp_path):
    """Нет data/family.yaml → exit 1, понятное сообщение, без трейсбека."""
    code, log, _ = build_in_tmp(tmp_path, with_data=False)
    assert code == 1
    assert "Ошибка" in log
    assert "Traceback" not in log
