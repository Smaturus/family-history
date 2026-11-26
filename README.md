# Семейный архив

Статический сайт семейной истории: единый локальный YAML-источник, редактируемые тексты и генератор HTML с двумя SVG-древами.

Главная страница ведёт в разделы «Матюхины» и «Скиба». У каждого раздела собственное представление предков, родовые ветви, документы, география и хроника. Супруг и общие потомки остаются на обоих древах, но предки супруга не дублируются. Для прямого доступа используются ссылки `#matyukhiny`, `#skiba`, `#matyukhiny-tree` и `#skiba-tree`.

Фотографии задаются в `gallery.photos` каждого раздела. Пустая галерея не создаёт публичных блоков и пунктов навигации.

## Локальная работа

```powershell
python -m pip install -r requirements.txt
python scripts/build_site.py
python -m http.server 8000
```

После запуска сервера сайт доступен по адресу `http://localhost:8000`.

Проверки:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

## Файлы

- `data/family.yaml` — генеалогические данные; каталог `data/` игнорируется Git и не публикуется.
- `content/content.yaml` — публичные тексты и структура разделов.
- `scripts/build_site.py` — сборка `index.html` и проверка приватности.
- `scripts/parse_data.py` — загрузка и валидация данных.
- `assets/site.css` — стили, встраиваемые в HTML при сборке.
- `tests/` — тесты и синтетическая фикстура для CI.
- `docs/architecture.md` — архитектура и правила публикации.

Файл `.nojekyll` отключает обработку Jekyll на GitHub Pages.

Для ныне живущих публикуются только имя и год рождения. Реальные данные не попадают в Git или Actions: автоматическая проверка сборки использует `tests/fixtures/minimal.yaml`.

Подробности — в [docs/architecture.md](docs/architecture.md).
