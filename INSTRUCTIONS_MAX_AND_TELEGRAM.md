# СПАС — полная инструкция: запуск в Telegram и Max (мессенджер VK)

> Этот документ ведёт от «у меня просто исходники» до «бот работает в обоих
> мессенджерах в проде». Все команды можно копировать построчно.
> Если что-то не получается — проверь раздел «Траблшутинг» в конце.

---

## 1. Что получится в итоге

Один и тот же код будет обслуживать:

* **Telegram-бот** — основной канал: 30 сценариев первой помощи, голосовой
  метроном СЛР, паника-протокол, чек-лист 112, карта АНД, GigaChat Vision,
  МЧС RSS-алерты, гамификация, /forget_me (152-ФЗ).
* **Max-бот** (мессенджер VK) — те же сценарии и протоколы через адаптер
  `bot/max/`. Min-функционал: /start, /sos, /panic, /dispatcher, /aed,
  /scenarios `<id>`, /help, inline-меню. На одном Python-процессе можно
  поднять оба бота параллельно (отдельные `MAX_BOT_TOKEN` и `BOT_TOKEN`).

Архитектурно это **один проект, два процесса**:

```
spas-ai/
├── bot/                     ← общий код: Catalogue, panic, dispatcher, content
│   ├── __main__.py          ← Telegram-бот (aiogram, polling/webhook)
│   └── max/
│       ├── __main__.py      ← Max-бот (long-polling)
│       ├── client.py        ← async-клиент Max API
│       └── handlers.py      ← роутинг команд и callback'ов
├── content/                 ← 30 сценариев + АНД + 112-чеклист + паника (одни на оба)
├── tools/                   ← backup_db.py, import_aed_overpass.py
└── ...
```

---

## 2. Системные требования

* **Python 3.12** (поддерживается также 3.11, проверено в CI).
* git, openssl, любой POSIX-шелл (Linux/macOS) или WSL/Git Bash на Windows.
* Доступ в интернет к `api.telegram.org` и `platform-api.max.ru`.
* Опционально: Docker 24+, Fly.io аккаунт, S3-совместимое хранилище (Selectel,
  Yandex Object Storage, MinIO, AWS S3).

---

## 3. Получение токенов

### 3.1 Telegram

1. Открой [@BotFather](https://t.me/BotFather) в Telegram.
2. `/newbot` → имя → `username` (должен заканчиваться на `_bot`).
3. Сохрани **HTTP API token** вида `1234567890:AAAA…`.
4. (Рекомендуется) `/mybots` → твой бот → **Bot Settings → Group Privacy → Disable**,
   чтобы бот видел сообщения в группах.

### 3.2 Max (VK Group)

1. Установи приложение **Max** ([max.ru](https://max.ru), iOS / Android / Web).
2. Найди и открой [@MasterBot](https://max.ru/MasterBot).
3. `/create` → имя → описание → @username.
4. MasterBot пришлёт **`access_token`** (длинная Base64-строка, выглядит как
   `qGdQK4_8LXOmO…`). Сохрани — он нужен для `MAX_BOT_TOKEN`.
5. (Опционально) В настройках бота включи команды `/start /sos /panic
   /dispatcher /aed /scenarios /help`.

> Документация Max: <https://dev.max.ru/>, OpenAPI:
> <https://maxmessengerapi.ru/max-bot-api-openapi-fixed.json>.

### 3.3 Опциональные ключи (для расширенных фич)

| Зачем | Где взять | Имя в `.env` |
|---|---|---|
| GigaChat Vision (анализ фото) | <https://developers.sber.ru/portal/products/gigachat> | `GIGACHAT_AUTH` |
| Sentry (мониторинг крашей) | <https://sentry.io/> | `SENTRY_DSN` |
| S3-бэкапы Selectel | <https://my.selectel.ru/storage> | `BACKUP_S3_*` |

---

## 4. Установка локально (за 5 минут)

```bash
# 1. Распаковать архив (если получили tarball) или склонировать репо
tar -xzf spas-ai-final-polish.tar.gz
cd spas-ai

# 2. Виртуальное окружение
python3.12 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip wheel

# 3. Зависимости (включая cryptography/boto3 для бэкап-скрипта)
pip install -r requirements-dev.txt

# 4. Pre-commit-хуки (ruff/format/yaml)
pre-commit install

# 5. Конфиг
cp .env.example .env
# открой .env и впиши BOT_TOKEN и MAX_BOT_TOKEN
```

Проверка:

```bash
ruff check .                          # должен быть «All checks passed!»
ruff format --check .
pytest -q --cov=bot --cov=tools --cov-fail-under=70
# 210 passed, ≥ 70% coverage
```

---

## 5. Запуск ботов локально

### 5.1 Только Telegram

```bash
source .venv/bin/activate
python -m bot
# Логи: «СПАС-бот запущен: @your_bot_username»
```

В Telegram открой свой `@your_bot_username` и нажми **Start**.

### 5.2 Только Max

```bash
source .venv/bin/activate
python -m bot.max
# Логи: «Max-бот запущен: <name> (id=<user_id>)»
```

В Max открой бота по `@username` или ссылке и нажми **Start**. Жми
кнопки или вводи /start, /sos, /panic, /dispatcher, /aed, /help.

### 5.3 Оба сразу

В двух разных терминалах (или через `tmux`/`screen`) запусти оба:

```bash
# Терминал 1
python -m bot
# Терминал 2
python -m bot.max
```

Для прода удобнее `Procfile` (используется Railway, Heroku-совместимыми
платформами и `honcho`):

```Procfile
web: python -m bot
max: python -m bot.max
```

```bash
pip install honcho
honcho start
```

---

## 6. Деплой в продакшен

Выбери один из вариантов. Если не уверен — Fly.io.

### 6.1 Fly.io (рекомендую, бесплатно для одной 256 МБ-машины)

```bash
# 1. Установи flyctl (one-liner от Fly): https://fly.io/docs/hands-on/install-flyctl/
curl -L https://fly.io/install.sh | sh

# 2. Авторизуйся
fly auth login

# 3. Создай приложение (используется существующий fly.toml — там 512 МБ + http checks)
fly launch --no-deploy --name spas-ai

# 4. Заведи volume для SQLite (один раз)
fly volumes create spas_data --region ams --size 1

# 5. Сохрани секреты (НЕ кладутся в git)
fly secrets set BOT_TOKEN=12345:ABC...
fly secrets set MAX_BOT_TOKEN=qGdQK4_8LXO...
fly secrets set GIGACHAT_AUTH=...                        # опционально
fly secrets set SENTRY_DSN=...                            # опционально
fly secrets set BACKUP_ENCRYPTION_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
fly secrets set BACKUP_S3_ENDPOINT=https://s3.ru-1.storage.selcloud.ru \
                BACKUP_S3_BUCKET=spas-backups \
                BACKUP_S3_ACCESS_KEY=... \
                BACKUP_S3_SECRET_KEY=...

# 6. Деплой
fly deploy
```

После `fly deploy` бот запустится на `Procfile`-процессе `web: python -m bot`.
Чтобы поднять Max-бота отдельно, склонируй приложение или используй второй
процесс:

```bash
fly machine run \
    --app spas-ai \
    --region ams \
    --image registry.fly.io/spas-ai:deployment-... \
    --env "MAX_BOT_TOKEN=qGdQ..." \
    -- python -m bot.max
```

Проверка: `fly logs --app spas-ai`, `fly status`.

### 6.2 Railway / Render / Koyeb

Любая Heroku-совместимая платформа. Подключи репозиторий, добавь переменные
окружения (см. раздел 3), и платформа сама стартует `web` и `max`-процессы из
`Procfile`.

### 6.3 VPS (Selectel / TimeWeb / любая) — Docker

```bash
# На VPS:
git clone https://github.com/cinderblazequest/egxaalnu.git spas-ai
cd spas-ai
cp .env.example .env
# отредактируй .env
docker compose up --build -d
docker compose logs -f
```

`Dockerfile` в проекте multi-stage, non-root, с `tini` и `HEALTHCHECK`.
Чтобы поднять Max-бота вторым контейнером, добавь сервис в `docker-compose.yml`:

```yaml
services:
  spas-max:
    build: .
    command: python -m bot.max
    restart: unless-stopped
    env_file: .env
    depends_on: [spas]
```

### 6.4 systemd (без Docker, на bare metal)

```bash
sudo cp deploy/spas.service /etc/systemd/system/
sudo cp deploy/spas-max.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now spas spas-max
sudo systemctl status spas spas-max
```

(Файлы `deploy/spas.service` и `deploy/spas-max.service` — пример ниже,
если их нет в репо, создай с таким содержимым.)

```ini
# /etc/systemd/system/spas.service
[Unit]
Description=SPAS Telegram bot
After=network.target

[Service]
WorkingDirectory=/opt/spas-ai
EnvironmentFile=/opt/spas-ai/.env
ExecStart=/opt/spas-ai/.venv/bin/python -m bot
Restart=always
User=spas

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/spas-max.service
[Unit]
Description=SPAS Max bot
After=network.target

[Service]
WorkingDirectory=/opt/spas-ai
EnvironmentFile=/opt/spas-ai/.env
ExecStart=/opt/spas-ai/.venv/bin/python -m bot.max
Restart=always
User=spas

[Install]
WantedBy=multi-user.target
```

---

## 7. Webhook-режим Telegram (опционально)

Polling работает «из коробки», но webhook быстрее и экономит запросы.

```bash
fly secrets set WEBHOOK_MODE=1 \
                WEBHOOK_URL=https://spas-ai.fly.dev/tg \
                WEBHOOK_SECRET=$(openssl rand -hex 16) \
                WEBHOOK_PORT=8443
fly deploy
```

`fly.toml` уже описывает TLS-сервис на 443 → внутренний порт 8443.
По SIGTERM webhook автоматически снимается через `bot.delete_webhook`.

> **Max** на текущем тестовом этапе использует только **long-polling**.
> Когда потребуется webhook для Max — добавь подписку через
> `POST /subscriptions` (см. <https://dev.max.ru/>).

---

## 8. Бэкапы базы

```bash
# Сгенерировать ключ один раз и сохранить
python -c "import secrets; print(secrets.token_hex(32))"

# Cron / Fly cron (раз в сутки):
python -m tools.backup_db --upload
```

Файл будет вида `spas-2026-05-31_12-30-45.db.enc` в S3-бакете.
Восстановление:

```python
from pathlib import Path
from tools.backup_db import decrypt_file
decrypt_file(Path("spas-...db.enc"), Path("restored.db"), "<KEY_HEX>")
```

---

## 9. Импорт точек АНД из OSM

```bash
# Москва:
python -m tools.import_aed_overpass --bbox 55.5,37.3,56.0,37.9

# Вся Россия (медленнее):
python -m tools.import_aed_overpass

# Посмотреть, что вернётся, без изменения файлов:
python -m tools.import_aed_overpass --dry-run --bbox 55.5,37.3,56.0,37.9
```

Скрипт мерджит результаты в `content/aed_locations.json`, де-дуп по
координатам с точностью ≈ 110 м.

---

## 10. Тестирование

```bash
# Полный конвейер:
ruff check . && ruff format --check .
pre-commit run --all-files
pytest -q --cov=bot --cov=tools --cov-fail-under=70

# Только Max-тесты:
pytest -q tests/test_max_client.py

# Coverage HTML-отчёт:
pytest --cov=bot --cov=tools --cov-report=html
xdg-open htmlcov/index.html
```

---

## 11. Чек-лист «всё работает»

- [ ] `python -m bot` стартует без ошибок и приходит ответ на `/start` в Telegram.
- [ ] `python -m bot.max` стартует и приходит ответ на `/start` в Max.
- [ ] `/sos` показывает категории (🚨 Критические / ⚠ Срочные / 🩹 Лёгкие).
- [ ] При выборе категории видны inline-кнопки сценариев (≥ 3 в каждой).
- [ ] `/panic` показывает интро + дыхательное упражнение.
- [ ] `/dispatcher` показывает список вопросов 112.
- [ ] `/aed` показывает топ-5 точек АНД с координатами.
- [ ] `/help` показывает все команды.
- [ ] `pytest` зелёный, coverage ≥ 70%.
- [ ] `ruff check .` clean.
- [ ] (Прод) `fly status` показывает `running` для всех машин.
- [ ] (Прод) `python -m tools.backup_db --upload` создаёт зашифрованный
      файл в S3-бакете.

---

## 12. Траблшутинг

### «Max API 401 verify.token»

Токен `MAX_BOT_TOKEN` неверный или просрочен. Перевыпусти у `@MasterBot`
(`/edit` → `/getToken`).

### «BOT_TOKEN missing in .env»

В `.env` нет переменной или она пустая. Скопируй `.env.example` → `.env`,
впиши значение, запусти заново.

### «aiogram.exceptions.TelegramConflictError»

Уже запущен другой инстанс с тем же токеном (например, локальный + Fly).
Останови один. В webhook-режиме polling запускать нельзя.

### Max-бот не отвечает, но logs тихие

Long-polling делает запросы каждые 30 секунд. Подожди или
проверь `MAX_API_BASE`. Если за корпоративным прокси — задай `HTTPS_PROXY`.

### Pre-commit «mixed-line-ending» на Windows

```bash
git config --global core.autocrlf false
git rm --cached -r .
git reset --hard
```

### Сертификат не генерится в проде

Проверь, что у процесса есть права писать в `DB_PATH` и что в Fly volume
``spas_data`` подключён (см. `fly.toml`). Сертификаты — деривативы от БД.

### Падение при `pytest`: `ModuleNotFoundError: cryptography`

Установи dev-зависимости: `pip install -r requirements-dev.txt`.

---

## 13. Дополнительно: что ещё можно интегрировать

| Что | Где это в коде | Зависимости |
|---|---|---|
| Голосовой метроном СЛР | `bot/handlers.py:_metronome_*` | `tools/generate_metronome.py`, ffmpeg |
| GigaChat Vision (фото пострадавшего → сценарий) | `bot/vision.py` | `GIGACHAT_AUTH`, OpenSSL CA |
| Дашборд Streamlit | `dashboard.py` | `pip install streamlit pandas` |
| OpenAPI spec REST API | `GET /api/openapi.json` | — |
| PWA-лендинг (RU/EN/UZ/KK) | `landing/index*.html` | любой статик-хост |

---

## 14. Контакты и поддержка

* Репозиторий: <https://github.com/cinderblazequest/egxaalnu>
* PR с финальной полировкой: <https://github.com/cinderblazequest/egxaalnu/pull/2>
* Telegram-документация: <https://core.telegram.org/bots/api>
* Max-документация: <https://dev.max.ru/>

В случае проблем сначала запусти `pytest -v`, потом `ruff check .`,
потом проверь, что `.env` не теряет переменные при `cat .env | grep -c =`.

Хорошего конкурса!
