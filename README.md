# Universal Save Bot

Telegram bot: havola yuborilsa Instagram, TikTok, YouTube, Facebook, X (Twitter), Pinterest,
Threads, Reddit, VK, SoundCloud va yt-dlp qo'llab-quvvatlaydigan 1000+ saytdan **video, rasm va
audioni asl sifatda, suv belgisiz** yuklab beradi.

## Imkoniyatlar

| | |
|---|---|
| 🎬 **Suv belgisiz video** | TikTok'da logotip va `@akkaunt` yozuvi tushirilgan format tanlanmaydi. Instagram'dan asl fayl olinadi. Izohdagi "Video by username" kabi akkaunt nomi olib tashlanadi. |
| 🖼 **Rasmlar va karusellar** | Instagram post/karusel, TikTok foto-postlar, Pinterest, X rasmlari albom qilib yuboriladi (gallery-dl). |
| 📹 **Sifat tanlash** | Videoda bir nechta sifat bo'lsa (YouTube, Facebook, Vimeo, X ...), tugmalar chiqadi: 360p, 480p, 720p, 1080p, 2K — har birining hajmi bilan. Telegram chegarasiga sig'maydiganlari alohida yoziladi. Bitta sifatli videolar (TikTok va ko'p reels) darhol yuklanadi. |
| 🎵 **MP3** | Sifat tanlovida va har bir video ostida «🎵 MP3» tugmasi bor. MP3 muqova rasmi va nomi bilan keladi. |
| ⚡ **Kesh** | Bir xil havola qayta yuborilsa, fayl qayta yuklanmaydi va bir zumda jo'natiladi (Telegram `file_id`). |
| 📦 **Hajmga mos sifat** | Tanlov bo'lmagan holatda video 50 MB ga sig'masa, avtomatik 480p/360p tanlanadi. MP3 bitreyti uzunligiga qarab moslashadi. |
| 🌐 **3 til** | O'zbekcha, Русский, English. Birinchi /start'da til so'raladi, keyin `/lang` yoki pastdagi «🌐 Til» tugmasi orqali o'zgartiriladi. Bot ta'rifi va buyruqlar menyusi ham Telegram ilovasi tiliga qarab ko'rinadi. |
| 🎨 **Rangli tugmalar** | Video sifatlari — ko'k, MP3 va tasdiqlash — yashil (Telegram'ning yangi rangli tugmalari; eski ilovalarda oddiy ko'rinadi). |
| 🕒 **Navbat** | Server bo'yicha bir vaqtda `MAX_PARALLEL` ta yuklash ketadi, qolganlar navbatda o'z o'rnini ko'radi. Bitta foydalanuvchi serverni band qilib qo'ya olmaydi. |
| 📊 **Jarayon** | «⏳ Yuklanmoqda: 45%» ko'rinishida holat ko'rsatiladi. |
| 👥 **Guruhlar** | Guruhga qo'shilsa, tanish platformalardagi havolalarni yuklab beradi (oddiy havolalarga javob bermaydi). |
| 🛠 **Admin panel** | `/stats`, `/broadcast` (hammaga xabar), `/ban`, `/unban`, `/update` (yt-dlp'ni yangilash). |
| 📢 **Majburiy obuna** | `REQUIRED_CHANNELS` orqali kanal(lar)ga obunani tekshiradi (ixtiyoriy). |
| 🛡 **Himoya** | Flood'dan himoya, ban, ichki tarmoq manzillarini (localhost, 10.x, 169.254.x) rad etish, root bo'lmagan Docker konteyner. |

## Tez ishga tushirish (Docker, tavsiya etiladi)

1. [@BotFather](https://t.me/BotFather) da `/newbot` orqali bot yarating va tokenni oling.
2. Telegram ID'ingizni [@userinfobot](https://t.me/userinfobot) dan bilib oling.
3. Serverda:

```bash
git clone https://github.com/islombek0929/savebot.git
cd savebot
cp .env.example .env
nano .env          # BOT_TOKEN va ADMIN_IDS ni yozing
docker compose up -d --build
docker compose logs -f
```

Bot ishga tushganda yt-dlp va gallery-dl avtomatik yangilanadi.

## Docker'siz (Ubuntu/Debian VPS)

```bash
sudo apt install -y python3-venv ffmpeg git
sudo useradd -m -d /opt/savebot savebot
sudo -u savebot git clone https://github.com/islombek0929/savebot.git /opt/savebot
cd /opt/savebot
sudo -u savebot python3 -m venv venv
sudo -u savebot venv/bin/pip install -r requirements.txt
sudo -u savebot cp .env.example .env && sudo -u savebot nano .env
sudo cp deploy/savebot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now savebot
journalctl -u savebot -f
```

## 1000 foydalanuvchi uchun server

| | Minimal | Tavsiya |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 2 GB | 4 GB |
| Disk | 20 GB SSD | 40 GB SSD |
| `MAX_PARALLEL` | 3 | 4–6 |

Faol 1000 kishi uchun shu yetarli. Kesh takroriy havolalarni (masalan, trenddagi reels) yuklamasdan
yuboradi, shuning uchun yuk kam bo'ladi. Ko'p vaqt yuklashga emas, Telegram'ga yuborishga ketadi,
shu sababli serverni Yevropada (Germaniya/Niderlandiya) olgan ma'qul. Foydalanuvchilar ko'payganda
`MAX_PARALLEL` ni oshiring va Local Bot API'ni yoqing.

## Sozlamalar (`.env`)

| O'zgaruvchi | Standart | Izoh |
|---|---|---|
| `BOT_TOKEN` | — | **Majburiy.** BotFather tokeni |
| `ADMIN_IDS` | — | Admin ID lari, vergul bilan |
| `MAX_PARALLEL` | 4 | Bir vaqtda nechta yuklash |
| `PER_USER_LIMIT` | 2 | Bitta foydalanuvchi bir vaqtda nechta yuklay oladi |
| `ASK_QUALITY` | 1 | Sifat tanlash tugmalari (0 — darhol avtomatik sifatda yuklash) |
| `MAX_QUALITY` | 1440 | Tanlovdagi eng yuqori sifat: 1080 / 1440 (2K) / 2160 (4K) |
| `VIDEO_QUALITY` | 720 | Tanlov bo'lmaganda avtomatik sifat |
| `MAX_DURATION` | 10800 | Maksimal davomiylik (soniya) |
| `DOWNLOAD_TIMEOUT` | 900 | Bitta yuklash uchun vaqt (soniya) |
| `CACHE_DAYS` | 30 | Kesh muddati |
| `REQUIRED_CHANNELS` | — | `@kanal` yoki `-100ID\|https://t.me/+link`. Bot kanalda **admin** bo'lishi kerak |
| `CONTACT` | — | /help da ko'rinadigan aloqa (DMCA uchun) |
| `COOKIES_FILE` | cookies/cookies.txt | Instagram/YouTube cookies fayli |
| `PROXY` | — | `socks5://...` yoki `http://...` |
| `LOCAL_API_URL` | — | Local Bot API manzili (2 GB gacha) |
| `MAX_FILE_MB` | 50 / 2000 | Fayl chegarasi |
| `AUTO_UPDATE` | 1 | Docker ishga tushganda yt-dlp'ni yangilash |

## Muhim eslatmalar

### Instagram va cookies
Instagram server IP'laridan kelgan anonim so'rovlarni tez-tez rad etadi ("login required" yoki
"HTTP Error 403"). Bunday bo'lsa, bot adminga ogohlantirish yuboradi. Yechim — cookies:

1. **Alohida** Instagram akkaunt oching (asosiy akkauntingizni ishlatmang, bloklanishi mumkin).
   Akkauntga rasm qo'yib, 2–3 ta sahifaga obuna bo'ling — "tirik" akkaunt kamroq bloklanadi.
2. Kompyuterda Chrome'ga **"Get cookies.txt LOCALLY"** kengaytmasini o'rnating.
3. instagram.com ga shu akkaunt bilan kiring → kengaytmani bosing → **Export** (`cookies.txt` yuklanadi).
4. Faylni serverga `savebot/cookies/cookies.txt` qilib qo'ying. Eng oson usul — nusxa ko'chirish:
   ```bash
   mkdir -p /home/amix/savebot/cookies
   nano /home/amix/savebot/cookies/cookies.txt
   ```
   Kompyuterda `cookies.txt` ni Bloknotda oching, hammasini nusxalang (Ctrl+A, Ctrl+C), nano'ga
   joylang (sichqonchaning o'ng tugmasi), saqlang: **Ctrl+O**, **Enter**, **Ctrl+X**.
5. `chmod 644 /home/amix/savebot/cookies/cookies.txt` va `docker compose restart bot`.
6. Logda `Cookies ulangan` chiqsa — tayyor: `docker compose logs bot | grep -i cookies`

`.env` yoki `docker-compose.yml` ni o'zgartirish shart emas. YouTube cookie'larini ham shu faylning
oxiriga qo'shish mumkin. Cookies vaqt o'tib eskiradi — ogohlantirish yana kelsa, qaytadan eksport qiling.

### YouTube
YouTube ba'zan server IP'sini bloklaydi ("Sign in to confirm you're not a bot"). Yechim: cookies
(yuqoridagidek) yoki `PROXY`. YouTube uchun kerakli JavaScript runtime (deno) avtomatik o'rnatiladi.

### 50 MB chegarasi, 1080p/2K va Local Bot API
Bu botning emas, **Telegram'ning cheklovi**: rasmiy Bot API orqali har qanday bot 50 MB dan katta
fayl yubora olmaydi. Taxminiy hajmlar (YouTube):

| Sifat | 1 daqiqa | 5 daqiqa | 10 daqiqa |
|---|---|---|---|
| 720p | ~8 MB | ~40 MB | ~80 MB |
| 1080p | ~15 MB | ~75 MB | ~150 MB |
| 2K | ~35 MB | ~170 MB | ~350 MB |

Ya'ni oddiy rejimda 1080p va 2K faqat qisqa videolar uchun ishlaydi; bot sig'maydigan sifatlarni
tanlovda "50 MB dan katta" deb ko'rsatadi. **2K ni to'liq ishlatish uchun Local Bot API shart** —
u bilan chegara 2 GB bo'ladi (`docker-compose.yml` da tayyor). Bunda diskka e'tibor bering:
bir vaqtda `MAX_PARALLEL` ta yuklash × 2 GB gacha vaqtinchalik joy kerak (40 GB+ disk tavsiya etiladi).

Yoqish:
1. https://my.telegram.org → API development tools dan `api_id` va `api_hash` oling.
2. Botni rasmiy serverdan chiqaring (bir marta): `https://api.telegram.org/bot<TOKEN>/logOut` ni brauzerda oching.
3. `.env` ga yozing:
   ```
   TELEGRAM_API_ID=...
   TELEGRAM_API_HASH=...
   LOCAL_API_URL=http://telegram-bot-api:8081
   MAX_FILE_MB=2000
   ```
4. `docker compose --profile localapi up -d --build`

### yt-dlp'ni yangilab turish
Saytlar tez-tez o'zgaradi. Biror sayt ishlamay qolsa, botda `/update` yozing yoki konteynerni
qayta ishga tushiring (`docker compose restart`). Docker har ishga tushganda yangilanadi,
systemd xizmati esa har 7 kunda o'zi qayta ishga tushadi.

### Huquqiy tomoni
Bot foydalanuvchi yuborgan ochiq kontentni yuklaydi. Mualliflik huquqi bo'yicha shikoyatlar
(DMCA) uchun `CONTACT` ni albatta to'ldiring. Yopiq (private) akkauntlar kontenti yuklanmaydi.

## Admin buyruqlari

| Buyruq | Vazifasi |
|---|---|
| `/admin` | Buyruqlar ro'yxati |
| `/stats` | Foydalanuvchilar, yuklashlar, top platformalar, navbat holati, versiyalar |
| `/broadcast` | Istalgan xabarga (matn, rasm, video) **reply** qilib yozing: tasdiqlagach hammaga yuboriladi |
| `/ban ID` / `/unban ID` | Foydalanuvchini bloklash / blokdan chiqarish |
| `/update` | yt-dlp va gallery-dl ni yangilaydi va botni qayta ishga tushiradi |

## Loyiha tuzilishi

```
savebot/
  __main__.py      ishga tushirish (python -m savebot)
  config.py        .env sozlamalari
  downloader.py    yt-dlp + gallery-dl, suv belgisiz format tanlash
  services.py      navbat, kesh, yuborish, obuna tekshiruvi
  db.py            SQLite (foydalanuvchilar, statistika, kesh)
  middlewares.py   ro'yxatga olish, ban, flood himoyasi
  handlers/        foydalanuvchi va admin buyruqlari
  texts.py         bot matnlari (uz / ru / en)
tests/             avtomatik testlar (internetsiz ishlaydi)
```

## Testlar

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Testlar internetsiz ishlaydi: format tanlash (TikTok suv belgisi), lokal HTTP server orqali
haqiqiy yt-dlp/gallery-dl/ffmpeg yuklash, ma'lumotlar bazasi va soxta Telegram sessiyasi
bilan barcha bot buyruqlari tekshiriladi.
