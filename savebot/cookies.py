"""Cookies to'plami: bir nechta akkaunt, navbat bilan ishlatish va ishlamay qolganini chetlash.

Fayllar ikki joydan o'qiladi:
  * cookies/        — serverga qo'lda qo'yilgan fayllar (Docker'da faqat o'qish uchun ulanadi)
  * data/cookies/   — admin Telegram orqali yuborgan fayllar (bot o'zi yozadi)

Har bir fayl qaysi saytlar uchun ekanligi ichidagi domenlardan aniqlanadi. Sayt 401 / "login
required" qaytarsa, o'sha fayl faqat o'sha sayt uchun chetga olinadi (bitta faylda Instagram o'lib,
YouTube tirik qolishi mumkin), keyingi akkauntga, oxirida esa cookie'siz (anonim) o'tiladi.
Fayl yangilansa (o'zgarish vaqti boshqacha bo'lsa) — chetlash avtomatik bekor bo'ladi.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)

HEADER = "# Netscape HTTP Cookie File\n"

# platforma -> cookie domenlari
PLATFORM_DOMAINS: dict[str, tuple[str, ...]] = {
    "instagram": ("instagram.com",),
    "threads": ("threads.net", "threads.com", "instagram.com"),
    "youtube": ("youtube.com",),
    "facebook": ("facebook.com",),
    "twitter": ("x.com", "twitter.com"),
    "tiktok": ("tiktok.com",),
    "pinterest": ("pinterest.com",),
    "reddit": ("reddit.com",),
    "vk": ("vk.com",),
}
# Saytga kirilganini bildiruvchi cookie (yuborilgan fayl tekshiruvi uchun)
LOGIN_COOKIE = {"instagram": "sessionid", "facebook": "c_user", "twitter": "auth_token",
                "tiktok": "sessionid"}

# 401 — sessiya bekor qilingan: fayl yangilanmaguncha ishlatilmaydi.
# "login required" / rate-limit — vaqtincha bo'lishi mumkin: 30 daqiqa dam.
HARD_DEAD = 10 ** 9
SOFT_DEAD = 30 * 60


def is_auth_error(detail: str) -> bool:
    msg = detail.lower()
    return any(s in msg for s in ("401", "unauthorized", "login", "log in", "checkpoint",
                                  "challenge_required", "not logged in", "sign in",
                                  "unreachable", "use --cookies"))


def _is_hard(detail: str) -> bool:
    msg = detail.lower()
    return any(s in msg for s in ("401", "unauthorized", "checkpoint", "challenge_required"))


def _domain_match(cookie_domain: str, domain: str) -> bool:
    d = cookie_domain.lstrip(".").lower()
    return d == domain or d.endswith("." + domain)


def parse_cookies(text: str) -> list[list[str]]:
    """Netscape cookies matnini o'qiydi. Telegram orqali nusxalanganda tab'lar bo'sh joyga
    aylanib ketishi mumkin — shuning uchun istalgan bo'sh joy bo'yicha ajratamiz."""
    rows = []
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")):
            continue
        parts = line.split()
        if len(parts) == 6:
            parts.append("")  # qiymati bo'sh cookie
        if len(parts) < 7:
            continue
        domain, flag, path, secure, expiry, name = parts[:6]
        value = " ".join(parts[6:])
        if flag.upper() not in ("TRUE", "FALSE") or secure.upper() not in ("TRUE", "FALSE"):
            continue
        if not expiry.lstrip("-").isdigit():
            continue
        rows.append([domain, flag.upper(), path, secure.upper(), expiry, name, value])
    return rows


def _platforms_of(rows: list[list[str]]) -> list[str]:
    found = []
    for platform, domains in PLATFORM_DOMAINS.items():
        if platform == "threads":
            continue  # threads Instagram cookie'sidan foydalanadi — alohida ko'rsatmaymiz
        if any(_domain_match(r[0].removeprefix("#HttpOnly_"), d) for r in rows for d in domains):
            found.append(platform)
    return found


@dataclass
class _FileInfo:
    path: str
    mtime: float
    domains: frozenset[str]


class CookiePool:
    def __init__(self, dirs: list[str], upload_dir: str, extra_files: list[str] | None = None):
        self.dirs = [d for d in dirs if d]
        self.upload_dir = upload_dir
        self.extra_files = [f for f in (extra_files or []) if f]
        self._files: dict[str, _FileInfo] = {}
        self._dead: dict[tuple[str, float, str], tuple[float, str, float]] = {}
        self._uses: dict[tuple[str, str], int] = {}
        self.notifier: Callable[[str], Awaitable[None]] | None = None

    # ---------------- fayllar ----------------
    def _scan(self) -> list[_FileInfo]:
        paths = []
        for folder in [*self.dirs, self.upload_dir]:
            if folder and os.path.isdir(folder):
                paths += [os.path.join(folder, n) for n in sorted(os.listdir(folder))
                          if n.endswith(".txt") and not n.startswith(".")]
        paths += [p for p in self.extra_files if os.path.isfile(p)]
        result, seen = [], set()
        for path in paths:
            real = os.path.realpath(path)
            if real in seen or not os.path.isfile(path):
                continue
            seen.add(real)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            info = self._files.get(path)
            if info is None or info.mtime != mtime:
                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        rows = parse_cookies(f.read())
                except OSError:
                    continue
                domains = frozenset(r[0].removeprefix("#HttpOnly_").lstrip(".").lower() for r in rows)
                info = _FileInfo(path, mtime, domains)
                self._files[path] = info
            result.append(info)
        return result

    def _covers(self, info: _FileInfo, platform: str) -> bool:
        return any(_domain_match(d, want) for d in info.domains
                   for want in PLATFORM_DOMAINS.get(platform, ()))

    def _dead_entry(self, info: _FileInfo, platform: str):
        entry = self._dead.get((info.path, info.mtime, platform))
        if entry and entry[0] > time.monotonic():
            return entry
        return None

    # ---------------- tanlash ----------------
    def pick(self, platform: str, exclude: set[str] | frozenset = frozenset()) -> str | None:
        """Shu platforma uchun ishlayotgan, eng kam ishlatilgan fayl. Yo'q bo'lsa None (anonim)."""
        if platform not in PLATFORM_DOMAINS:
            return None  # boshqa saytlarga cookies yubormaymiz
        candidates = [f for f in self._scan()
                      if f.path not in exclude and self._covers(f, platform)
                      and not self._dead_entry(f, platform)]
        if not candidates:
            return None
        chosen = min(candidates, key=lambda f: self._uses.get((f.path, platform), 0))
        self._uses[(chosen.path, platform)] = self._uses.get((chosen.path, platform), 0) + 1
        return chosen.path

    def mark_dead(self, path: str, platform: str, detail: str) -> None:
        info = self._files.get(path)
        if info is None:
            self._scan()
            info = self._files.get(path)
        if info is None:
            return
        hard = _is_hard(detail)
        key = (path, info.mtime, platform)
        already = self._dead_entry(info, platform) is not None
        self._dead[key] = (time.monotonic() + (HARD_DEAD if hard else SOFT_DEAD),
                           detail.strip().splitlines()[-1][:200] if detail.strip() else "",
                           time.time())
        log.warning("Cookies %s (%s) chetlandi: %s", os.path.basename(path), platform, detail[:150])
        if hard and not already and self.notifier:
            alive = sum(1 for f in self._scan()
                        if self._covers(f, platform) and not self._dead_entry(f, platform))
            text = (f"🍪 <b>{os.path.basename(path)}</b> — {platform} sessiyasi bekor qilindi (401).\n"
                    f"Ishlayotgan {platform} cookies: <b>{alive}</b> ta"
                    + (" — bot hozircha cookie'siz (anonim) ishlayapti." if not alive else ".")
                    + "\n\nYangisini qo'shish: <b>🛠 Admin panel → 🍪 Cookies</b>")
            try:
                asyncio.get_running_loop().create_task(self.notifier(text))
            except RuntimeError:
                pass

    # ---------------- holat va yuklash ----------------
    def status(self) -> list[dict]:
        out = []
        for info in self._scan():
            platforms = [p for p in PLATFORM_DOMAINS if p != "threads" and self._covers(info, p)]
            items = []
            for p in platforms:
                dead = self._dead_entry(info, p)
                items.append({"platform": p, "alive": dead is None,
                              "reason": dead[1] if dead else "", "since": dead[2] if dead else None,
                              "uses": self._uses.get((info.path, p), 0)})
            out.append({"name": os.path.basename(info.path), "path": info.path,
                        "uploaded": os.path.dirname(info.path) == self.upload_dir.rstrip("/"),
                        "platforms": items})
        return out

    def save_upload(self, text: str) -> tuple[str, list[str]]:
        """Admin yuborgan cookies matnini tekshirib saqlaydi. Qaytaradi: (fayl nomi, platformalar).

        Instagram'da fayl nomi akkaunt ID si bilan (instagram-123.txt): boshqa akkaunt — yangi fayl
        (navbatga qo'shiladi), o'sha akkaunt — eskisining o'rniga."""
        rows = parse_cookies(text)
        if not rows:
            raise ValueError("Bu cookies fayliga o'xshamaydi (Netscape formatidagi qatorlar topilmadi).")
        platforms = _platforms_of(rows)
        if not platforms:
            raise ValueError("Faylda tanish sayt (Instagram, YouTube, ...) cookie'lari yo'q.")
        names = {r[5] for r in rows}
        for p in platforms:
            need = LOGIN_COOKIE.get(p)
            if need and need not in names:
                raise ValueError(f"{p}: «{need}» cookie'si yo'q — saytga akkaunt bilan kirilgan holda "
                                 "eksport qiling.")
        main = platforms[0]
        suffix = ""
        if main == "instagram":
            uid = next((r[6] for r in rows if r[5] == "ds_user_id" and r[6]), "")
            suffix = f"-{uid}" if uid.isdigit() else ""
        name = f"{main}{suffix}.txt"
        os.makedirs(self.upload_dir, exist_ok=True)
        path = os.path.join(self.upload_dir, name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(HEADER)
            f.writelines("\t".join(r) + "\n" for r in rows)
        os.replace(tmp, path)
        return name, platforms
