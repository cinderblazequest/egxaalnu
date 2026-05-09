# СПАС — ROADMAP: всё, что осталось добавить, чтобы проект стал лучшим

> Документ — детальный план по «добиванию» проекта до уровня
> «гарантированно лучший в номинации». Делится на:
>
> 1. **Чисто кодовые задачи** — может сделать Devin (автоматизируется).
> 2. **Гибридные задачи** — нужны и код, и человек (контент, согласование).
> 3. **Чисто человеческие** — нельзя автоматизировать (пилот, видео, врач).
>
> К каждой задаче дан: цель, оценка вклада в баллы конкурса, файлы,
> шаги, скелет кода/документа (где имеет смысл), Definition of Done.

Текущее состояние (на 2026-05-09):
* 210 автотестов, **76.27%** coverage, ruff/format/pre-commit clean.
* Telegram-бот на aiogram + Max-бот через `bot/max/`.
* Лендинг RU/EN/UZ/KK, REST API, виджет, дашборд, Docker, Fly.io.
* PR #2 открыт: <https://github.com/cinderblazequest/egxaalnu/pull/2>.

---

## Часть A. Кодовые задачи (Devin может сделать сам)

### A1. Полный паритет Max ↔ Telegram (пошаговые сценарии, гамификация, Vision) — критично

**Цель.** Сейчас Max-бот показывает текст сценария целиком одним сообщением.
В Telegram то же самое прокликивается по шагам с кнопками `< / >`,
встроенным метрономом, тестом «до/после», и закрывается выдачей
сертификата. Жюри будет проверять Max — и если там «текстовая стена»,
впечатление развалится. Нужно полное соответствие.

**Прирост баллов:** +1 балл (двухплатформенность с одинаковым UX).

**Файлы:**
* `bot/max/handlers.py` — расширить логику (state-машина по шагам).
* `bot/max/state.py` (новый) — простое in-memory + SQLite хранение
  «где пользователь в сценарии».
* `bot/max/__main__.py` — без изменений.
* `tests/test_max_state.py` (новый) — юнит-тесты state-машины.
* `bot/storage.py` — переиспользовать таблицы `scenarios_progress`,
  `user_xp`, `user_settings` (UNIQUE по `user_id` уже есть, добавить
  `platform` колонку через миграцию m012).

**Шаги:**
1. Добавить миграцию `m012_max_users` в `bot/migrations.py`:
   ```sql
   ALTER TABLE users ADD COLUMN platform TEXT NOT NULL DEFAULT 'telegram';
   CREATE INDEX IF NOT EXISTS idx_users_platform ON users(platform);
   ```
2. Завести модуль `bot/max/state.py` со state-машиной:
   ```python
   class StepState(NamedTuple):
       scenario_id: str
       step_idx: int

   _state: dict[int, StepState] = {}  # in-memory; для перезапуска — sqlite

   async def remember(uid, sid, idx): ...
   async def forget(uid): ...
   ```
3. В `handle_callback` добавить payload-префиксы:
   * `step:<sid>:<idx>` — показать конкретный шаг,
   * `pre:<sid>` / `post:<sid>` — pre/post-тест,
   * `metro:<sid>` — отправить голосовой mp3-файл (`audio/metronome_*`).
4. Реализовать функцию `render_step(scenario, idx)` с кнопками
   `[« Назад] [Дальше »]`, прогресс-баром «3 / 7».
5. На последнем шаге — pre-test inline-кнопками, по завершении —
   `post-test`, генерация сертификата через `bot.certificate.build_certificate_code`.
6. Vision: метод `MaxBotClient.upload_attachment` (Max API
   `POST /uploads` → `POST /messages` с `attachments=[image]`).
   Re-use `bot/vision.py:analyze_photo()` — ему всё равно, откуда фото.

**Definition of Done:**
* `python -m bot.max` → `/sos` → выбор сценария → пошаговое прохождение
  → pre-test → post-test → код сертификата.
* `tests/test_max_state.py` — минимум 8 кейсов (next/prev, выход за
  границы, перезапуск с восстановлением шага).
* coverage `bot/max/` ≥ 80%.

---

### A2. Webhook-режим для Max — полезно

**Цель.** Long-polling каждый раз шлёт `GET /updates?timeout=30` —
это нагрузка и задержка ≤ 30 сек. Webhook через
`POST /subscriptions` снижает latency до миллисекунд.

**Прирост баллов:** +0.3 балла (production-ready).

**Файлы:**
* `bot/max/webhook.py` (новый) — aiohttp endpoint `/max/tg`.
* `bot/max/__main__.py` — флаг `MAX_WEBHOOK_MODE=1`.
* `fly.toml` — внутренний порт 8444 (отдельно от Telegram-webhook 8443).

**Шаги:**
1. Изучить запросы `POST /subscriptions` (документация Max OpenAPI).
2. На старте, если `MAX_WEBHOOK_MODE=1`, вызвать
   `client.post('/subscriptions', json={"url": MAX_WEBHOOK_URL, "update_types": [...]})`.
3. aiohttp-приложение принимает `POST /max/tg`, парсит JSON в
   формате update, вызывает `dispatch_update`.
4. На SIGTERM — `DELETE /subscriptions?url=...`.

**Definition of Done:**
* `MAX_WEBHOOK_MODE=1` → бот стартует, `curl -X POST /max/tg -d '<update>'`
  доставляет апдейт.
* IP-белый список из документации Max (`185.16.150.0/30` etc.)
  валидируется перед обработкой.

---

### A3. Гамификация в Max (XP, ачивки, лидерборд) — важно

**Цель.** В Telegram пользователь получает XP за прохождение сценариев
и pre/post-тесты, видит прогресс и сертификат. В Max этого пока нет.

**Прирост баллов:** +0.5 балла.

**Файлы:**
* `bot/max/handlers.py` — после успешного post-test вызывать
  `bot.gamification.add_xp(user_id, action="scenario_complete")`.
* `bot/max/handlers.py` — команда `/profile` показывает XP, ачивки.

**Шаги:**
1. Хук в обработчике post-test:
   ```python
   from bot.gamification import add_xp, evaluate_achievements
   await add_xp(uid, "scenario_complete", scenario_id=sid)
   new_ach = await evaluate_achievements(uid)
   if new_ach:
       await client.send_message(chat_id, f"🏆 Новая ачивка: {new_ach.title}")
   ```
2. `/profile` рисует:
   ```
   👤 Твой профиль
   XP: 240 · стрик: 3 дня
   🏆 Ачивки (4): Первый шаг, Сердце-герой, Спокойствие, Полиглот
   📋 Сценариев пройдено: 12 / 30
   ```
3. `/leaderboard` — топ-10 по XP за неделю (с маскированными именами).

**Definition of Done:**
* После прохождения 1 сценария в Max XP в `user_xp` обновляется.
* `/profile` показывает корректные числа.

---

### A4. Onboarding-туториал в боте (`/start` → демо за 60 секунд) — важно

**Цель.** Сейчас `/start` показывает менюшку. Жюри/учитель ОБЖ может
кликать наугад. Нужен короткий гайд: «3 экрана + 1 практика».

**Прирост баллов:** +0.4 балла (UX и engagement).

**Файлы:**
* `bot/handlers.py` — новый обработчик `/onboarding` и подкоманда
  на первом `/start`.
* `bot/i18n.py` — ключи `onb.step1/step2/step3/finish` для 4 языков.
* `bot/max/handlers.py` — мирроринг.
* `tests/test_onboarding.py`.

**Сценарий онбординга:**
1. **Экран 1.** «Я СПАС, помогаю в первой помощи. Если опасно — звони 112.»
2. **Экран 2.** Кнопка «Попробовать сценарий» → запускается `cuts_minor` (лёгкая порез).
3. **Экран 3.** После прохождения — «Молодец! Ты получил +20 XP. Открой /sos для всех сценариев.»

**Definition of Done:**
* Новый пользователь, нажав `/start`, проходит 60-секундный туториал.
* `tests/test_onboarding.py` ≥ 6 кейсов.

---

### A5. Marp-презентация для жюри (PDF + PPTX) — важно

**Цель.** Конкурс судят по **видео и презентации**, не по коду.
Сейчас в `docs/jury_deck.md` есть скелет на 10 слайдов, надо довести
до прод-уровня и сгенерировать.

**Прирост баллов:** +0.6 балла (защита проекта).

**Файлы:**
* `docs/jury_deck.md` — расширить до 12–15 слайдов.
* `docs/assets/` — иконки, скриншоты, графики (placeholder, нужны
  реальные).
* `Makefile` — таргет `make slides` (`npx @marp-team/marp-cli docs/jury_deck.md -o docs/jury.pdf`).

**Структура слайдов:**
1. **Титул** + лого + автор.
2. **Проблема:** 60% подростков не могут оказать первую помощь
   (ссылка на Росстат / ВЦИОМ). Сердечно-сосудистые → 1.4 млн
   смертей/год в РФ.
3. **Решение:** AI-помощник в Telegram + Max.
4. **Демо:** скриншот сценария «остановка сердца».
5. **30 сценариев + AED-карта + 112 + паника-протокол.**
6. **AI-фишки:** GigaChat Vision, метроном, гамификация.
7. **2 платформы, 4 языка.**
8. **Соответствие 152-ФЗ + дисклеймер.**
9. **Метрики пилота** (когда будут).
10. **Бизнес-модель:** B2G (МЧС/Минобр), B2B (страховые), B2C freemium.
11. **Команда + дорожная карта.**
12. **Что нужно сейчас:** партнёрство МЧС, пилот в 5 школах.

**Definition of Done:**
* `make slides` → `docs/jury.pdf`, `docs/jury.pptx`.
* Все скриншоты — реальные (не placeholder).
* В CI добавить шаг «build slides» (artefact).

---

### A6. Скрипт сидинга демо-данных — полезно

**Цель.** Чтобы скриншоты в презентации/лендинге не были пустыми.
Скрипт должен создать 5 фейковых пользователей, прогнать им сценарии,
выдать XP, ачивки, заполнить отзывы.

**Прирост баллов:** +0.2 балла (через UX-демо).

**Файлы:**
* `tools/seed_demo.py` (новый) — CLI: `python -m tools.seed_demo --users 5 --scenarios 12`.
* `tests/test_seed_demo.py`.

**Скелет:**
```python
import argparse
from bot.storage import init_db
from bot.gamification import add_xp

async def seed(users: int, scenarios: int) -> None:
    await init_db()
    for i in range(users):
        uid = 100_000 + i
        for j in range(scenarios):
            await add_xp(uid, "scenario_complete", scenario_id=f"demo_{j}")
    print(f"Создано {users} пользователей × {scenarios} сценариев")
```

**Definition of Done:**
* `python -m tools.seed_demo --users 5` → в БД появляется 5 пользователей
  с реалистичным распределением XP.
* `--reset` опция полностью пересоздаёт БД для воспроизводимых демо.

---

### A7. Видео-генератор демо-кадров (asciinema → mp4) — полезно

**Цель.** Часть видео можно автоматизировать: показать терминал
с тестами, докер-билдом, метриками.

**Прирост баллов:** +0.1 балла (technical demo).

**Файлы:**
* `tools/record_demo.sh` — bash-скрипт записи прохождения через
  Telegram MTProto-клиент или через REST API.
* `docs/demo_script.md` — раскадровка.

**Шаги:**
1. Поставить `asciinema` локально: `apt install asciinema`.
2. `asciinema rec docs/demo_terminal.cast` — записать прохождение
   `pytest`, `docker build`, `fly deploy`.
3. Конвертировать через `agg`: `agg --theme monokai docs/demo_terminal.cast docs/demo_terminal.gif`.

---

### A8. README badges + GitHub Pages для лендинга — мелочь, но важно для впечатления

**Цель.** При первом взгляде на репозиторий должны быть бейджи
«CI passing», «coverage 76%», «license MIT», «Telegram + Max».
Лендинг должен открываться по ссылке `https://cinderblazequest.github.io/egxaalnu/`.

**Прирост баллов:** +0.1 балла.

**Файлы:**
* `README.md` — блок бейджей сверху.
* `.github/workflows/pages.yml` (новый) — публикация `landing/` в Pages.

**Скелет workflow:**
```yaml
name: Pages
on:
  push: { branches: [main] }
permissions: { contents: read, pages: write, id-token: write }
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/upload-pages-artifact@v3
        with: { path: landing }
      - uses: actions/deploy-pages@v4
```

---

### A9. Sentry production-ready инициализация — мелочь

**Цель.** Сейчас `SENTRY_DSN` упоминается в .env, но не подключается.

**Файлы:**
* `bot/sentry_setup.py` (новый).
* `bot/__main__.py` + `bot/max/__main__.py` — вызов `sentry_setup.init()`.

**Скелет:**
```python
import os, sentry_sdk
def init() -> None:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return
    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.05, environment=os.getenv("APP_ENV", "prod"))
```

В `requirements.txt` добавить `sentry-sdk==2.14.0`.

---

### A10. Расширение тестов до 85% coverage — приятный бонус

**Цель.** Сейчас `bot/storage.py` 68%, `tools/import_aed_overpass.py` 59%
— подтянуть до общего 85%.

**Файлы:**
* `tests/test_storage_full.py` — все методы хранилища.
* `tests/test_import_aed_full.py` — main(), Russia bbox.

**Definition of Done:**
* `pytest --cov-fail-under=85` зелёный.

---

### A11. Контейнер для Max с автоматическим деплоем на Fly — для прода

**Цель.** Один `fly deploy` поднимает оба процесса. Сейчас Max нужно
запускать отдельной машиной вручную.

**Файлы:**
* `fly.toml` — добавить `[processes]` секцию:
  ```toml
  [processes]
  app = "python -m bot"
  max = "python -m bot.max"
  ```
* `Dockerfile` — без изменений (CMD не используется при processes).

---

## Часть B. Гибридные (нужно и код, и человек)

### B1. Контент: пересмотр всех 30 сценариев врачом-реаниматологом

**Цель.** Самая важная задача проекта. Без подписи врача жюри
вправе указать на риск выдачи неверных рекомендаций.

**Что нужно от врача:**
* Прочитать `content/scenarios.json`, проверить каждый шаг.
* Подписать `docs/medical_review.md` с указанием специальности и места работы.
* Желательно — отзыв 2–3 фразы для лендинга и презентации.

**Что Devin может сделать заранее:**
* Сформировать `docs/medical_review_template.md` с табличкой
  «сценарий / источник / шаги / проверено / комментарий».
* Подготовить чек-лист «соответствие ESC 2021 / ERC 2021 / МЧС».
* Сделать diff-инструмент `tools/scenario_diff.py`, который сравнивает
  текущие сценарии с эталонными источниками (ERC PDF).

**Где искать врача:**
* Кафедра анестезиологии и реаниматологии медвуза.
* Областной центр медицины катастроф (ОЦМК).
* МЧС России (отдел медицинского обеспечения).
* Скорая помощь (главврач подстанции).

---

### B2. Пилот в 1 школе на 30+ учеников

**Цель.** Главная метрика — реальное использование. Учитель ОБЖ
проводит 2 урока с использованием бота, потом анкетирует учеников.

**Что Devin подготавливает:**
* `docs/pilot_kit.md` — методические материалы для учителя:
  - План урока (45 мин × 2): теория + практика с ботом + тест.
  - Анкета «до» и «после» (Google Forms / Yandex Forms).
  - QR-коды для входа в бот.
* `docs/jury_pilot_results_template.md` — шаблон отчёта по пилоту.

**Что делает человек:**
* Договариваются с учителем ОБЖ.
* Проводят пилот, собирают анкеты.
* Заполняют отчёт (5 цифр: явка, NPS, % успешных тестов «до/после»,
  отзывы, фото).

---

### B3. Партнёрские письма поддержки

**Цель.** Жюри ценят официальные письма от значимых организаций.

**Что Devin готовит:**
* `docs/letters/template_school.docx` — текст письма от школы.
* `docs/letters/template_mchs.docx` — текст от МЧС.
* `docs/letters/template_health.docx` — от больницы / медцентра.

**Что делает человек:**
* Идёт к директору школы / в МЧС / больницу с письмом и просит
  подписать на бланке.
* Сканирует подписанные → `docs/letters/signed_<organization>.pdf`.

---

### B4. Видео-демо 2–3 минуты

**Цель.** Жюри смотрит видео ДО кода. Без качественного видео
проект могут пропустить.

**Что Devin готовит:**
* `docs/video_storyboard.md` — раскадровка по секундам:
  - 0–10 с: статистика (60% подростков не могут СЛР).
  - 10–40 с: live-сценарий «остановка сердца» в Telegram.
  - 40–60 с: переключение на Max — то же самое.
  - 60–90 с: GigaChat Vision показывает фото → автоматический сценарий.
  - 90–120 с: дашборд с метриками пилота.
  - 120–150 с: команда, что просим у конкурса.
* `docs/video_subtitles.srt` — субтитры RU + EN.
* `docs/video_voiceover.md` — текст за кадром.

**Что делает человек:**
* Записать (можно на телефон, OBS Studio, Бандикам).
* Смонтировать в DaVinci Resolve / CapCut.
* Озвучить или нанять диктора (Озвучка.ru, Boomerang).

---

### B5. Скриншоты для лендинга и презентации

**Цель.** На лендинге сейчас placeholder-картинки.

**Что Devin готовит:**
* `tools/seed_demo.py` (см. A6) → реалистичные данные.
* Список нужных скриншотов в `docs/screenshots_required.md`:
  1. Telegram: главное меню.
  2. Telegram: сценарий «остановка сердца», шаг 3 с метрономом.
  3. Telegram: сертификат.
  4. Max: главное меню.
  5. Max: пошаговое прохождение.
  6. Лендинг: 4 языка.
  7. Дашборд: график retention.
  8. AED-карта.

**Что делает человек:**
* Открыть бота в эмуляторе или на телефоне.
* Сделать скриншоты по чек-листу.
* Сложить в `landing/screenshots/` (PNG ≤ 800 КБ каждый).

---

## Часть C. Чисто человеческие (Devin не может)

### C1. Регистрация Max-бота через @MasterBot
Установить Max → найти `@MasterBot` → `/create` → получить `MAX_BOT_TOKEN`.
Без этого токена Max-бот не запустится физически.

### C2. Регистрация в каталогах
* Опубликовать Max-бота в каталоге Max (через @MasterBot → `/publish`).
* Telegram-бот: добавить в `@StoreBot` или `@SearchBot`.

### C3. Свой домен и SSL
* Купить домен (например, `spas-ai.ru` через РЕГРУ — 200 ₽/год).
* Настроить DNS на Fly.io: `fly certs add spas-ai.ru`.
* Обновить `WEBHOOK_URL`, `landing/sitemap.xml`, README.

### C4. Юридические документы
* Политика конфиденциальности (`landing/privacy.html`) — есть
  шаблон, нужно подписать своими данными (ФИО, email, ИП/ООО).
* Согласие на обработку (`bot/i18n.py:consent.text`) — проверить юристом.
* Дисклеймер о медицинском контенте — желательно проверить юристом.

### C5. Юридические лица для гранта/конкурса
* ИП или Самозанятость (для подачи на гранты).
* Расчётный счёт (без него многие конкурсы не примут заявку).

---

## Часть D. Метрики и измерения (Devin может посчитать только при условии данных)

### D1. Когортный retention
**Файл:** `dashboard.py` уже считает. Нужны реальные пользователи (B2).

### D2. NPS-хитмэп
**Файл:** `dashboard.py:_render_nps()`. Нужны реальные ответы из таблицы `feedback`.

### D3. Pre/Post-тест дельта
**Файл:** `dashboard.py:_render_test_diff()`. Уже работает на демо-данных
от A6 (после запуска `seed_demo.py`).

---

## Финальный приоритет (что делать первым)

| Приоритет | Задача | Кому | Срок |
|---|---|---|---|
| 1 | C1 — токен Max | Тебе | 5 мин |
| 2 | A1 — паритет Max ↔ Telegram | Devin | 2 ч |
| 3 | B1 — медицинская проверка | Тебе | 3–5 дней |
| 4 | A5 — презентация Marp | Devin | 1 ч |
| 5 | B4 — видео-демо | Тебе | 1 день |
| 6 | A4 — onboarding | Devin | 1 ч |
| 7 | B2 — пилот в школе | Тебе | 1–2 недели |
| 8 | A6 — seed_demo | Devin | 30 мин |
| 9 | B5 — скриншоты | Тебе | 30 мин |
| 10 | A3 — гамификация Max | Devin | 1 ч |
| 11 | B3 — письма поддержки | Тебе | 1 неделя |
| 12 | A2 — webhook Max | Devin | 1 ч |
| 13 | A7-A11 — мелочи | Devin | 2–3 ч |

---

## Команды для следующей сессии Devin

Если хочешь, чтобы Devin продолжил, запусти задачи в таком порядке.
Каждая команда — отдельная сессия / запрос:

```
1) "Сделай A1 из ROADMAP.md (паритет Max и Telegram)"
2) "Сделай A4 из ROADMAP.md (onboarding-туториал)"
3) "Сделай A5 из ROADMAP.md (Marp-презентация)"
4) "Сделай A6 из ROADMAP.md (seed_demo)"
5) "Сделай A3 из ROADMAP.md (гамификация Max)"
6) "Сделай A2, A7, A8, A9, A10, A11 из ROADMAP.md за один проход"
```

Для гибридных:
```
"Подготовь B1 (medical_review_template.md, scenario_diff.py)"
"Подготовь B2 (pilot_kit.md, анкеты, QR-коды)"
"Подготовь B3 (письма-шаблоны)"
"Подготовь B4 (storyboard, субтитры, voiceover)"
"Подготовь B5 (список нужных скриншотов)"
```

---

## Что получится после полного выполнения этого ROADMAP

* **2 платформы** (Telegram + Max) с полным паритетом UX.
* **30 сценариев** проверены врачом-реаниматологом.
* **Пилот в школе** с 30+ учениками и реальными метриками.
* **Видео-демо** 2–3 мин с субтитрами на RU/EN.
* **Marp-презентация** на 12 слайдов (PDF + PPTX).
* **Письма поддержки** от школы / МЧС / медцентра.
* **GitHub Pages** с лендингом на 4 языках.
* **Sentry** + **S3-бэкапы** в проде.
* **Тесты** ≥ 85% coverage, CI matrix Python 3.11/3.12.
* **README** с реальными бейджами и метриками пилота.
* **Юр-документы:** политика конфиденциальности, дисклеймер, согласие.

С таким набором проект становится **серьёзным претендентом на 1-е место** —
не «учебный бот школьника», а **готовая к внедрению платформа**.

Удачи! Если что — пиши «Сделай X из ROADMAP.md» и Devin продолжит.
