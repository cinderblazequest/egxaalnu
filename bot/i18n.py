"""i18n: словарь строк по локалям ru/en/uz/kk.

Используется в новых командах (профиль, sos, lang, teacher, accessibility,
consent, alerts, admin, forget_me). Базовые сценарии и пункты меню
живут в ``handlers.py`` и пока остаются на русском — интерфейс многоязычный
там, где это влияет на пользовательский опыт.
"""

from __future__ import annotations

SUPPORTED = ("ru", "en", "uz", "kk")
DEFAULT = "ru"

# Aliases the bot accepts for /lang (kk also covers "kz").
_ALIASES = {"kz": "kk"}


def normalize_lang(code: str | None) -> str:
    if not code:
        return DEFAULT
    code = code.strip().lower()
    # Accept BCP-47 tags like "en-US": only the primary subtag matters.
    if "-" in code:
        code = code.split("-", 1)[0]
    if "_" in code:
        code = code.split("_", 1)[0]
    code = _ALIASES.get(code, code)
    return code if code in SUPPORTED else DEFAULT


_STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        # core
        "lang.changed": "Язык интерфейса: русский.",
        "lang.choose": "Выбери язык / Choose language / Tilni tanlang / Тілді таңдаңыз:",
        # profile
        "profile.title": "🎓 Твой профиль СПАС",
        "profile.level": "Уровень",
        "profile.xp": "XP",
        "profile.streak": "Серия дней",
        "profile.empty": "Ачивки появятся, как только пройдёшь сценарии.",
        # sharing
        "share.title": "📣 Поделиться прогрессом",
        # SOS
        "sos.no_contact": (
            "Доверенный контакт не задан. Сначала пришли /setup_sos — это можно "
            "сделать один раз, и потом /sos_share будет отправлять им твою "
            "геолокацию автоматически."
        ),
        "sos.set_ok": "Готово! Доверенный контакт сохранён: {name}",
        "sos.cleared": "Доверенный контакт удалён.",
        "sos.share_intro": "Жми «отправить геолокацию» — я перешлю её доверенному контакту.",
        # accessibility
        "a11y.on": (
            "♿ Режим доступности включён: бот будет писать без эмодзи и "
            "форматирования. /accessibility — выключить."
        ),
        "a11y.off": "♿ Режим доступности выключен.",
        # teacher
        "teacher.intro": (
            "👩‍🏫 <b>Режим учителя.</b>\n\n"
            "Создай класс — получишь invite-код, раздашь его ученикам, "
            "и в /teacher_dashboard увидишь, кто что прошёл "
            "(анонимно по никам)."
        ),
        "teacher.ask_name": "Как назовём класс? Пришли одно сообщение, например <i>9-А Лицей №1</i>.",
        "teacher.created": (
            "📋 Класс создан: <b>{name}</b>\n"
            "Код: <code>{code}</code>\n\n"
            "Раздай код ученикам — они откроют бота и пришлют:\n"
            "<code>/join {code}</code>"
        ),
        "teacher.no_classes": "У тебя пока нет классов. Создай первый — /teacher.",
        "join.ask_nickname": (
            "Как тебя записать в классе (ник)? Пришли одно сообщение, "
            "до 40 символов. Учитель увидит только этот ник."
        ),
        "join.bad_code": "Не нашёл такой код. Уточни у учителя.",
        "join.ok": (
            "✅ Готово, ты в классе <b>{class_name}</b> как «<b>{nickname}</b>».\n"
            "Учитель будет видеть твой прогресс по этому нику."
        ),
        "join.already": "Ты уже в этом классе.",
        # 152-ФЗ consent
        "consent.intro": (
            "🛡️ <b>Согласие на обработку персональных данных</b>\n\n"
            "Чтобы продолжить пользоваться ботом СПАС, нужно согласие "
            "на обработку персональных данных по 152-ФЗ.\n\n"
            "Что мы храним: твой Telegram user_id, выбранный язык, прогресс по "
            "сценариям и анонимные события (без сообщений). "
            "Подробнее: /privacy.\n\n"
            "Отозвать согласие и удалить данные можно в любой момент: /forget_me."
        ),
        "consent.btn_accept": "✅ Согласен, продолжить",
        "consent.btn_decline": "❌ Не согласен",
        "consent.btn_privacy": "📄 Открыть политику",
        "consent.accepted": "Спасибо! Согласие зафиксировано. Жми /start ещё раз — и поехали.",
        "consent.declined": (
            "Без согласия бот пользоваться не может (требование 152-ФЗ). "
            "Если передумаешь — напиши /start и согласись."
        ),
        "consent.required": "Сначала прими согласие на обработку ПДн: /start",
        "consent.privacy": (
            "📄 <b>Политика обработки данных (короткая версия).</b>\n\n"
            "• Мы храним только твой Telegram user_id, язык и обезличенные "
            "события сценариев и тестов.\n"
            "• Мы НЕ читаем твои переписки, фото, контакты.\n"
            "• Данные хранятся на серверах в РФ, доступ только разработчику.\n"
            "• Срок хранения — до отзыва согласия (/forget_me).\n"
            "• Полный текст: docs/governance_152fz.md в репозитории.\n\n"
            "Назад: /start. Удалить мои данные: /forget_me."
        ),
        # /forget_me
        "forget.confirm": (
            "⚠️ <b>Удаление всех твоих данных.</b>\n\n"
            "Будут безвозвратно удалены: профиль, XP, ачивки, прогресс, "
            "сертификаты, доверенные контакты, подписки на алерты.\n\n"
            "Точно? Это нельзя отменить."
        ),
        "forget.btn_yes": "🗑️ Да, удалить всё",
        "forget.btn_no": "« Отмена",
        "forget.done": ("✅ Все твои данные удалены. Бот тебя больше не помнит. " "Спасибо, что был с нами."),
        "forget.cancelled": "Хорошо, ничего не удалили.",
        # МЧС alerts
        "alerts.subscribed": "🔔 Подписка на алерты МЧС включена для региона: <b>{region}</b>.",
        "alerts.unsubscribed": "🔕 Подписка на алерты МЧС отключена.",
        "alerts.list_empty": "У тебя нет активных подписок на алерты.",
        "alerts.list_title": "🔔 Твои подписки на алерты МЧС:",
        "alerts.usage": (
            "Использование:\n"
            "/subscribe_alerts <i>регион</i> — подписаться (пример: <code>/subscribe_alerts moscow</code>)\n"
            "/unsubscribe_alerts — отписаться от всех\n"
            "/my_alerts — посмотреть свои подписки"
        ),
        # vision (C2)
        "vision.processing": "🔍 Анализирую фото… это займёт пару секунд.",
        "vision.disclaimer": ("<i>⚠️ Это не диагноз. Если есть угроза жизни — звони 112 и открой /sos.</i>"),
        "vision.disabled": (
            "📷 Распознавание фото пока выключено (нет ключа GigaChat). "
            "Опиши ситуацию текстом — я подскажу сценарий."
        ),
        "vision.error": ("Не получилось распознать фото. Попробуй ещё раз или опиши текстом."),
        "vision.too_many": "Лимит фото-запросов исчерпан, попробуй через час.",
    },
    "en": {
        "lang.changed": "Interface language: English.",
        "lang.choose": "Choose language / Выбери язык / Tilni tanlang / Тілді таңдаңыз:",
        "profile.title": "🎓 Your СПАС profile",
        "profile.level": "Level",
        "profile.xp": "XP",
        "profile.streak": "Day streak",
        "profile.empty": "Earn achievements by completing scenarios.",
        "share.title": "📣 Share your progress",
        "sos.no_contact": (
            "Trusted contact is not set. Run /setup_sos first — it's a one-time setup, "
            "and after that /sos_share will forward your geolocation automatically."
        ),
        "sos.set_ok": "Done! Trusted contact saved: {name}",
        "sos.cleared": "Trusted contact removed.",
        "sos.share_intro": "Tap 'Send location' — I'll forward it to your trusted contact.",
        "a11y.on": (
            "♿ Accessibility mode on: the bot will write without emoji or "
            "formatting. /accessibility — turn off."
        ),
        "a11y.off": "♿ Accessibility mode off.",
        "teacher.intro": (
            "👩‍🏫 <b>Teacher mode.</b>\n\n"
            "Create a class — get an invite code, share it with students, "
            "and /teacher_dashboard will show their anonymized progress."
        ),
        "teacher.ask_name": "What's the class name? Send a single message, e.g. <i>Year 9 Lyceum 1</i>.",
        "teacher.created": (
            "📋 Class created: <b>{name}</b>\n"
            "Code: <code>{code}</code>\n\n"
            "Share the code with students — they open the bot and send:\n"
            "<code>/join {code}</code>"
        ),
        "teacher.no_classes": "No classes yet. Create one — /teacher.",
        "join.ask_nickname": "Pick a nickname (max 40 chars). The teacher sees only this nickname.",
        "join.bad_code": "Code not found. Ask your teacher.",
        "join.ok": (
            "✅ You joined <b>{class_name}</b> as «<b>{nickname}</b>».\n"
            "The teacher will see your progress under this nickname."
        ),
        "join.already": "You're already in this class.",
        "consent.intro": (
            "🛡️ <b>Personal data processing consent</b>\n\n"
            "To use the СПАС bot we need your consent under Russian Federal "
            "Law #152-FZ.\n\n"
            "What we store: your Telegram user_id, chosen language, scenario "
            "progress and anonymized events (no message bodies). More: /privacy.\n\n"
            "You can withdraw consent and delete all data at any time: /forget_me."
        ),
        "consent.btn_accept": "✅ I agree, continue",
        "consent.btn_decline": "❌ Decline",
        "consent.btn_privacy": "📄 Privacy policy",
        "consent.accepted": "Thank you! Consent recorded. Send /start again — let's go.",
        "consent.declined": (
            "Without consent the bot cannot work (152-FZ requirement). "
            "When you change your mind, send /start."
        ),
        "consent.required": "Accept the personal data consent first: /start",
        "consent.privacy": (
            "📄 <b>Privacy policy (short).</b>\n\n"
            "• We store only your Telegram user_id, language and anonymized "
            "events for scenarios and tests.\n"
            "• We do NOT read your chats, photos, contacts.\n"
            "• Data is hosted in Russia; access limited to the developer.\n"
            "• Retention — until you revoke consent (/forget_me).\n"
            "• Full text: docs/governance_152fz.md in the repo.\n\n"
            "Back: /start. Delete my data: /forget_me."
        ),
        "forget.confirm": (
            "⚠️ <b>Delete all your data.</b>\n\n"
            "We will permanently remove your profile, XP, achievements, progress, "
            "certificates, trusted contact and alert subscriptions.\n\n"
            "Sure? This cannot be undone."
        ),
        "forget.btn_yes": "🗑️ Yes, delete everything",
        "forget.btn_no": "« Cancel",
        "forget.done": ("✅ All your data is deleted. The bot no longer remembers you. " "Take care."),
        "forget.cancelled": "OK, nothing was deleted.",
        "alerts.subscribed": "🔔 Alert subscriptions enabled for region: <b>{region}</b>.",
        "alerts.unsubscribed": "🔕 Alert subscriptions disabled.",
        "alerts.list_empty": "You have no active alert subscriptions.",
        "alerts.list_title": "🔔 Your EMERCOM alert subscriptions:",
        "alerts.usage": (
            "Usage:\n"
            "/subscribe_alerts <i>region</i> — subscribe (example: <code>/subscribe_alerts moscow</code>)\n"
            "/unsubscribe_alerts — unsubscribe from all\n"
            "/my_alerts — see your subscriptions"
        ),
        "vision.processing": "🔍 Analysing the photo… one moment.",
        "vision.disclaimer": (
            "<i>⚠️ This is not a diagnosis. If life is at risk — call 112 and open /sos.</i>"
        ),
        "vision.disabled": (
            "📷 Photo recognition is off (no GigaChat key). "
            "Describe what you see in text and I'll suggest a scenario."
        ),
        "vision.error": "Couldn't recognise the photo. Try again or describe in text.",
        "vision.too_many": "Photo-request quota reached, try in an hour.",
    },
    "uz": {
        "lang.changed": "Interfeys tili: o'zbekcha.",
        "lang.choose": "Tilni tanlang / Choose language / Выбери язык / Тілді таңдаңыз:",
        "profile.title": "🎓 СПАС profil",
        "profile.level": "Daraja",
        "profile.xp": "XP",
        "profile.streak": "Kun davomida ketma-ket",
        "profile.empty": "Stsenariylarni bajaring — yutuq belgilari paydo bo'ladi.",
        "share.title": "📣 Yutuqlarim bilan o'rtoqlashish",
        "sos.no_contact": (
            "Ishonchli kontakt belgilanmagan. Avval /setup_sos buyrug'ini yuboring — "
            "bir martalik sozlama, keyin /sos_share avtomatik joylashuv jo'natadi."
        ),
        "sos.set_ok": "Tayyor! Ishonchli kontakt saqlandi: {name}",
        "sos.cleared": "Ishonchli kontakt o'chirildi.",
        "sos.share_intro": "«Joylashuvni yuborish» tugmasini bosing — kontaktga jo'nataman.",
        "a11y.on": (
            "♿ Imkoniyatlari cheklangan rejim yoqildi: emoji va belgilar siz, "
            "matn katta. /accessibility — o'chirish."
        ),
        "a11y.off": "♿ Imkoniyatlari cheklangan rejim o'chirildi.",
        "teacher.intro": (
            "👩‍🏫 <b>O'qituvchi rejimi.</b>\n\n"
            "Sinf yarating — taklif kodi olasiz, talabalarga tarqating, "
            "/teacher_dashboard'da kim nimani bajarganini ko'rasiz (laqab bo'yicha)."
        ),
        "teacher.ask_name": "Sinf nomi qanday? Bitta xabar yuboring, masalan <i>9-A litsey 1</i>.",
        "teacher.created": (
            "📋 Sinf yaratildi: <b>{name}</b>\n"
            "Kod: <code>{code}</code>\n\n"
            "Talabalarga kodni bering — botni ochib jo'natsinlar:\n"
            "<code>/join {code}</code>"
        ),
        "teacher.no_classes": "Sinflar yo'q. /teacher orqali yarating.",
        "join.ask_nickname": "Laqab tanlang (40 belgi). O'qituvchi shu laqabni ko'radi.",
        "join.bad_code": "Bunday kod topilmadi. O'qituvchidan so'rang.",
        "join.ok": (
            "✅ Tayyor, siz <b>{class_name}</b> sinfidasiz, laqab «<b>{nickname}</b>».\n"
            "O'qituvchi shu laqab ostida progressingizni ko'radi."
        ),
        "join.already": "Siz allaqachon bu sinfdasiz.",
        "consent.intro": (
            "🛡️ <b>Shaxsiy ma'lumotlarni qayta ishlashga rozilik</b>\n\n"
            "СПАС botidan foydalanish uchun Rossiya 152-FZ bo'yicha rozilik kerak.\n\n"
            "Saqlanadi: Telegram user_id, til, stsenariy progressi, anonim hodisalar. "
            "Batafsil: /privacy. Rozilikni qaytarib olish: /forget_me."
        ),
        "consent.btn_accept": "✅ Roziman",
        "consent.btn_decline": "❌ Rozi emasman",
        "consent.btn_privacy": "📄 Maxfiylik siyosati",
        "consent.accepted": "Rahmat! Rozilik yozib olindi. /start ni yana yuboring.",
        "consent.declined": "Rozilik bo'lmasa bot ishlamaydi. Fikringiz o'zgarsa, /start yuboring.",
        "consent.required": "Avval shaxsiy ma'lumot rozilikni qabul qiling: /start",
        "consent.privacy": (
            "📄 <b>Maxfiylik siyosati (qisqacha).</b>\n\n"
            "• Faqat user_id, til va anonim hodisalar saqlanadi.\n"
            "• Suhbat, rasm, kontaktlar O'QILMAYDI.\n"
            "• Server Rossiyada, faqat ishlab chiquvchi kira oladi.\n"
            "• Rozilikni /forget_me bilan bekor qilish mumkin."
        ),
        "forget.confirm": (
            "⚠️ <b>Hamma ma'lumotlaringizni o'chirish.</b>\n\n"
            "Profil, XP, yutuqlar, progress, sertifikatlar, kontakt, obunalar - hammasi.\n\n"
            "Aniqmi? Qaytarib bo'lmaydi."
        ),
        "forget.btn_yes": "🗑️ Ha, hammasini o'chir",
        "forget.btn_no": "« Bekor qilish",
        "forget.done": "✅ Hamma ma'lumot o'chirildi. Bot endi sizni eslamaydi.",
        "forget.cancelled": "Yaxshi, hech narsa o'chirilmadi.",
        "alerts.subscribed": "🔔 Hudud bo'yicha ogohlantirishlar yoqildi: <b>{region}</b>.",
        "alerts.unsubscribed": "🔕 Ogohlantirishlar o'chirildi.",
        "alerts.list_empty": "Hech qanday faol obuna yo'q.",
        "alerts.list_title": "🔔 Sizning obunalaringiz:",
        "alerts.usage": (
            "Foydalanish:\n"
            "/subscribe_alerts <i>hudud</i> — obuna bo'lish\n"
            "/unsubscribe_alerts — obunani bekor qilish\n"
            "/my_alerts — obunalar ro'yxati"
        ),
        "vision.processing": "🔍 Rasmni tahlil qilyapman… bir soniya.",
        "vision.disclaimer": "<i>⚠️ Bu tashxis emas. Hayot xavfi bo'lsa — 112 ga qo'ng'iroq qiling.</i>",
        "vision.disabled": "📷 Rasm tanish o'chirilgan. Matnda yozing — stsenariy taklif qilaman.",
        "vision.error": "Rasmni tanib olmadim. Yana urinib ko'ring yoki matnda yozing.",
        "vision.too_many": "Rasm so'rovlari chegarasi tugadi, bir soatdan keyin urinib ko'ring.",
    },
    "kk": {
        "lang.changed": "Интерфейс тілі: қазақша.",
        "lang.choose": "Тілді таңдаңыз / Choose language / Выбери язык / Tilni tanlang:",
        "profile.title": "🎓 СПАС профилің",
        "profile.level": "Деңгей",
        "profile.xp": "XP",
        "profile.streak": "Қатарынан күн",
        "profile.empty": "Сценарийлерді өткен соң жетістіктер пайда болады.",
        "share.title": "📣 Прогреспен бөлісу",
        "sos.no_contact": (
            "Сенімді контакт орнатылмаған. Алдымен /setup_sos жіберіңіз — "
            "бір рет жасайсыз, кейін /sos_share геолокацияны автоматты түрде жібереді."
        ),
        "sos.set_ok": "Дайын! Сенімді контакт сақталды: {name}",
        "sos.cleared": "Сенімді контакт өшірілді.",
        "sos.share_intro": "«Геолокация жіберу» батырмасын басыңыз — мен контактқа жолдаймын.",
        "a11y.on": "♿ Қолжетімділік режимі қосылды (эмодзисіз, ірі мәтін).",
        "a11y.off": "♿ Қолжетімділік режимі өшірілді.",
        "teacher.intro": (
            "👩‍🏫 <b>Мұғалім режимі.</b>\n\n"
            "Сынып жасаңыз — шақыру коды беріледі, оқушыларға таратасыз, "
            "/teacher_dashboard ішінде кімнің не өткенін ник бойынша көресіз."
        ),
        "teacher.ask_name": "Сыныптың аты қандай? Бір хабарлама жіберіңіз, мысалы <i>9-А лицей 1</i>.",
        "teacher.created": (
            "📋 Сынып жасалды: <b>{name}</b>\n"
            "Код: <code>{code}</code>\n\n"
            "Кодты оқушыларға беріңіз — олар ботты ашып жіберсін:\n"
            "<code>/join {code}</code>"
        ),
        "teacher.no_classes": "Сізде сынып жоқ. /teacher арқылы жасаңыз.",
        "join.ask_nickname": "Ник таңдаңыз (40 таңбаға дейін). Мұғалім тек осы никті көреді.",
        "join.bad_code": "Бұндай код табылмады. Мұғалімнен сұраңыз.",
        "join.ok": (
            "✅ Дайын, сіз <b>{class_name}</b> сыныбындасыз, ник «<b>{nickname}</b>».\n"
            "Мұғалім осы ник арқылы прогресіңізді көреді."
        ),
        "join.already": "Сіз бұл сыныптасыз.",
        "consent.intro": (
            "🛡️ <b>Жеке деректерді өңдеуге келісім</b>\n\n"
            "СПАС ботын пайдалану үшін Ресейдің 152-FZ заңы бойынша келісім қажет.\n\n"
            "Сақталады: Telegram user_id, тіл, сценарий прогресі, анонимдік оқиғалар. "
            "Толығырақ: /privacy. Келісімді қайтарып алу: /forget_me."
        ),
        "consent.btn_accept": "✅ Келісемін",
        "consent.btn_decline": "❌ Келіспеймін",
        "consent.btn_privacy": "📄 Құпиялылық",
        "consent.accepted": "Рақмет! Келісім тіркелді. /start қайта жіберіңіз.",
        "consent.declined": "Келісімсіз бот жұмыс істемейді. Ойыңыз өзгерсе, /start жіберіңіз.",
        "consent.required": "Алдымен жеке деректерге келісім беріңіз: /start",
        "consent.privacy": (
            "📄 <b>Құпиялылық саясаты (қысқа).</b>\n\n"
            "• Тек user_id, тіл, анонимдік оқиғалар сақталады.\n"
            "• Хат-хабарларыңыз, фото, контакттар оқылмайды.\n"
            "• Сервер Ресейде, кіру тек әзірлеушіге.\n"
            "• Келісімді /forget_me арқылы кері қайтаруға болады."
        ),
        "forget.confirm": (
            "⚠️ <b>Барлық деректеріңізді өшіру.</b>\n\n"
            "Профиль, XP, жетістіктер, прогресс, сертификаттар, контакт, жазылулар "
            "толығымен өшіріледі.\n\nШын ба? Қайтаруға болмайды."
        ),
        "forget.btn_yes": "🗑️ Иә, бәрін өшір",
        "forget.btn_no": "« Болдырмау",
        "forget.done": "✅ Барлық деректер өшірілді. Бот сізді есінде сақтамайды.",
        "forget.cancelled": "Жарайды, ештеңе өшірілмеді.",
        "alerts.subscribed": "🔔 Аумақ бойынша хабарландыру жазылымы қосылды: <b>{region}</b>.",
        "alerts.unsubscribed": "🔕 Хабарландыру жазылымы өшірілді.",
        "alerts.list_empty": "Белсенді жазылымдар жоқ.",
        "alerts.list_title": "🔔 Сіздің жазылымдарыңыз:",
        "alerts.usage": (
            "Қолданыс:\n"
            "/subscribe_alerts <i>аумақ</i> — жазылу\n"
            "/unsubscribe_alerts — бас тарту\n"
            "/my_alerts — жазылымдар тізімі"
        ),
        "vision.processing": "🔍 Фотоны талдап жатырмын… бір сәт.",
        "vision.disclaimer": "<i>⚠️ Бұл диагноз емес. Өмірге қауіп болса — 112-ге қоңырау шалыңыз.</i>",
        "vision.disabled": "📷 Фотоны тану өшірілген. Мәтінмен жазыңыз — сценарий ұсынамын.",
        "vision.error": "Фотоны танымадым. Қайта жіберіңіз немесе мәтінмен жазыңыз.",
        "vision.too_many": "Фото-сұраулар лимиті бітті, бір сағаттан соң қайта жіберіңіз.",
    },
}


def t(key: str, lang: str = DEFAULT, **fmt: object) -> str:
    """Lookup ``key`` in language ``lang``; falls back to default and to key itself."""
    lang = normalize_lang(lang)
    table = _STRINGS.get(lang) or _STRINGS[DEFAULT]
    raw = table.get(key) or _STRINGS[DEFAULT].get(key) or key
    if fmt:
        try:
            return raw.format(**fmt)
        except (KeyError, IndexError):
            return raw
    return raw
