"""Instagram'ga serverning o'zidan bir marta kirib, sessiyani bot cookies navbatiga qo'shadi.

Nega: brauzerdan ko'chirilgan cookies'ni Instagram tez bekor qiladi (boshqa IP / qurilma). Sessiya
serverning o'z IP'sidan yaratilsa, odatda ancha uzoq yashaydi.

Ishga tushirish (serverda, interaktiv terminalda):
    docker compose exec -it bot python -m savebot.ig_login

Parol faqat terminalda so'raladi (ko'rinmaydi) va hech qayerda saqlanmaydi — faqat sessiya cookies'i
data/cookies/instagram-<id>.txt ga yoziladi, bot uni darhol ishlata boshlaydi.
"""
from __future__ import annotations

import getpass
import sys
import time

from .config import load_config
from .cookies import CookiePool


def _netscape(jar) -> str:
    rows = []
    far = int(time.time()) + 365 * 24 * 3600
    for c in jar:
        if "instagram" not in (c.domain or ""):
            continue
        domain = c.domain if c.domain.startswith(".") else "." + c.domain
        rows.append("\t".join([
            domain, "TRUE", c.path or "/", "TRUE" if c.secure else "FALSE",
            str(int(c.expires) if c.expires else far), c.name, c.value or "",
        ]))
    return "\n".join(rows) + "\n"


def main() -> int:
    try:
        import instaloader
    except ImportError:
        print("instaloader o'rnatilmagan: pip install instaloader")
        return 1

    cfg = load_config()
    username = (sys.argv[1] if len(sys.argv) > 1 else input("Instagram login (username): ")).strip()
    password = getpass.getpass("Parol (ko'rinmaydi): ")
    loader = instaloader.Instaloader(quiet=True, max_connection_attempts=1, request_timeout=30)
    try:
        try:
            loader.login(username, password)
        except instaloader.TwoFactorAuthRequiredException:
            code = input("Ikki bosqichli tasdiqlash kodi: ").strip()
            loader.two_factor_login(code)
    except instaloader.BadCredentialsException:
        print("❌ Login yoki parol noto'g'ri.")
        return 2
    except instaloader.ConnectionException as e:
        print("❌ Instagram kirishni to'xtatdi (tekshiruv/checkpoint bo'lishi mumkin).\n"
              "   Telefon yoki brauzerda Instagram'ni ochib «Bu men edim» deb tasdiqlang va qayta urining.\n"
              f"   Tafsilot: {e}")
        return 3
    except instaloader.LoginException as e:
        print(f"❌ Kirib bo'lmadi: {e}")
        return 3
    finally:
        password = ""

    text = _netscape(loader.context._session.cookies)
    pool = CookiePool(dirs=[], upload_dir=cfg.cookies_upload_dir)
    try:
        name, platforms = pool.save_upload(text)
    except ValueError as e:
        print(f"❌ Sessiya cookies'i saqlanmadi: {e}")
        return 4
    print(f"✅ Tayyor: {name} ({', '.join(platforms)}). Bot uni darhol ishlatadi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
