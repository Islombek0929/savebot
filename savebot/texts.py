"""Bot matnlari (o'zbekcha). HTML formatida."""

START = (
    "👋 Salom, <b>{name}</b>!\n\n"
    "Menga havola yuboring — videoni, rasmni yoki audioni <b>asl sifatda, suv belgisiz</b> "
    "yuklab beraman.\n\n"
    "📌 Qo'llab-quvvatlanadi: Instagram (reels, post, karusel, stories), TikTok (video va rasm), "
    "YouTube (video, shorts, MP3), Facebook, X (Twitter), Pinterest, Threads, Reddit, Likee, "
    "Snapchat, VK, SoundCloud va yana 1000+ sayt.\n\n"
    "ℹ️ Fayl hajmi chegarasi: {max_mb} MB\n"
    "❓ Yordam: /help"
)

HELP = (
    "<b>Qanday ishlatiladi?</b>\n\n"
    "1️⃣ Ilovada videoning «Ulashish» → «Havolani nusxalash» tugmasini bosing.\n"
    "2️⃣ Havolani shu yerga yuboring.\n"
    "3️⃣ Bir necha soniyada fayl tayyor bo'ladi.\n\n"
    "🎬 Video ostidagi <b>«🎵 MP3»</b> tugmasi orqali uning audiosini ham olasiz.\n"
    "▶️ YouTube havolasida format tanlash tugmalari chiqadi.\n"
    "👥 Botni guruhga qo'shsangiz, guruhdagi havolalarni ham yuklab beradi.\n\n"
    "ℹ️ Fayl hajmi chegarasi: {max_mb} MB. Yopiq (private) akkauntlardagi kontent yuklanmaydi."
)

CONTACT_LINE = "\n\n📩 Murojaat va mualliflik huquqi (DMCA) bo'yicha: {contact}"

SEND_LINK = "🔗 Iltimos, video yoki post havolasini yuboring."
CHOOSE_FORMAT = "Qaysi formatda yuklab beray?"
BTN_VIDEO = "🎬 Video"
BTN_AUDIO = "🎵 MP3"
LINK_EXPIRED = "Havola eskirgan, uni qaytadan yuboring."

QUEUED = "🕒 Navbatdasiz ({pos}-o'rin). Biroz kuting..."
STARTING = "⏳ Yuklanmoqda..."
PROGRESS = "⏳ Yuklanmoqda: {percent}%"
PROCESSING = "⚙️ Tayyorlanmoqda..."
UPLOADING = "📤 Telegram'ga yuborilmoqda..."
TOO_MANY = "✋ Oldingi yuklashlaringiz tugashini kuting (bir vaqtda {limit} ta)."

ERR_PRIVATE = "🔒 Bu kontent yopiq yoki login talab qiladi. Ochiq (public) akkauntdagi havolani yuboring."
ERR_UNSUPPORTED = "❌ Bu havola qo'llab-quvvatlanmaydi."
ERR_NOT_FOUND = "❌ Kontent topilmadi yoki o'chirilgan."
ERR_TOO_BIG = "📦 Fayl juda katta — {max_mb} MB dan oshadi."
ERR_TOO_LONG = "⏱ Video juda uzun (chegara: {minutes} daqiqa)."
ERR_LIVE = "📡 Jonli efirni yuklab bo'lmaydi. Efir tugagach urinib ko'ring."
ERR_TIMEOUT = "⌛ Yuklash juda uzoq davom etdi. Keyinroq qayta urinib ko'ring."
ERR_FAILED = "❌ Yuklab bo'lmadi. Havolani tekshirib, qayta urinib ko'ring."
ERR_UNEXPECTED = "❌ Xatolik yuz berdi, keyinroq urinib ko'ring."

SUBSCRIBE = "📢 Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo'ling, so'ng «✅ Tekshirish» tugmasini bosing."
BTN_CHECK_SUB = "✅ Tekshirish"
SUB_OK = "✅ Rahmat! Endi havola yuborishingiz mumkin."
SUB_NOT_YET = "Hali obuna bo'lmadingiz."
