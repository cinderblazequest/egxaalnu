# Changelog

Все заметные изменения проекта документируются в этом файле.
Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версионирование — [SemVer](https://semver.org/lang/ru/).

## [Unreleased]

### Added — final-polish (май 2026)
* **i18n SOS / panic / dispatcher:** ключи `sos.text`, `nav.back/cancel`,
  `cat.{critical,urgent,minor}`, `panic.*`, `disp.*` для ru/en/uz/kk.
  `category_kb`, `dispatcher_question_kb`, `panic_intro_kb`, `triage_kb`,
  `back_to_panic_kb`, `run_breathing` теперь принимают параметр `lang`.
  Регрессионный тест `tests/test_i18n_completeness.py` фиксирует наличие
  всех новых ключей во всех четырёх языках.
* **Локализация PWA-лендинга:** `landing/index.uz.html`, `landing/index.kk.html`;
  переключатель языка во всех 4 файлах ведёт на 4 языка.
* **DevOps Dockerfile:** multi-stage build + non-root user `spas` (UID 10001) +
  `tini` как PID 1 + `HEALTHCHECK` на `/health`. Изображение чище и безопаснее.
* **DevOps fly.toml:** TCP/HTTP health-checks, отдельный TLS-сервис для
  webhook (`internal_port = 8443`), VM повышен до 512 MB.
* **DevOps graceful shutdown:** `bot/__main__.py` ставит обработчики
  SIGTERM/SIGINT через `loop.add_signal_handler`; polling/webhook/RSS-таска
  останавливаются по событию.
* **Webhook-режим:** `WEBHOOK_MODE=1` поднимает aiohttp-приложение с
  `aiogram.webhook.aiohttp_server.SimpleRequestHandler` на `/tg`,
  регистрирует webhook в Telegram (`secret_token`), даёт `/healthz`.
* **Backup script `tools/backup_db.py`:** atomic snapshot через
  `sqlite3.Connection.backup`, AES-256-GCM шифрование (32-байтный ключ),
  загрузка в любой S3-совместимый стор (Selectel / Yandex / MinIO / AWS) через
  `boto3`. Поддерживает `--dry-run`, `--no-encrypt`, имя ключа со штампом UTC.
* **AED Overpass импорт `tools/import_aed_overpass.py`:** запрашивает
  `emergency=defibrillator` у Overpass API, мерджит в
  `content/aed_locations.json` с де-дупом по округлённым координатам
  (3 знака ≈ 110 м).
* **Тесты (новые 88 кейсов):** API endpoints (health/scenarios/aed/dispatcher/
  panic/openapi/CORS), allow-list dashboard, детерминированность сертификата
  через subprocess с разным `PYTHONHASHSEED`, snapshot+encrypt+merge для tools/.
* **Документация:** `.env.example` переписан как полный референс всех 30+
  переменных (THROTTLE_*, LOG_FORMAT, SENTRY_DSN, API_*, MCHS_RSS_*,
  WEBHOOK_*, BACKUP_S3_*, BACKUP_ENCRYPTION_KEY).

### Fixed
* **Стабильный код сертификата:** `abs(hash(seed))` заменён на
  `hashlib.sha256(seed.encode()).digest()[:8]` — раньше `PYTHONHASHSEED`
  делал код невоспроизводимым между перезапусками бота.
* **dashboard.py SQL-инъекция:** имя таблицы валидируется по фиксированному
  allow-list `ALLOWED_TABLES`; идентификатор оборачивается в кавычки. Любая
  левая строка → `ValueError`.

### Added — block H/C7/C8/C2/A3 (январь 2026)
* **152-ФЗ согласие (H8):** на `/start` показывается экран согласия
  с кнопками «Согласен / Не согласен / Открыть политику», ответ хранится
  в `user_settings.consent_pdn_at` + версия `consent_pdn_version`.
  Append-only `consent_log` для аудита. Команды `/privacy` (текст
  политики) и `/forget_me` (удаление всех данных). Миграция m006.
  Модуль: `bot/handlers.py:_consent_*`.
* **Право на забвение (H3):** `/forget_me` — двухступенчатое подтверждение
  + cascade DELETE по 13 таблицам. Запись в `audit_log`.
* **Audit log (H1):** новая таблица `audit_log` (action, actor_id, target,
  details, ts). Логируются: consent_accept/decline, forget_me,
  admin_export, aed_moderation. Команда `/audit` для админа. Миграция m007.
* **Admin CSV export (H4):** `/admin_export {table}` шлёт CSV-документ
  по 15 разрешённым таблицам. Только для `ADMIN_ID`.
* **OpenAPI 3.0 (H7):** эндпоинт `GET /api/openapi.json` со спецификацией
  REST API. Тест в `tests/test_api_openapi.py`.
* **GigaChat Vision (C2):** новый модуль `bot/vision.py`. Хендлер фото:
  upload → triage → JSON-ответ {category, severity, scenario_id, advice}.
  Кнопка «Открыть сценарий». Rate-limit 5 фото/час/user. i18n строки
  `vision.*` для ru/en/uz/kk.
* **МЧС RSS push (C7):** новый модуль `bot/mchs_rss.py`. Команды
  `/subscribe_alerts {region}`, `/unsubscribe_alerts`, `/my_alerts`.
  Опрос RSS включается через `MCHS_RSS_ENABLED=1` (по умолчанию выкл).
  14 регионов + `all`. Дедупликация через `alerts_seen`. Маппинг
  категории новости → сценарий первой помощи. Миграция m008.
  Тесты в `tests/test_mchs_rss.py`.
* **Полный i18n + UZ/KZ (C8):** добавлены узбекский (`uz`) и казахский
  (`kk`) языки. Алиас `kz → kk`. Команда `/lang` теперь предлагает
  четыре варианта. ~50 ключей переведены. Тесты в `tests/test_i18n_full.py`.
* **TTS-скелет (A3):** новый модуль `bot/tts.py` с дисковым кешем
  под `audio/cache/`. Активируется при наличии `YANDEX_API_KEY` и
  правильных IAM ролей.
* **Бренд-гайд (E1):** `landing/logo.svg` (gradient red + белый плюс),
  `docs/brand_guide.md` (цвета, типографика, тон, шаблоны сообщений).
* **PWA-иконки (E6):** `landing/icons/icon-{192,512,maskable-512}.png`
  + `apple-touch-icon.png`. Скрипт `tools/generate_icons.py` (PIL).
* **Demo tour script (E7):** `docs/demo_tour_script.md` — 2-минутный
  сценарий записи демо для жюри.
* **152-ФЗ форма согласия (Bonus):** `docs/consent_form_template.md` —
  PDF-шаблон для родителей при пилоте в школе.
* **Coverage в CI (G1):** `pytest --cov` с порогом 70% и upload XML
  как артефакт. `.coveragerc` исключает Telegram-handlers/main.
* **README badges (G8):** CI, Python, Coverage, Ruff, License, 152-ФЗ.
* **Dependabot (G9):** `.github/dependabot.yml` для pip + GitHub Actions.
* **Tools:** `tools/scenarios_to_pdf.py` (печатный PDF 30 сценариев),
  `tools/finance_to_xlsx.py` (markdown → xlsx для жюри),
  `tools/generate_icons.py` (PWA-иконки).
* **31 новый тест** (storage consent/audit, mchs_rss, OpenAPI, i18n full,
  vision rate-limit). Всего: 101 тест, coverage 80%.

### Added — block C/D/E/G (ноябрь 2025)
* **Геймификация (C4):** XP, 8 уровней («Новичок» → «Легенда»), 10 ачивок,
  серия «дни подряд», команда `/profile`. Модуль `bot/gamification.py`.
* **Учительский режим (C5):** `/teacher` — завести класс, `/join CODE` —
  присоединиться, `/teacher_dashboard` — прогресс класса по XP. Таблицы
  `classes`, `class_members` (см. `bot/migrations.py` m003). Модуль
  `bot/teacher.py`.
* **SOS-режим (C3):** `/sos_contact` — добавить доверенный контакт,
  `/sos_share` — разовая отправка геолокации + текста, `/sos_clear` —
  удалить контакт. Таблица `sos_contacts`. Модуль `bot/sos.py`.
* **Семейный share (C6):** `/share_progress`, `/share_certificate` —
  готовые тексты для `t.me/share/url`. Модуль `bot/sharing.py`.
* **Доступность (C9):** `/accessibility` — переключение plain-text режима
  (без эмодзи и HTML), хранится в `user_settings`. Модуль
  `bot/accessibility.py`.
* **Голосовой ввод (C1):** распознавание `voice` через Yandex SpeechKit —
  опционально, gracefully degrade при отсутствии `YANDEX_STT_API_KEY`.
  Модуль `bot/stt.py`.
* **REST API (C10):** aiohttp-сервер на `API_PORT=8090` с CORS-разрешением.
  Эндпойнты: `/api/health`, `/api/scenarios`, `/api/scenarios/{id}`,
  `/api/aed`, `/api/dispatcher`, `/api/panic`. Модуль `bot/api.py`.
* **PWA (E6):** `landing/manifest.webmanifest` + `service-worker.js` +
  install-prompt в `landing/index.html`. Виджет `landing/widget.js` для
  встраивания в школьные сайты.
* **i18n (RU/EN):** минимальный словарь в `bot/i18n.py` для новых команд.
* **Дашборд (D1–D6):** когортный retention по неделям, NPS-хитмэп,
  поведенческая воронка `/start → завершение → сертификат`, A/B-варианты
  по эксперименту, лидерборд XP. См. `dashboard.py`.
* **Throttle (G4):** middleware `bot/middleware/throttle.py` — sliding
  window per-user, по умолчанию 5 событий/сек. Конфиг через `THROTTLE_RATE`,
  `THROTTLE_PER`.
* **JSON-логирование (G5):** `bot/log_setup.py` — переключение через
  `LOG_FORMAT=json|human`, опциональная интеграция Sentry (`SENTRY_DSN`).
* **Liveness-эндпойнт (G6):** `bot/health.py` на `HEALTH_PORT=8080` для
  Fly.io / Railway healthchecks. JSON-ответ со счётчиком пользователей,
  событий, размером БД.
* **Миграции (G7):** легковесный механизм без Alembic — `bot/migrations.py`,
  таблица `_migrations`, идемпотентные шаги `m001…m005`.
* **Pre-commit (G2):** `.pre-commit-config.yaml` — ruff-check + ruff-format
  + standard hooks (trailing-whitespace, end-of-file-fixer, json/yaml/toml
  валидация).
* **Покрытие тестами:** добавлены `tests/test_gamification.py`,
  `test_sos_module.py`, `test_accessibility.py`, `test_i18n.py`,
  `test_sharing.py`, `test_throttle.py` — 70 unit-тестов.
* **Презентация (E2):** `docs/jury_deck.md` переписан под Marp — рендерится
  в PDF/PPTX через `npx @marp-team/marp-cli`.
* **Финансовая модель (E3):** `docs/finance_model.md` — расходы по годам,
  источники грантов, P&L, чувствительность.
* **Дорожная карта (E4):** `docs/roadmap.md` — Mermaid Gantt 2026–2028 +
  ключевые ворота + риски.
* **Governance + 152-ФЗ (E5):** `docs/governance_152fz.md` — модель данных,
  согласия для несовершеннолетних, удаление, безопасность, план АНО.
* **Docker Compose (G):** `docker-compose.yml` для одной команды
  `docker compose up` — бот + healthcheck + опц. дашборд.

### Added
* Panic-режим (`/panic`): дыхательное упражнение 6 вдохов/мин,
  triage по симптомам, упражнение 5-4-3-2-1 grounding.
* Краудсорс АНД (`/add_aed`): пользователь шлёт геолокацию, описание
  и (опц.) фото — заявка попадает в очередь модерации.
* Команда модерации `/aed_admin` для администратора.
* Чек-лист «Что сказать диспетчеру 112» (`/dispatcher`): 5 вопросов,
  бот собирает готовое сообщение для оператора.
* Цифровой сертификат (`/certificate`): генерация PNG для
  пользователей, завершивших ≥3 сценариев. PIL/Pillow + QR-код.
* Раздельные `pre_test` и `post_test` в сценариях
  (с обратной совместимостью).
* Анимированный «успокаивающий» текстовый метроном 6 дыханий/мин для
  panic-режима.
* JSON-конфиги: `content/dispatcher_checklist.json`,
  `content/panic_protocol.json`.
* Юнит-тесты pytest (`tests/`): 50+ кейсов на storage, catalogue,
  aed, certificate, panic, dispatcher.
* GitHub Actions CI: ruff lint + format check + pytest на 3.11/3.12 +
  валидация JSON-контента.
* Apache 2.0 LICENSE и CC BY-NC-SA 4.0 LICENSE-CONTENT.
* CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md.
* Английская версия лендинга (`landing/en.html`).
* Генераторы PDF: одностраничная инфографика для жюри,
  10-страничная методичка (`tools/generate_*_pdf.py`).
* Генератор аудио-метронома `tools/generate_metronome.py` через
  ffmpeg (100/110/120 BPM + 6 BPM calm).
* Скрипт валидации контента `python -m tools.validate_content`.
* `Makefile`, `pyproject.toml` (ruff + pytest config),
  `requirements-dev.txt`.
* Документы: шаблоны писем поддержки, пресс-релиз, банк опроса для
  пилота, методичка, риски, методологические заметки, шаблоны для
  SMM (VK/TG), брифинг волонтёров, презентация для жюри.

### Changed
* `requirements.txt`: добавлены `Pillow`, `qrcode[pil]`
  (для сертификата).
* `bot/handlers.py`: подключены новые команды и кнопка panic
  в главном меню.
* `bot/storage.py`: новые таблицы `aed_submissions`, `certificates`,
  индексы и расширенные `metrics()`.
* `bot/catalogue.py`: поле `pre_test` опционально, fallback на
  `post_test`.
* `landing/index.html`: добавлены ссылки на EN-версию и методичку.

## [0.1.0] — 2026-05-04

### Added
* Базовый Telegram-бот на aiogram 3.x с 30 сценариями.
* Голосовой/текстовый метроном 110 BPM.
* SQLite-аналитика (users, events, feedback, test_results).
* Streamlit-дашборд для жюри.
* Лендинг (RU).
* Деплой-конфиги: Dockerfile, fly.toml, Procfile.
* Опциональная LLM-интеграция (GigaChat / YandexGPT).
* Документация: концепция, текст заявки, банк вопросов жюри.
