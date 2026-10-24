"""Тесты доступности генерируемого сайта.

Проверяют текстовые альтернативы, фокусируемость прокручиваемого древа
и aria-состояния навигации на сборке над синтетической фикстурой.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_parser import build_in_tmp


def test_pedigree_svg_has_text_alternatives(tmp_path):
    """SVG-древо: role="img" + <title>/<desc> для скринридеров."""
    code, log, html = build_in_tmp(tmp_path)
    assert code == 0, log
    assert 'class="pedigree"' in html
    assert '<svg class="pedigree"' in html and 'role="img"' in html
    assert 'aria-labelledby="pedigree-title pedigree-desc"' in html
    assert '<title id="pedigree-title">Древо прямых предков</title>' in html
    assert '<desc id="pedigree-desc">' in html


def test_treewrap_scrollable_region_focusable(tmp_path):
    """Прокручиваемый контейнер древа доступен с клавиатуры."""
    code, log, html = build_in_tmp(tmp_path)
    assert code == 0, log
    assert 'class="treewrap" tabindex="0" role="region" aria-label="Древо прямых предков"' in html


def test_nav_active_state_announced(tmp_path):
    """Активный пункт навигации помечен aria-current, декорации скрыты."""
    code, log, html = build_in_tmp(tmp_path)
    assert code == 0, log
    assert 'aria-current="true"' in html
    assert 'hero-art" aria-hidden="true"' in html
    assert 'hero-years" aria-hidden="true"' in html
    assert 'lang="ru"' in html


def test_focus_visible_style_present():
    """Глобальный focus-ring объявлен в CSS, smooth-scroll уважает reduced-motion."""
    css = Path(__file__).resolve().parents[1] / "assets" / "site.css"
    text = css.read_text(encoding="utf-8")
    assert ":focus-visible" in text
    # smooth-scroll включается только при разрешённой анимации
    before_media = text.split("@media (prefers-reduced-motion: no-preference)")[0]
    assert "scroll-behavior:smooth" not in before_media
    assert "html{scroll-behavior:smooth}" in text
