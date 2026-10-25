# Якорь контекста проекта

Короткий стартовый контекст для нового чата Cursor.  
Подробности: [README](../README.md), [docs/architecture.md](../docs/architecture.md). ADR ведутся локально и в публичный репозиторий не входят.

## Готово на `master`

- **Live:** https://smaturus.github.io/family-history/
- **Репозиторий:** Smaturus/family-history
- **README** — короткий обзор; глубина — в `docs/architecture.md`
- **Hero:** фон = `assets/Image 1.png`; раскладка = `assets/Image 2.png`
- **Pages allowlist:** `index.html`, `.nojekyll`, `assets/hero-bg*.{avif,webp,jpg}`
- **Сборка:** локально `python3 scripts/build_site.py` (GEDCOM не в CI, файл `data/skiba.ged` не в Git)

## Как использовать в новом чате

Скопируйте блок ниже в первое сообщение и допишите задачу:

```text
Контекст: @assets/project-anchor.md
(или вставь содержимое этого файла)

Новая задача:
<опишите, что нужно сделать>
```

Либо в Cursor: `@` → файл `assets/project-anchor.md`.
