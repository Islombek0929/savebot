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
_cache: dict[str, tuple[float, list[str]]] = {}
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


def _getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _original_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        if not isinstance(host, str) or not host or _is_ip(host) or host == "localhost" \
                or "." not in host or family == socket.AF_INET6:
            raise
        name = host.rstrip(".").lower()
        ips = resolve(name)
        if not ips:
            raise
        log.info("DNS zaxirasi (DoH): %s -> %s", name, ips[0])
        results = []
        for ip in ips:
            try:
                results += _original_getaddrinfo(ip, port, socket.AF_INET, type, proto, flags)
            except socket.gaierror:
                continue
        if not results:
            raise
        return results


def install() -> None:
    """socket.getaddrinfo ni zaxirali versiyaga almashtiradi (DOH_FALLBACK=0 bo'lsa — yo'q)."""
    global _installed
    if _installed or os.getenv("DOH_FALLBACK", "1").strip() in ("0", "false", "no"):
        return
    socket.getaddrinfo = _getaddrinfo
    _installed = True
