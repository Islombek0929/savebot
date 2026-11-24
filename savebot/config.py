"""Sozlamalar — hammasi .env faylidan (yoki muhit o'zgaruvchilaridan) o'qiladi."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field

from dotenv import load_dotenv


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def _list(name: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int] = field(default_factory=frozenset)
    # Oddiy Bot API — 50 MB. Local Bot API server bilan — 2000 MB.
    local_api_url: str | None = None
    max_mb: int = 50
    # Bir vaqtda serverda nechta yuklash ketadi (qolganlar navbatda turadi)
    max_parallel: int = 4
    # Bitta foydalanuvchi bir vaqtda nechta yuklash qila oladi
    per_user_limit: int = 2
    # Video sifati (eng kichik tomoni bo'yicha: 720 => 720p, vertikal videolar uchun ham to'g'ri)
    video_quality: int = 720
    # Videoning maksimal davomiyligi, soniya (0 — cheklovsiz)
    max_duration: int = 3 * 60 * 60
    # Bitta yuklash uchun maksimal vaqt, soniya
    download_timeout: int = 15 * 60
    cookies_file: str | None = None
    # Proxy (masalan socks5://user:pass@host:1080) — sayt server IP'sini bloklasa
    proxy: str | None = None
    db_path: str = "data/bot.db"
    tmp_dir: str = field(default_factory=tempfile.gettempdir)
    # Majburiy obuna kanallari: @kanal yoki -100... ID (bot kanalda admin bo'lishi shart)
    required_channels: tuple[str, ...] = ()
    # Kesh muddati (kun). Bir xil havola qayta yuborilsa, fayl yuklanmasdan darhol jo'natiladi.
    cache_days: int = 30
    # DMCA / murojaatlar uchun kontakt (masalan @admin_username)
    contact: str | None = None

    @property
    def max_bytes(self) -> int:
        return self.max_mb * 1024 * 1024

    @property
    def cookies(self) -> str | None:
        if self.cookies_file and os.path.exists(self.cookies_file):
            return self.cookies_file
        return None


def load_config() -> Config:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN topilmadi — .env faylini to'ldiring (namuna: .env.example)")
    local_api = os.getenv("LOCAL_API_URL", "").strip() or None
    return Config(
        bot_token=token,
        admin_ids=frozenset(int(x) for x in _list("ADMIN_IDS")),
        local_api_url=local_api,
        max_mb=_int("MAX_FILE_MB", 2000 if local_api else 50),
        max_parallel=max(1, _int("MAX_PARALLEL", 4)),
        per_user_limit=max(1, _int("PER_USER_LIMIT", 2)),
        video_quality=_int("VIDEO_QUALITY", 720),
        max_duration=_int("MAX_DURATION", 3 * 60 * 60),
        download_timeout=_int("DOWNLOAD_TIMEOUT", 15 * 60),
        cookies_file=os.getenv("COOKIES_FILE", "").strip() or None,
        proxy=os.getenv("PROXY", "").strip() or None,
        db_path=os.getenv("DB_PATH", "data/bot.db"),
        tmp_dir=os.getenv("TMP_DIR", "").strip() or tempfile.gettempdir(),
        required_channels=tuple(_list("REQUIRED_CHANNELS")),
        cache_days=_int("CACHE_DAYS", 30),
        contact=os.getenv("CONTACT", "").strip() or None,
    )
