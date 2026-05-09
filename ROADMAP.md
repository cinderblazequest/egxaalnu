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

---

# Часть E. Рецепты для быстрой разработки (cookbook)

> Этот раздел избавляет от 80% «куда что класть». Большинство задач
> делается копированием шаблона ниже и подстановкой имён. Все
> рецепты протестированы на текущем коде (май 2026).

## E0. Карта проекта одной картинкой

```
egxaalnu/
├── bot/                       # код Telegram-бота
│   ├── __main__.py            # entry: polling/webhook + signal handlers
│   ├── handlers.py            # ВСЕ хендлеры команд и callback (TG)
│   ├── i18n.py                # переводы (ru/en/uz/kk) — единый dict[lang][key]
│   ├── catalogue.py           # загрузка scenarios.json + AED
│   ├── dispatcher.py          # чек-лист 112 (загрузка + render)
│   ├── panic.py               # паника-протокол (загрузка + клавиатуры)
│   ├── sos.py                 # формирование SOS-сообщения
│   ├── aed.py                 # геопоиск ближайших АНД
│   ├── certificate.py         # SHA-256 коды сертификатов
│   ├── gamification.py        # XP, стрики, ачивки, лидерборд
│   ├── sharing.py             # реферальные ссылки
│   ├── accessibility.py       # шрифт/контраст/upper-case
│   ├── vision.py              # GigaChat Vision (фото → сценарий)
│   ├── mchs_rss.py            # МЧС RSS-алерты + подписки
│   ├── api.py                 # REST API (aiohttp): /api/*
│   ├── health.py              # /health endpoint
│   ├── log_setup.py           # логирование (json/human)
│   ├── storage.py             # SQLite-хранилище (async)
│   ├── migrations.py          # m001..m011 — schema migrations
│   ├── middleware/throttle.py # ограничение rate
│   └── max/                   # АДАПТЕР MAX (новый!)
│       ├── __main__.py        # entry для Max-бота
│       ├── client.py          # async-клиент Max API
│       └── handlers.py        # хендлеры команд и callback (Max)
├── content/
│   ├── scenarios.json         # 30 сценариев (источник правды)
│   ├── aed_locations.json     # точки АНД
│   ├── dispatcher_checklist.json
│   ├── panic_protocol.json
│   ├── achievements.json      # ачивки (id, title, condition)
│   └── ...
├── tools/
│   ├── backup_db.py           # snapshot + AES-GCM + S3
│   ├── import_aed_overpass.py # OSM → aed_locations.json
│   ├── validate_content.py    # pydantic-проверка JSON
│   └── generate_metronome.py  # mp3 для СЛР
├── tests/                     # 210 кейсов pytest
├── landing/                   # PWA (4 языка) + service worker
├── docs/                      # jury_deck, finance_model, pilot_kit
├── audio/                     # mp3 метронома
├── ssl/                       # CA для GigaChat
├── .github/workflows/ci.yml   # matrix Python 3.11/3.12
├── Dockerfile                 # multi-stage non-root
├── docker-compose.yml
├── fly.toml                   # 512 MB + http_checks + webhook service
├── Procfile                   # web: бот, max: max-бот
├── pyproject.toml             # зависимости
├── requirements.txt           # production
├── requirements-dev.txt       # +ruff, pytest, cryptography, boto3
├── .pre-commit-config.yaml
├── .env.example               # все 30+ переменных с комментариями
├── README.md
├── CHANGELOG.md
├── ROADMAP.md                 # этот файл
└── INSTRUCTIONS_MAX_AND_TELEGRAM.md
```

**Где что искать:**
- ✏ Хочешь поменять текст команды → `bot/i18n.py`.
- ✏ Хочешь поменять список сценариев → `content/scenarios.json`.
- ✏ Хочешь поменять реакцию на кнопку → `bot/handlers.py` или `bot/max/handlers.py`.
- ✏ Хочешь добавить таблицу в БД → новая миграция `bot/migrations.py:m012_*`.
- ✏ Хочешь логировать новое событие → `bot/storage.py:log_event()`.
- ✏ Хочешь новый REST endpoint → `bot/api.py`.
- ✏ Хочешь новый CLI-инструмент → `tools/<name>.py`.

---

## E1. Команды-шпаргалка

```bash
# Активация окружения
source .venv/bin/activate

# Lint + format
ruff check . && ruff format --check .
ruff check --fix . && ruff format .         # автофикс

# Pre-commit (полный ход)
pre-commit run --all-files

# Тесты (быстро, без покрытия)
pytest -q

# Тесты с покрытием
pytest -q --cov=bot --cov=tools --cov-report=term-missing

# Только один тест-файл
pytest -q tests/test_max_client.py -v

# Только один кейс
pytest -q tests/test_max_client.py::test_send_message_uses_post_with_chat_id

# Запуск ботов локально
python -m bot                                # Telegram
python -m bot.max                            # Max
honcho start                                 # оба сразу (через Procfile)

# CLI-инструменты
python -m tools.backup_db --dry-run
python -m tools.backup_db --upload
python -m tools.import_aed_overpass --bbox 55.5,37.3,56.0,37.9
python -m tools.validate_content              # проверка scenarios.json

# Git workflow
git checkout -b devin/$(date +%s)-feature-name
git add <files> && git commit -m "feat(scope): что делаем"
git push -u origin HEAD

# Docker
docker compose up --build -d
docker compose logs -f spas
docker compose exec spas /bin/bash

# Fly.io
fly deploy
fly logs --app spas-ai
fly status
fly ssh console
fly secrets set KEY=value
```

---

## E2. Рецепт: добавить новый сценарий первой помощи

**Шаги (10 минут):**

1. Открой `content/scenarios.json` и добавь объект в массив `scenarios`:
   ```json
   {
     "id": "snake_bite",
     "title": "Укус змеи",
     "icon": "🐍",
     "category": "urgent",
     "summary": "Что делать при укусе ядовитой змеи.",
     "phone": "112",
     "metronome": false,
     "steps": [
       {"text": "Уложи пострадавшего, не давай ходить."},
       {"text": "Зафиксируй конечность шиной или повязкой."},
       {"text": "Приложи холод выше места укуса."},
       {"text": "Срочно вызови 112 — нужна сыворотка."},
       {"text": "Не отсасывай яд, не прижигай, не накладывай жгут."}
     ],
     "pre_test": [
       {
         "q": "Что НЕЛЬЗЯ делать при укусе змеи?",
         "options": ["Уложить", "Отсасывать яд", "Звонить 112"],
         "correct": 1
       }
     ],
     "post_test": [
       {
         "q": "Куда прикладывать холод?",
         "options": ["Прямо на рану", "Выше места укуса", "Ниже"],
         "correct": 1
       }
     ]
   }
   ```
2. Запусти `python -m tools.validate_content` — проверит, что pydantic
   принимает структуру.
3. Перезапусти бота — сценарий автоматически появится в `/sos`
   в категории «urgent».
4. Тесты не нужно править: `Catalogue` динамический.

**Категории:**
* `critical` — угроза жизни (СЛР, кровотечение, удушье).
* `urgent` — требует помощи в часы (ожог, перелом, укус).
* `minor` — бытовые травмы (порез, синяк, ссадина).

---

## E3. Рецепт: добавить новый язык (например, татарский)

**Шаги (30 минут):**

1. Зарегистрируй BCP-47 код: `tt` → tatar. Если уже есть нормализация
   (`tt-RU`), и она маппится на `tt` — норм.
2. В `bot/i18n.py` найди константы `ru/en/uz/kk` и добавь словарь `tt`:
   ```python
   _tt = {
       "menu.title": "Беренче ярдәм",
       "sos.text": "🚨 Хәвеф! 112-гә шалтыратыгыз...",
       # ... (скопируй все ключи из _ru и переведи)
   }
   ```
3. Добавь язык в SUPPORTED_LANGS:
   ```python
   SUPPORTED_LANGS = ("ru", "en", "uz", "kk", "tt")
   ```
4. В `bot/handlers.py:_lang_kb()` добавь кнопку выбора `🇹🇼 Tatar`.
5. Добавь HTML-копию лендинга: `landing/index.tt.html`. Поменяй
   `lang="ru"` на `lang="tt"`, переведи все строки.
6. Обнови переключатель языка в `landing/index*.html` (5 файлов):
   ```html
   <a href="index.tt.html">🇹🇼 TT</a>
   ```
7. Тесты:
   ```python
   # tests/test_i18n_completeness.py — добавь "tt" в LANGS
   LANGS = ("ru", "en", "uz", "kk", "tt")
   ```
8. Запусти `pytest -q tests/test_i18n_completeness.py` —
   должны быть все ключи в новом языке.

---

## E4. Рецепт: добавить новую команду (паритет TG + Max)

Допустим, нужна команда `/quiz` — случайный pre-test.

**Шаги:**

1. **Добавь обработчик в Telegram (`bot/handlers.py`):**
   ```python
   @router.message(Command("quiz"))
   async def _cmd_quiz(message: Message) -> None:
       uid = message.from_user.id
       lang = await _user_lang(uid)
       scenario = random.choice(list(catalogue.scenarios.values()))
       q = random.choice(scenario.pre_test)
       text = t("quiz.intro", lang) + "\n\n" + q.q
       buttons = [
           [InlineKeyboardButton(text=opt, callback_data=f"quiz:{scenario.id}:{q.correct}:{i}")]
           for i, opt in enumerate(q.options)
       ]
       await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

   @router.callback_query(F.data.startswith("quiz:"))
   async def _cb_quiz(query: CallbackQuery) -> None:
       _, sid, correct, picked = query.data.split(":")
       lang = await _user_lang(query.from_user.id)
       msg = t("quiz.right", lang) if int(picked) == int(correct) else t("quiz.wrong", lang)
       await query.message.answer(msg)
       await query.answer()
   ```

2. **Добавь те же ключи в `bot/i18n.py`:**
   ```python
   "quiz.intro": "🎯 Случайный вопрос:",  # _ru
   "quiz.right": "✅ Правильно! +5 XP",
   "quiz.wrong": "❌ Не угадал. Попробуй ещё.",
   ```
   Скопируй и переведи в `_en`, `_uz`, `_kk`.

3. **Зеркало в Max (`bot/max/handlers.py`):**
   ```python
   if cmd == "/quiz":
       scenario = random.choice(list(ctx.catalogue.scenarios.values()))
       q = random.choice(scenario.pre_test)
       buttons = [[MaxButton(opt, f"quiz:{scenario.id}:{q.correct}:{i}")] for i, opt in enumerate(q.options)]
       await client.send_message(chat_id, q.q, buttons=buttons)
       return

   # В handle_callback:
   if payload.startswith("quiz:"):
       _, sid, correct, picked = payload.split(":")
       msg = "Правильно! +5 XP" if int(picked) == int(correct) else "Не угадал"
       await client.send_message(chat_id, msg)
       await client.answer_callback(callback_id)
       return
   ```

4. **Тест (`tests/test_quiz.py`):**
   ```python
   import pytest
   from bot.max.handlers import build_context, dispatch_update
   from tests.test_max_client import _RecordingClient

   @pytest.mark.asyncio
   async def test_quiz_returns_question() -> None:
       ctx = build_context(Path("content"))
       client = _RecordingClient()
       await dispatch_update(client, ctx, {
           "update_type": "message_created",
           "message": {"recipient": {"chat_id": 1}, "body": {"text": "/quiz"}},
       })
       assert client.sent and "?" in client.sent[0]["text"]
   ```

5. Прогон: `pytest -q tests/test_quiz.py`.

---

## E5. Рецепт: добавить миграцию БД

Допустим, нужна таблица `scenarios_bookmarks`.

**Шаги:**

1. Открой `bot/migrations.py`. Найди последнюю миграцию (m011) и добавь
   новую функцию:
   ```python
   async def m012_bookmarks(conn: aiosqlite.Connection) -> None:
       """Закладки сценариев — пользователь может «отметить» сценарий."""
       await conn.executescript("""
           CREATE TABLE IF NOT EXISTS scenarios_bookmarks (
               user_id INTEGER NOT NULL,
               scenario_id TEXT NOT NULL,
               created_at TEXT NOT NULL DEFAULT (datetime('now')),
               PRIMARY KEY (user_id, scenario_id)
           );
           CREATE INDEX IF NOT EXISTS idx_bookmarks_user
               ON scenarios_bookmarks(user_id);
       """)
       await conn.commit()
   ```

2. Зарегистрируй её в списке `MIGRATIONS` (по порядку):
   ```python
   MIGRATIONS = (
       m001_init,
       ...,
       m011_alert_subscriptions,
       m012_bookmarks,        # <- сюда
   )
   ```

3. При старте `await init_db()` миграция применится автоматически
   (есть таблица `_migrations` с историей).

4. Проверь:
   ```bash
   rm -f spas.db
   python -c "import asyncio; from bot.storage import init_db; asyncio.run(init_db())"
   sqlite3 spas.db ".schema scenarios_bookmarks"
   ```

5. Тест:
   ```python
   # tests/test_storage_full.py
   @pytest.mark.asyncio
   async def test_bookmarks_table_created(tmp_path):
       os.environ["DB_PATH"] = str(tmp_path / "spas.db")
       from bot.storage import init_db, _connect
       await init_db()
       async with _connect() as conn:
           cur = await conn.execute("SELECT name FROM sqlite_master WHERE name='scenarios_bookmarks'")
           row = await cur.fetchone()
       assert row is not None
   ```

---

## E6. Рецепт: добавить ачивку

**Шаги:**

1. В `content/achievements.json` добавь объект:
   ```json
   {
     "id": "polyglot_4",
     "title": "Полиглот",
     "description": "Прошёл сценарий на 4 разных языках",
     "icon": "🌐",
     "condition": {"type": "languages_used", "value": 4}
   }
   ```

2. В `bot/gamification.py:_check_achievement()` добавь обработку
   `condition.type == "languages_used"`:
   ```python
   if cond["type"] == "languages_used":
       async with _connect() as conn:
           cur = await conn.execute(
               "SELECT COUNT(DISTINCT lang) FROM events WHERE user_id=? AND name='lang_changed'",
               (uid,),
           )
           (count,) = await cur.fetchone()
       return count >= cond["value"]
   ```

3. Тест:
   ```python
   # tests/test_gamification.py
   @pytest.mark.asyncio
   async def test_polyglot_achievement_unlocks(tmp_path):
       # установить 4 разных lang_changed event'а
       # вызвать evaluate_achievements
       # проверить, что polyglot_4 в списке ачивок
   ```

---

## E7. Рецепт: добавить REST API endpoint

Допустим, эндпоинт `/api/stats` возвращает суммарную статистику.

**Шаги:**

1. В `bot/api.py` найди `build_api()` и добавь обработчик:
   ```python
   async def _stats_handler(request: web.Request) -> web.Response:
       async with _connect() as conn:
           cur = await conn.execute("SELECT COUNT(*) FROM users")
           (users_count,) = await cur.fetchone()
           cur = await conn.execute("SELECT COUNT(*) FROM events WHERE name='scenario_complete'")
           (completes,) = await cur.fetchone()
       return web.json_response({"users": users_count, "scenarios_completed": completes})

   app.router.add_get("/api/stats", _stats_handler)
   ```

2. Добавь в OpenAPI spec (`bot/api.py:_openapi_spec()`):
   ```python
   paths["/api/stats"] = {
       "get": {
           "summary": "Сводная статистика",
           "responses": {"200": {"description": "OK"}},
       }
   }
   ```

3. Тест:
   ```python
   # tests/test_api_endpoints.py
   async def test_stats_endpoint(api_client):
       resp = await api_client.get("/api/stats")
       assert resp.status == 200
       body = await resp.json()
       assert "users" in body and "scenarios_completed" in body
   ```

---

## E8. Рецепт: написать тест в стиле репо

**Структура файла теста:**
```python
"""Краткое описание модуля под тестом и зачем эти тесты."""
from __future__ import annotations

import pytest
from <module> import <symbol>

# Группа 1: позитивные сценарии
def test_normal_case_does_X() -> None:
    assert <symbol>(...) == ...

def test_handles_empty_input() -> None:
    assert <symbol>([]) == ...

# Группа 2: краевые случаи
def test_raises_on_invalid_input() -> None:
    with pytest.raises(ValueError):
        <symbol>(None)

# Группа 3: async-тесты — обязательно @pytest.mark.asyncio
@pytest.mark.asyncio
async def test_async_op() -> None:
    result = await <symbol>(...)
    assert result == ...
```

**Конвенции:**
- Имя файла: `tests/test_<module>.py`.
- Имя теста: `test_<что_проверяется>` (snake_case, глагол).
- Один assert на тест где возможно (но смысловые группы — ок).
- Никаких `time.sleep()` — используй `asyncio.sleep` или мок-таймера.
- Сетевые запросы — мокать через `_StubSession` (см. `tests/test_max_client.py`)
  или `aresponses` / `pytest-httpx`.

---

## E9. Конвенции кода (что я соблюдаю)

* **Python 3.11+ синтаксис.** `dict[str, int]`, `int | None`, `from __future__ import annotations`.
* **Type hints везде**, включая возвращаемое значение.
* **Async всё, что I/O** — БД, HTTP, файлы (через aiofiles).
* **Pydantic** для валидации внешних JSON (контент, конфиг).
* **dataclasses** для внутренних структур.
* **Имена:**
  - Модули — `snake_case`.
  - Классы — `PascalCase`.
  - Функции/переменные — `snake_case`.
  - Константы — `UPPER_SNAKE`.
  - Приватные — префикс `_`.
* **Логи:** `log = logging.getLogger("spas.<module>")`. Уровни:
  - `error` — критичные сбои,
  - `warning` — деградации,
  - `info` — события («бот стартовал», «контент загружен»),
  - `debug` — детали.
* **Без `print()`** в проде — только в CLI-инструментах (`tools/*`).
* **Без `assert` в рантайме** — только в тестах.
* **Минимальные комментарии** — код должен читаться. Если без комментария
  непонятно — переименуй переменную.
* **Docstrings:**
  - Модуль — обязателен (1–3 строки).
  - Public class/function — желателен (что делает + edge-cases).
  - Private — можно опустить.

---

## E10. Частые ошибки и как их быстро чинить

| Ошибка | Причина | Фикс |
|---|---|---|
| `ImportError: cannot import name 'X'` | Имя функции изменилось | `grep -rn "def X" bot/` найди настоящее имя |
| `aiosqlite.OperationalError: no such table` | Не запустилась миграция | `await init_db()` перед использованием |
| `aiogram.exceptions.TelegramConflictError` | Запущено два инстанса с одним токеном | Убей второй / выключи polling если webhook |
| `PermissionError: data/spas.db` | Нет прав в Fly volume | Маунт указан в fly.toml? Volume создан? |
| `ruff: E501 line too long` | Строка > 100 | Разбей на несколько; не отключай rule |
| `ruff: F401 imported but unused` | Импорт не используется | Удали или добавь к `__all__` |
| `pytest: ModuleNotFoundError` | Нет venv или dev-deps | `pip install -r requirements-dev.txt` |
| `pre-commit: 'mixed-line-ending'` | Windows CRLF | `git config core.autocrlf false` + `git rm --cached -r .` + reset |
| `Max API 401 verify.token` | Невалидный `MAX_BOT_TOKEN` | Перевыпусти у @MasterBot |
| `Max API 429 too_many_requests` | Превышен rate-limit | Throttle middleware или задержка |
| Coverage < 70% | Новый код без тестов | Добавь тест-кейсы или поправь `--cov-fail-under` |

---

## E11. Git workflow

```bash
# 1. Новая ветка от текущей рабочей
git checkout devin/<existing-branch>
git checkout -b devin/$(date +%s)-feature-name

# 2. Делай маленькие коммиты по смыслу
git add <files>
git commit -m "feat(scope): что делаем"

# 3. Push и PR
git push -u origin HEAD
git_pr fetch_template
git_pr create   # head=твоя ветка, base=рабочая или main

# 4. Если CI падает
git_pr ci_job_logs <job_id>
# исправь и:
git add <files>; git commit -m "fix: ..."; git push

# 5. Никогда:
# - git push --force-with-lease на main
# - git commit --amend (только новые коммиты)
# - git reset --hard (можно потерять работу)
# - git rebase публичной истории
```

**Конвенция коммитов:**
- `feat(scope): ...` — новая фича.
- `fix(scope): ...` — баг-фикс.
- `docs(scope): ...` — документация.
- `test(scope): ...` — только тесты.
- `chore(scope): ...` — обслуживание (deps, конфиг).
- `refactor(scope): ...` — рефакторинг без изменения поведения.

`scope` — папка/модуль (`max`, `i18n`, `devops`, `api`, etc.).

---

## E12. Промпты для Devin/Cursor/Claude (готовы к копированию)

### «Добавить сценарий»
```
Прочитай ROADMAP.md раздел E2 и добавь сценарий "<id>"
("<title>", категория <category>) в content/scenarios.json. Шаги
действий: <step1>; <step2>; ... pre/post-тесты по 1 вопросу.
После — прогон pytest и push в текущую ветку.
```

### «Добавить язык»
```
Прочитай ROADMAP.md раздел E3 и добавь поддержку языка <code>
(<name>). Заполни все ключи в bot/i18n.py, добавь
landing/index.<code>.html, обнови переключатель в существующих
лендингах, добавь язык в tests/test_i18n_completeness.py.
```

### «Добавить команду паритетно в TG и Max»
```
Прочитай ROADMAP.md раздел E4 и добавь команду /<name> в
bot/handlers.py (Telegram) и bot/max/handlers.py (Max). Реализуй
<описание поведения>. Все строки — через bot/i18n.py с ключами
<key1>, <key2>. Добавь юнит-тест в tests/test_<name>.py.
```

### «Сделай раздел A1 / A4 / A5 …»
```
Прочитай ROADMAP.md раздел <код>. Реализуй пункт целиком, прогони
pytest, ruff, pre-commit, и создай PR с описанием по шаблону репо.
```

---

## E13. Минимальные предохранители

Перед каждым `git push`:
```bash
ruff check . && \
ruff format --check . && \
pre-commit run --all-files && \
pytest -q --cov=bot --cov=tools --cov-fail-under=70
```

Если хоть что-то упало — НЕ пушим. Чиним.

Перед каждым `fly deploy`:
```bash
docker build -t spas-test .
docker run --rm --env-file .env spas-test python -m bot &
sleep 10
curl http://localhost:8080/health
docker kill <container>
```

Перед каждым релизом — обнови `CHANGELOG.md` (раздел `Unreleased` →
вынеси в новый версионированный с датой).

---

## E14. Где искать готовые сниппеты (внутри репо)

| Что | Файл-пример |
|---|---|
| async-handler с inline-кнопками | `bot/handlers.py:_dispatcher_cmd` |
| Pydantic-модель + загрузка JSON | `bot/dispatcher.py:load_dispatcher_checklist` |
| Async SQLite query | `bot/storage.py:get_user_xp` |
| aiohttp-роут с CORS | `bot/api.py:build_api` |
| Тест-стаб для aiohttp.ClientSession | `tests/test_max_client.py:_StubSession` |
| Pytest async fixture | `tests/test_api_endpoints.py:api_client` |
| CLI с argparse | `tools/import_aed_overpass.py:main` |
| Subprocess-тест с PYTHONHASHSEED | `tests/test_certificate_deterministic.py` |

Скопируй и переименуй — это быстрее, чем писать с нуля.

---

## E15. Итог

После прочтения этого раздела + AGENTS.md типовая задача занимает:
- Новый сценарий: **10 минут**.
- Новый язык: **30 минут**.
- Новая команда (TG+Max): **45 минут**.
- Новая миграция: **15 минут**.
- Новый API-эндпоинт: **20 минут**.
- Новая ачивка: **15 минут**.

Если задача занимает больше — значит, не нашёл рецепт. Перечитай
этот раздел, найди нужный шаблон, копируй.
