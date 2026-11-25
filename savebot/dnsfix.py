"""DNS zaxirasi: tizim DNS i nomni topa olmasa — DNS-over-HTTPS (443-port) orqali so'raymiz.

Ba'zi tarmoqlarda (o'quv markazi, ofis) tashqi DNS (53-port) yopiq, mahalliy DNS esa Instagram/
Facebook CDN (fbcdn.net) manzillarini topa olmaydi: "Temporary failure in name resolution".
HTTPS (443) esa ochiq bo'ladi — shu orqali Cloudflare/Google'dan IP manzilni olamiz.

socket.getaddrinfo almashtiriladi: avval odatdagidek, faqat xato bo'lsa — DoH. Shuning uchun
yt-dlp, aiohttp (Telegram) va boshqa hamma narsa o'zgarishsiz ishlayveradi.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import socket
import ssl
import threading
import time
import urllib.request

log = logging.getLogger(__name__)

# IP manzil bilan — ularni topish uchun DNS kerak emas (sertifikatlarda IP ham yozilgan)
DOH_SERVERS = (
    "https://1.1.1.1/dns-query?name={name}&type=A",
    "https://8.8.8.8/resolve?name={name}&type=A",
    "https://1.0.0.1/dns-query?name={name}&type=A",
    "https://8.8.4.4/resolve?name={name}&type=A",
)

_original_getaddrinfo = socket.getaddrinfo
_original_gethostbyname = socket.gethostbyname
_cache: dict[str, tuple[float, list[str]]] = {}
# Tizim DNS i ishlamagan domenlar (masalan fbcdn.net) -> muddat. Bu domendagi boshqa nomlar uchun
# tizim DNS ni kutmaymiz: u xato berguncha 10-20 soniya o'tishi mumkin.
_doh_first: dict[str, float] = {}
DOH_FIRST_SECONDS = 3600
_lock = threading.Lock()
_installed = False


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]").split("%")[0])
        return True
    except ValueError:
        return False


def doh_query(name: str, timeout: float = 5.0) -> list[str]:
    """Nomning IPv4 manzillari (DoH orqali). Topilmasa — bo'sh ro'yxat."""
    ctx = ssl.create_default_context()
    for template in DOH_SERVERS:
        url = template.format(name=name)
        req = urllib.request.Request(url, headers={"accept": "application/dns-json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:  # noqa: BLE001 — keyingi serverni sinaymiz
            log.debug("DoH %s ishlamadi: %s", url, e)
            continue
        ips = [a["data"] for a in data.get("Answer") or [] if a.get("type") == 1 and a.get("data")]
        ttl = min([a.get("TTL", 300) for a in data.get("Answer") or [] if a.get("type") == 1] or [300])
        if ips or data.get("Status") == 3:  # 3 = NXDOMAIN — bunday nom yo'q
            with _lock:
                _cache[name] = (time.monotonic() + max(60, min(ttl, 3600)), ips)
            return ips
    return []


def resolve(name: str) -> list[str]:
    with _lock:
        hit = _cache.get(name)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    return doh_query(name)


def _domain(name: str) -> str:
    """Asosiy domen: instagram.ftas2-2.fna.fbcdn.net -> fbcdn.net"""
    return ".".join(name.split(".")[-2:])


def _doh_preferred(name: str) -> bool:
    until = _doh_first.get(_domain(name))
    return until is not None and until > time.monotonic()


def _doh_addrinfo(name, port, type, proto, flags) -> list:
    results = []
    for ip in resolve(name):
        try:
            results += _original_getaddrinfo(ip, port, socket.AF_INET, type, proto, flags)
        except socket.gaierror:
            continue
    return results


def _ipv4_only() -> bool:
    """IPv6 marshruti yo'q serverlarda Instagram'ning AAAA manziliga ulanish "[Errno 101] Network is
    unreachable" beradi. Standart: faqat IPv4. IPV4_ONLY=0 bilan o'chiriladi."""
    return os.environ.get("IPV4_ONLY", "1").strip().lower() not in ("0", "false", "no", "off")


def _getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family == 0 and _ipv4_only():
        family = socket.AF_INET
    name = _fallback_name(host)
    if name and family != socket.AF_INET6 and _doh_preferred(name):
        results = _doh_addrinfo(name, port, type, proto, flags)
        if results:
            return results
    try:
        return _original_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        if name is None or family == socket.AF_INET6:
            raise
        results = _doh_addrinfo(name, port, type, proto, flags)
        if not results:
            raise
        _doh_first[_domain(name)] = time.monotonic() + DOH_FIRST_SECONDS
        log.info("DNS zaxirasi (DoH): %s -> %s (%s uchun 1 soat DoH birinchi)",
                 name, results[0][4][0], _domain(name))
        return results


def _fallback_name(host) -> str | None:
    if not isinstance(host, str) or not host or _is_ip(host) or host == "localhost" or "." not in host:
        return None
    return host.rstrip(".").lower()


def _gethostbyname(host):
    name = _fallback_name(host)
    if name and _doh_preferred(name):
        ips = resolve(name)
        if ips:
            return ips[0]
    try:
        return _original_gethostbyname(host)
    except socket.gaierror:
        ips = resolve(name) if name else []
        if not ips:
            raise
        _doh_first[_domain(name)] = time.monotonic() + DOH_FIRST_SECONDS
        log.info("DNS zaxirasi (DoH): %s -> %s", name, ips[0])
        return ips[0]


def install() -> None:
    """socket.getaddrinfo ni zaxirali versiyaga almashtiradi (DOH_FALLBACK=0 bo'lsa — yo'q)."""
    global _installed
    if _installed or os.getenv("DOH_FALLBACK", "1").strip() in ("0", "false", "no"):
        return
    socket.getaddrinfo = _getaddrinfo
    socket.gethostbyname = _gethostbyname
    _installed = True


if __name__ == "__main__":  # diagnostika: python -m savebot.dnsfix instagram.com ...
    import sys

    for host in sys.argv[1:] or ["instagram.ftas2-2.fna.fbcdn.net", "api.telegram.org"]:
        try:
            print(f"{host}: tizim DNS -> {_original_gethostbyname(host)}")
        except OSError as e:
            ips = doh_query(host)
            print(f"{host}: tizim DNS xato ({e}); DoH -> {ips or 'topilmadi'}")
