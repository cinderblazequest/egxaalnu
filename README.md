# СПАС: AI‑помощник первой помощи

[![CI](https://github.com/cinderblazequest/egxaalnu/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/cinderblazequest/egxaalnu/actions/workflows/ci.yml)
[![Python 3.11 | 3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org/)
[![Coverage ≥70%](https://img.shields.io/badge/coverage-%E2%89%A570%25-brightgreen)](.github/workflows/ci.yml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000)](https://github.com/astral-sh/ruff)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![152-ФЗ ready](https://img.shields.io/badge/152--ФЗ-ready-success)](docs/governance_152fz.md)
[![Контест](https://img.shields.io/badge/Конкурс-%C2%ABМоя%20страна%20%E2%80%94%20Моя%20Россия%C2%BB%202026-red)](https://moyastrana.ru)

> Карманный Telegram‑бот первой помощи для подростков 14–17 лет. 30 сценариев, голосовой метроном СЛР, карта АНД, звонок 112 одним нажатием. Работает на отечественном LLM (GigaChat / YandexGPT). Open‑source.

Проект на XXIII Всероссийский конкурс «Моя страна — Моя Россия», номинация «Моё здоровье», категория 14–17 лет, 2026 год.

---

## Что внутри

```
spas-ai/
├── bot/                        # ядро бота на aiogram 3.x
│   ├── __main__.py             # точка входа
│   ├── handlers.py             # все Telegram-обработчики
│   ├── catalogue.py            # загрузчик сценариев + АНД
│   ├── storage.py              # SQLite для аналитики
│   ├── metronome.py            # голосовой/текстовый метроном
│   ├── llm.py                  # интеграция GigaChat / YandexGPT
│   └── aed.py                  # поиск ближайшего АНД (haversine)
├── content/
│   ├── scenarios.json          # 30 сценариев первой помощи
│   └── aed_locations.json      # 12 точек АНД в крупнейших городах
├── audio/                      # mp3-метрономы (см. README внутри)
├── landing/
│   └── index.html              # страница проекта
├── docs/
│   ├── spas_ai_concept_and_27day_plan.md
│   └── spas_ai_application_text.md
├── dashboard.py                # Streamlit-дашборд для жюри
├── requirements.txt
├── Dockerfile
├── fly.toml                    # деплой на Fly.io
├── Procfile                    # деплой на Railway / Render
├── .env.example
└── README.md
```

---

## Деплой за 30 минут (вариант A: Fly.io, рекомендую)

### Шаг 1. Получить Telegram BOT_TOKEN

1. Открой [@BotFather](https://t.me/BotFather) в Telegram.
2. `/newbot` → имя «СПАС — первая помощь» → username `spas_pomosh_bot` (или любой свободный).
3. Скопируй TOKEN. Не показывай никому.
4. (Опционально) `/setdescription`, `/setabouttext`, `/setuserpic` — оформи бота.

### Шаг 2. Получить ключи AI (опционально, бот работает и без них)

- **GigaChat (Сбер):** [developers.sber.ru/portal/products/gigachat](https://developers.sber.ru/portal/products/gigachat) → создать проект → получить API‑ключ. Есть бесплатный лимит.
- **YandexGPT:** [yandex.cloud/services/yandexgpt](https://yandex.cloud/services/yandexgpt) → создать API‑ключ + узнать FOLDER_ID. Free tier есть.

### Шаг 3. Локальный запуск (проверка)

```bash
cd spas-ai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# открой .env и подставь BOT_TOKEN, при желании — ключи AI
python -m bot
```

Открой бота в Telegram, жми `/start`. Должно работать.

### Шаг 4. Деплой на Fly.io (бесплатный free tier 3 машины)

```bash
# один раз: установить flyctl
curl -L https://fly.io/install.sh | sh
flyctl auth signup        # бесплатная регистрация
flyctl auth login

# в папке spas-ai
flyctl launch --no-deploy --copy-config --name spas-ai
flyctl secrets set BOT_TOKEN="123456:ABC..."
# опционально:
flyctl secrets set GIGACHAT_API_KEY="..."
flyctl secrets set ADMIN_ID="123456789"
flyctl volumes create spas_data --size 1
flyctl deploy
```

Проверка:
```bash
flyctl logs            # должно показывать "СПАС-бот запущен: @your_bot"
```

### Шаг 5. Деплой лендинга (бесплатно, 5 минут)

Вариант A (GitHub Pages): закоммитить `landing/` в публичный репозиторий, в Settings → Pages выбрать ветку `main` и папку `/landing`.

Вариант B (Tilda): создать новую страницу в Tilda, скопировать HTML в Zero Block. Прицепить домен — бесплатно через `*.tilda.ws`.

### Шаг 6. Поднять дашборд для жюри (опционально)

```bash
pip install streamlit pandas
streamlit run dashboard.py
```

Открой `http://localhost:8501`. Скриншоты этого экрана — приложение к заявке.

---

## Деплой за 30 минут (вариант B: Railway, ещё проще)

1. Зарегистрируйся на [railway.app](https://railway.app) (есть бесплатный $5/мес).
2. New Project → Deploy from GitHub repo → выбери свой `spas-ai`.
3. В Variables добавь `BOT_TOKEN` и опционально `GIGACHAT_API_KEY`.
4. Railway сам построит образ через `Dockerfile` и запустит. Готово.

---

## Деплой за 30 минут (вариант C: VPS Selectel / TimeWeb, 200–300 ₽/мес)

```bash
# на VPS (Ubuntu 24.04)
sudo apt update && sudo apt install -y python3-pip python3-venv git
git clone https://github.com/<твой-юзернейм>/spas-ai.git
cd spas-ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # подставь BOT_TOKEN
sudo tee /etc/systemd/system/spas.service <<'EOF'
[Unit]
Description=СПАС бот
After=network.target
[Service]
WorkingDirectory=/root/spas-ai
ExecStart=/root/spas-ai/.venv/bin/python -m bot
Restart=always
EnvironmentFile=/root/spas-ai/.env
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now spas
sudo journalctl -u spas -f
```

---

## Что бот умеет

- `/start` — главное меню (3 категории, ~30 сценариев)
- `/sos` — экстренный экран с алгоритмом
- `/aed` — поиск ближайшего АНД по геолокации
- `/ask` — свободный вопрос AI (требует ключ GigaChat / YandexGPT)
- `/panic` — кнопка «мне страшно»: 4-7-8 дыхание + 5-4-3-2-1 grounding
- `/dispatcher` — что говорить оператору 112 (5 вопросов)
- `/feedback` — NPS‑опрос
- `/stats` — метрики (только для админа по `ADMIN_ID`)
- `/profile` — XP, уровень, ачивки (геймификация)
- `/teacher`, `/join CODE`, `/teacher_dashboard` — учительский режим
- `/sos_contact`, `/sos_share`, `/sos_clear` — доверенный контакт + геолокация
- `/share_progress`, `/share_certificate` — поделиться с близкими
- `/accessibility` — plain-text режим без эмодзи и HTML
- Голосовой ввод (Yandex SpeechKit) — опционально, через `YANDEX_STT_API_KEY`
- Сценарии: pre‑test → пошаговый алгоритм → post‑test → automatic learning gain
- Голосовой метроном для модулей СЛР (110 BPM)
- Кнопка «Позвонить 112» (`tel:` deep link, открывает звонилку)
- Аналитика: события, NPS, pre/post в SQLite

## Дополнительные сервисы

- **REST API** (`/api/scenarios`, `/api/aed`, `/api/dispatcher`, `/api/panic`)
  на порту `API_PORT=8090` — для встраивания в школьные сайты.
- **Виджет** `landing/widget.js` — две строки в HTML и блок с топ-9
  сценариев + кнопка запуска бота.
- **PWA-лендинг** — добавляется на главный экран Android/iOS, работает
  офлайн (cached scenarios + service worker).
- **Liveness** на порту `HEALTH_PORT=8080` (`/health`) — для Fly.io /
  Railway healthcheck.
- **Дашборд (D)** — когортный retention, NPS-хитмэп, поведенческая воронка,
  A/B-эксперименты, лидерборд XP. Запуск: `streamlit run dashboard.py`.

## Запуск всех компонентов одной командой

```bash
docker compose up --build
```

Запустит бота с включённым `/health`, REST API и SQLite в `./data/spas.db`.

## Документы для конкурса

- `docs/jury_deck.md` — Marp-дек на 10 слайдов (`npx @marp-team/marp-cli` → PDF/PPTX).
- `docs/finance_model.md` — финансовая модель на 3 года.
- `docs/roadmap.md` — Mermaid Gantt 2026–2028.
- `docs/governance_152fz.md` — соответствие 152-ФЗ.

## Метрики (для заявки и защиты)

Дашборд показывает:
- Уникальных пользователей всего и DAU
- Завершённые сценарии (completion rate)
- Средний NPS
- Средний прирост компетенции (pre → post)
- Топ‑10 сценариев
- Графики событий по дням

---

## Лицензии

- **Код:** Apache License 2.0 — свободно копируйте, форкайте, коммерциализируйте.
- **Контент сценариев:** CC BY‑NC‑SA 4.0 — любая школа/СОНКО может использовать с указанием автора.

## Источники медицинского контента

- Российский Национальный Совет по реанимации — открытые рекомендации
- ERC Guidelines 2021 (European Resuscitation Council)
- Позиция Минздрава РФ по снижению смертности от внешних причин (2024)
- ВОЗ, резолюция «Kids Save Lives» (2015)

## Дисклеймер

СПАС — справочно‑информационный сервис. Не заменяет 112/103 и профессиональную медицинскую помощь. При любой опасной ситуации — звонок 112.

---

## Контакты автора

[ФИО], 17 лет, [Школа], [Регион]
- Telegram: [@username]
- VK: [vk.com/...]
- Email: [...]
- GitHub: [...]
