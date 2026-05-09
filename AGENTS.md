# AGENTS.md — контекст для AI-ассистентов (Devin, Cursor, Claude Code)

> Этот файл — короткая «карта» проекта для AI-агентов. Он читается
> автоматически и сильно ускоряет первый запуск.
>
> Полный план работ — `ROADMAP.md` (часть A/B/C/D).
> Полные рецепты разработки — `ROADMAP.md` часть E (E0–E15).
> Пошаговая инструкция деплоя — `INSTRUCTIONS_MAX_AND_TELEGRAM.md`.

## Что это за проект

**СПАС** — двухплатформенный AI-помощник по первой помощи для
подростков и учителей. Один и тот же контент, разные транспорты:

* **Telegram-бот** на `aiogram 3.13` (polling + опциональный webhook).
* **Max-бот** (мессенджер VK Group) на собственном тонком клиенте к
  `platform-api.max.ru`.

Контент общий: 30 сценариев (`content/scenarios.json`), паника-протокол,
чек-лист 112, точки АНД, ачивки. Изменив JSON — обновляешь оба бота.

## Технологический стек

* **Python 3.11+** (CI matrix: 3.11 + 3.12).
* **Async** I/O везде: `aiogram`, `aiohttp`, `aiosqlite`.
* **SQLite** + miграции в `bot/migrations.py` (`m001..m011+`).
* **Pydantic** — валидация JSON-контента.
* **REST API** на `aiohttp` (`bot/api.py`).
* **Streamlit** — дашборд (`dashboard.py`).
* **Тесты:** `pytest`, `pytest-asyncio`, coverage `pytest-cov`.
* **Линтер/форматтер:** `ruff` (один тул для всего).
* **Pre-commit:** ruff + format + yaml/toml-check + custom content-validator.
* **CI:** GitHub Actions matrix 3.11/3.12.
* **Деплой:** Docker (multi-stage, non-root, tini, healthcheck) → Fly.io 512 МБ VM.

## Структура

См. `ROADMAP.md` E0 — полная карта файлов.

Самое важное:
- `bot/handlers.py` — хендлеры Telegram-бота.
- `bot/max/handlers.py` — хендлеры Max-бота (паритет).
- `bot/i18n.py` — единый словарь переводов (ru/en/uz/kk).
- `content/*.json` — единый источник правды контента.

## Команды разработчика

```bash
# Активация окружения
source .venv/bin/activate

# Линт + формат + тесты (полный конвейер)
ruff check . && ruff format --check . && \
pre-commit run --all-files && \
pytest -q --cov=bot --cov=tools --cov-fail-under=70

# Авто-фикс
ruff check --fix . && ruff format .

# Запуск
python -m bot          # Telegram
python -m bot.max      # Max
honcho start           # оба через Procfile

# Тесты только Max
pytest -q tests/test_max_client.py

# Покрытие HTML
pytest --cov-report=html && xdg-open htmlcov/index.html
```

## Конвенции

* **Type hints** везде, включая возвращаемое значение.
* **Async** — для всего I/O.
* **Логи** через `logging.getLogger("spas.<module>")`. Уровни:
  `error / warning / info / debug`.
* **Тексты** для пользователя — только через `bot/i18n.py:t(key, lang)`.
* **Имена коммитов:** `feat|fix|docs|test|chore|refactor(scope): ...`.
* **Имена веток:** `devin/<unix-ts>-<short-name>`.
* **Минимум комментариев** — переименование переменной лучше комментария.
* **Без `print()`** в проде, только в `tools/*` для CLI.
* **Без `assert`** в рантайме — только в тестах.

## Безопасность

* Никогда не коммить `.env`, `data/spas.db`, `audio/*.mp3` (если личное).
* Все секреты — через переменные окружения, документированы в `.env.example`.
* В дашборде имена таблиц — через allow-list (`ALLOWED_TABLES`),
  никаких raw f-string SQL.
* Сертификаты — через `hashlib.sha256`, не `hash()` (PYTHONHASHSEED).
* Бэкапы — AES-256-GCM перед отправкой в S3.

## Юридическое

* 152-ФЗ: согласие на `/start`, `/privacy`, `/forget_me` с cascade DELETE.
* Audit log пишется в таблицу `audit_log`.
* Дисклеймер «не заменяет врача» — везде, где медицинский контент.

## Чего НЕ делать

* ❌ Push в `main` напрямую (только PR).
* ❌ `git commit --amend` (только новые коммиты).
* ❌ `git reset --hard` без явной просьбы пользователя.
* ❌ Менять тесты, чтобы они «проходили» (только если попросили).
* ❌ Использовать `getattr/setattr/Any` чтобы обойти типы.
* ❌ Захардкоживать данные пользователей или секреты в код.
* ❌ Удалять логи / аудит / согласия без явной миграции.
* ❌ Менять JSON-формат `content/*.json` без обновления pydantic-моделей
  и тестов валидации.

## Куда смотреть, когда что-то ломается

| Симптом | Куда смотреть |
|---|---|
| `ImportError` после правки i18n | `bot/i18n.py` — пропустил кавычку или скобку |
| Падает миграция | `bot/migrations.py` — порядок в `MIGRATIONS` |
| Coverage упало | `pytest --cov-report=term-missing` — найди `0%` строки |
| Бот не отвечает | Логи: `fly logs` или локально stdout |
| Max API 401 | Невалидный `MAX_BOT_TOKEN` |
| Telegram conflict | Запущено два инстанса с одним токеном |

Полный траблшутинг — `INSTRUCTIONS_MAX_AND_TELEGRAM.md` раздел 12.

## Промпты для агентов

* «Прочитай ROADMAP.md и сделай раздел A1.»
* «Прочитай ROADMAP.md E2 и добавь сценарий "<id>".»
* «Прочитай ROADMAP.md E3 и добавь язык "<code>".»
* «Прочитай ROADMAP.md E4 и добавь команду /<name> в TG и Max паритетно.»

## Definition of Done для любой задачи

1. ✅ `ruff check .` — clean.
2. ✅ `ruff format --check .` — clean.
3. ✅ `pre-commit run --all-files` — все хуки passed.
4. ✅ `pytest -q --cov=bot --cov=tools --cov-fail-under=70` — зелёный.
5. ✅ Новый/изменённый код покрыт тестами.
6. ✅ Изменения в `bot/handlers.py` зеркалены в `bot/max/handlers.py`
   (если это пользовательская команда/callback).
7. ✅ Новые ключи `i18n` есть во всех 4 языках (или добавлен fallback).
8. ✅ Описание в `CHANGELOG.md` обновлено.
9. ✅ PR-описание заполнено по шаблону репо.
10. ✅ CI зелёный (или объяснено, почему не запускается).
