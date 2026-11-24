"""Bot matnlari: o'zbek, rus, ingliz. HTML formatida.

Foydalanish: t(lang, "START", name="Ali")
"""
from __future__ import annotations

LANGS = {"uz": "🇺🇿 O'zbekcha", "ru": "🇷🇺 Русский", "en": "🇬🇧 English"}
DEFAULT_LANG = "uz"

_T: dict[str, dict[str, str]] = {
    # ---------------- asosiy ----------------
    "CHOOSE_LANG": {
        "uz": "🌐 Tilni tanlang",
        "ru": "🌐 Выберите язык",
        "en": "🌐 Choose your language",
    },
    "LANG_SET": {
        "uz": "✅ Til: O'zbekcha",
        "ru": "✅ Язык: Русский",
        "en": "✅ Language: English",
    },
    "START": {
        "uz": "👋 Salom{name}!\n\n"
              "Havola yuboring — video, rasm yoki musiqani <b>suv belgisiz</b> yuklab beraman.\n\n"
              "<i>Instagram · TikTok · YouTube · Facebook · X · Pinterest va boshqalar</i>",
        "ru": "👋 Привет{name}!\n\n"
              "Отправьте ссылку — скачаю видео, фото или музыку <b>без водяного знака</b>.\n\n"
              "<i>Instagram · TikTok · YouTube · Facebook · X · Pinterest и другие</i>",
        "en": "👋 Hi{name}!\n\n"
              "Send me a link — I'll download the video, photo or music <b>without watermark</b>.\n\n"
              "<i>Instagram · TikTok · YouTube · Facebook · X · Pinterest and more</i>",
    },
    "HELP": {
        "uz": "<b>Qanday ishlatiladi</b>\n\n"
              "1. Videoning havolasini nusxalang\n"
              "2. Shu yerga yuboring\n"
              "3. Sifatni tanlang — tayyor ✅\n\n"
              "🎵 Video ostidagi <b>MP3</b> tugmasi — audiosini olish\n"
              "👥 Guruhlarda ham ishlaydi\n\n"
              "<i>Chegara: {max_mb} MB · Til: /lang</i>",
        "ru": "<b>Как пользоваться</b>\n\n"
              "1. Скопируйте ссылку на видео\n"
              "2. Отправьте её сюда\n"
              "3. Выберите качество — готово ✅\n\n"
              "🎵 Кнопка <b>MP3</b> под видео — скачать аудио\n"
              "👥 Работает и в группах\n\n"
              "<i>Лимит: {max_mb} МБ · Язык: /lang</i>",
        "en": "<b>How to use</b>\n\n"
              "1. Copy the video link\n"
              "2. Send it here\n"
              "3. Pick the quality — done ✅\n\n"
              "🎵 The <b>MP3</b> button under a video gets its audio\n"
              "👥 Works in groups too\n\n"
              "<i>Limit: {max_mb} MB · Language: /lang</i>",
    },
    "CONTACT_LINE": {
        "uz": "\n📩 Murojaat va DMCA: {contact}",
        "ru": "\n📩 Связь и DMCA: {contact}",
        "en": "\n📩 Contact & DMCA: {contact}",
    },
    "SEND_LINK": {
        "uz": "🔗 Video yoki post havolasini yuboring.",
        "ru": "🔗 Отправьте ссылку на видео или пост.",
        "en": "🔗 Send a video or post link.",
    },
    # ---------------- menyu tugmalari ----------------
    "MENU_LANG": {"uz": "🌐 Til", "ru": "🌐 Язык", "en": "🌐 Language"},
    "MENU_HELP": {"uz": "❓ Yordam", "ru": "❓ Помощь", "en": "❓ Help"},
    "CMD_START": {"uz": "Boshlash", "ru": "Начать", "en": "Start"},
    "CMD_HELP": {"uz": "Yordam", "ru": "Помощь", "en": "Help"},
    "CMD_LANG": {"uz": "Tilni o'zgartirish", "ru": "Сменить язык", "en": "Change language"},
    "BOT_DESCRIPTION": {
        "uz": "Instagram, TikTok, YouTube va 1000+ saytdan video, rasm va musiqani suv belgisiz "
              "yuklab beraman. Havolani yuboring!",
        "ru": "Скачиваю видео, фото и музыку из Instagram, TikTok, YouTube и 1000+ сайтов без "
              "водяного знака. Просто отправьте ссылку!",
        "en": "I download videos, photos and music from Instagram, TikTok, YouTube and 1000+ "
              "sites without watermark. Just send a link!",
    },
    "BOT_SHORT": {
        "uz": "Video, rasm va musiqani suv belgisiz yuklab beraman 📥",
        "ru": "Скачиваю видео, фото и музыку без водяного знака 📥",
        "en": "Download videos, photos and music without watermark 📥",
    },
    # ---------------- yuklash ----------------
    "BTN_AUDIO": {"uz": "🎵 MP3", "ru": "🎵 MP3", "en": "🎵 MP3"},
    "LINK_EXPIRED": {
        "uz": "Havola eskirgan, qaytadan yuboring.",
        "ru": "Ссылка устарела, отправьте её снова.",
        "en": "Link expired, please send it again.",
    },
    "CHECKING": {"uz": "🔎 Tekshirilmoqda...", "ru": "🔎 Проверяю...", "en": "🔎 Checking..."},
    "CHOOSE_QUALITY": {
        "uz": "Sifatni tanlang 👇",
        "ru": "Выберите качество 👇",
        "en": "Choose quality 👇",
    },
    "QUALITY_TOO_BIG": {
        "uz": "<i>{names} — {max_mb} MB dan katta</i>",
        "ru": "<i>{names} — больше {max_mb} МБ</i>",
        "en": "<i>{names} — larger than {max_mb} MB</i>",
    },
    "QUEUED": {
        "uz": "🕒 Navbatdasiz: {pos}",
        "ru": "🕒 Вы в очереди: {pos}",
        "en": "🕒 In queue: {pos}",
    },
    "STARTING": {"uz": "⏳ Yuklanmoqda...", "ru": "⏳ Загрузка...", "en": "⏳ Downloading..."},
    "PROGRESS": {
        "uz": "⏳ Yuklanmoqda {bar} {percent}%",
        "ru": "⏳ Загрузка {bar} {percent}%",
        "en": "⏳ Downloading {bar} {percent}%",
    },
    "PROCESSING": {"uz": "⚙️ Tayyorlanmoqda...", "ru": "⚙️ Обработка...", "en": "⚙️ Processing..."},
    "UPLOADING": {"uz": "📤 Yuborilmoqda...", "ru": "📤 Отправляю...", "en": "📤 Sending..."},
    "AUDIO_PREPARING": {
        "uz": "🎵 MP3 tayyorlanmoqda...",
        "ru": "🎵 Готовлю MP3...",
        "en": "🎵 Preparing MP3...",
    },
    "TOO_MANY": {
        "uz": "✋ Oldingi yuklash tugashini kuting.",
        "ru": "✋ Дождитесь окончания предыдущей загрузки.",
        "en": "✋ Please wait for the previous download to finish.",
    },
    # ---------------- xatolar ----------------
    "ERR_PRIVATE": {
        "uz": "🔒 Bu kontent yopiq yoki login talab qiladi.",
        "ru": "🔒 Контент закрыт или требует входа в аккаунт.",
        "en": "🔒 This content is private or requires login.",
    },
    "ERR_BLOCKED": {
        "uz": "⏳ Sayt vaqtincha cheklov qo'ydi. Birozdan keyin qayta urinib ko'ring.",
        "ru": "⏳ Сайт временно ограничил доступ. Попробуйте чуть позже.",
        "en": "⏳ The site is temporarily limiting requests. Please try again a bit later.",
    },
    "ERR_NETWORK": {
        "uz": "🌐 Serverda tarmoq muammosi. Birozdan keyin qayta urinib ko'ring.",
        "ru": "🌐 Проблема с сетью на сервере. Попробуйте чуть позже.",
        "en": "🌐 Server network problem. Please try again a bit later.",
    },
    "ERR_UNSUPPORTED": {
        "uz": "❌ Bu havola qo'llab-quvvatlanmaydi.",
        "ru": "❌ Эта ссылка не поддерживается.",
        "en": "❌ This link is not supported.",
    },
    "ERR_NOT_FOUND": {
        "uz": "❌ Kontent topilmadi yoki o'chirilgan.",
        "ru": "❌ Контент не найден или удалён.",
        "en": "❌ Content not found or deleted.",
    },
    "ERR_TOO_BIG": {
        "uz": "📦 Fayl juda katta (chegara {max_mb} MB).",
        "ru": "📦 Файл слишком большой (лимит {max_mb} МБ).",
        "en": "📦 File is too large (limit {max_mb} MB).",
    },
    "ERR_TOO_LONG": {
        "uz": "⏱ Video juda uzun (chegara {minutes} daqiqa).",
        "ru": "⏱ Видео слишком длинное (лимит {minutes} мин).",
        "en": "⏱ Video is too long (limit {minutes} min).",
    },
    "ERR_LIVE": {
        "uz": "📡 Jonli efirni yuklab bo'lmaydi.",
        "ru": "📡 Прямой эфир скачать нельзя.",
        "en": "📡 Live streams can't be downloaded.",
    },
    "ERR_TIMEOUT": {
        "uz": "⌛ Juda uzoq davom etdi. Keyinroq urinib ko'ring.",
        "ru": "⌛ Слишком долго. Попробуйте позже.",
        "en": "⌛ Took too long. Please try again later.",
    },
    "ERR_FAILED": {
        "uz": "❌ Yuklab bo'lmadi. Havolani tekshirib, qayta urinib ko'ring.",
        "ru": "❌ Не удалось скачать. Проверьте ссылку и попробуйте снова.",
        "en": "❌ Download failed. Check the link and try again.",
    },
    "ERR_UNEXPECTED": {
        "uz": "❌ Xatolik yuz berdi, keyinroq urinib ko'ring.",
        "ru": "❌ Произошла ошибка, попробуйте позже.",
        "en": "❌ Something went wrong, please try again later.",
    },
    # ---------------- majburiy obuna ----------------
    "SUBSCRIBE": {
        "uz": "📢 Botdan foydalanish uchun kanalga obuna bo'ling:",
        "ru": "📢 Чтобы пользоваться ботом, подпишитесь на канал:",
        "en": "📢 Please subscribe to the channel to use the bot:",
    },
    "BTN_CHANNEL": {"uz": "📢 Obuna bo'lish", "ru": "📢 Подписаться", "en": "📢 Subscribe"},
    "BTN_CHECK_SUB": {"uz": "✅ Tekshirish", "ru": "✅ Проверить", "en": "✅ Check"},
    "SUB_OK": {
        "uz": "✅ Rahmat! Endi havola yuborishingiz mumkin.",
        "ru": "✅ Спасибо! Теперь можно отправлять ссылки.",
        "en": "✅ Thanks! You can send links now.",
    },
    "SUB_NOT_YET": {
        "uz": "Hali obuna bo'lmadingiz.",
        "ru": "Вы ещё не подписались.",
        "en": "You haven't subscribed yet.",
    },
}


def t(lang: str | None, key: str, **kw) -> str:
    variants = _T[key]
    text = variants.get(lang or DEFAULT_LANG) or variants[DEFAULT_LANG]
    return text.format(**kw) if kw else text


def all_variants(key: str) -> set[str]:
    """Tugma matni qaysi tilda bo'lsa ham tanish uchun."""
    return set(_T[key].values())


def guess_lang(code: str | None) -> str:
    """Telegram ilovasi tilidan taxmin qilish (foydalanuvchi hali tanlamagan bo'lsa)."""
    code = (code or "").lower().split("-")[0]
    if code == "uz":
        return "uz"
    if code in ("ru", "uk", "be", "kk", "ky", "tg"):
        return "ru"
    if code:
        return "en"
    return DEFAULT_LANG


def progress_bar(percent: int, width: int = 10) -> str:
    filled = max(0, min(width, round(percent / 100 * width)))
    return "▰" * filled + "▱" * (width - filled)
