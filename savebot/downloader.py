"""
Yuklovchi: yt-dlp (video/audio) + gallery-dl (rasmlar, karusellar, TikTok foto-postlar).

Suv belgisi (watermark) haqida:
  * TikTok — yt-dlp ikki xil format beradi: "play_addr" (toza) va "download_addr"
    (TikTok logosi va @akkaunt nomi tushirilgan). Biz "watermark" deb belgilangan
    formatlarni format tanlashdan chiqarib tashlaymiz.
  * Instagram — server asl faylni beradi; Instagram'ning o'z "yuklab olish" tugmasidagidek
    logotip va akkaunt nomi qo'shilmaydi.
"""
from __future__ import annotations

import asyncio
import copy
import ipaddress
import json
import logging
import os
import re
import shutil
import socket
import sys
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yt_dlp

from .config import Config

log = logging.getLogger(__name__)

VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
AUDIO_EXT = {".mp3", ".m4a", ".opus", ".ogg", ".aac", ".wav", ".flac"}
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ANIMATION_EXT = {".gif"}
JUNK_SUFFIXES = (".part", ".ytdl", ".temp", ".json", ".description", ".tmp")

# Suv belgili formatlarni chiqarib tashlovchi filtr (format_note ichida "watermark" bo'lmasin)
NO_WATERMARK = "[format_note!*=?watermark][format_id!^=?download]"

# Bu xato kodlarida boshqa usul bilan qayta urinish ma'nosiz
FATAL_CODES = {"live", "too_long", "too_big", "timeout"}


class DownloadError(Exception):
    """Foydalanuvchiga tushunarli xato. code: private, unsupported, not_found, too_big,
    too_long, live, timeout, failed."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class _Timeout(Exception):
    pass


@dataclass
class MediaFile:
    path: str
    kind: str  # video | audio | photo | animation | document
    width: int | None = None
    height: int | None = None
    duration: int | None = None


@dataclass
class Result:
    files: list[MediaFile]
    title: str = ""
    platform: str = "other"
    performer: str | None = None


@dataclass
class Progress:
    """Yuklash holati — thread ichidan yoziladi, asosiy loop o'qiydi."""

    percent: int | None = None
    stage: str = "download"  # download | process


# ----------------------------------------------------------------------------------
# Havolalar bilan ishlash
# ----------------------------------------------------------------------------------
_PLATFORMS: list[tuple[str, re.Pattern]] = [
    (name, re.compile(rf"(^|\.)({pattern})$"))
    for name, pattern in [
        ("youtube", r"youtube\.com|youtu\.be|youtube-nocookie\.com"),
        ("instagram", r"instagram\.com|instagr\.am"),
        ("tiktok", r"tiktok\.com"),
        ("facebook", r"facebook\.com|fb\.watch|fb\.com"),
        ("twitter", r"twitter\.com|x\.com"),
        ("pinterest", r"pinterest\.[a-z.]+|pin\.it"),
        ("threads", r"threads\.net|threads\.com"),
        ("reddit", r"reddit\.com|redd\.it"),
        ("snapchat", r"snapchat\.com"),
        ("likee", r"likee\.video|like\.video"),
        ("vk", r"vk\.com|vk\.ru|vkvideo\.ru"),
        ("ok", r"ok\.ru"),
        ("soundcloud", r"soundcloud\.com"),
        ("vimeo", r"vimeo\.com"),
        ("dailymotion", r"dailymotion\.com|dai\.ly"),
        ("twitch", r"twitch\.tv"),
    ]
]
# Bu platformalarda "?" dan keyingi parametrlar faqat kuzatuv uchun (igsh, utm, is_from_webapp...)
_STRIP_QUERY = {"instagram", "tiktok", "twitter", "pinterest", "threads", "reddit",
                "snapchat", "likee", "soundcloud"}
_KEEP_QUERY = {"facebook": {"v", "story_fbid", "id", "fbid"}, "vk": {"z", "w"}}

URL_RE = re.compile(r"https?://[^\s<>\"'«»]+", re.IGNORECASE)
BARE_URL_RE = re.compile(
    r"(?<![\w./@-])((?:[\w-]+\.)*(?:instagram\.com|tiktok\.com|youtu\.be|youtube\.com|x\.com|"
    r"twitter\.com|facebook\.com|fb\.watch|pin\.it|pinterest\.com|threads\.net|threads\.com)"
    r"/[^\s<>\"'«»]+)",
    re.IGNORECASE,
)


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    for prefix in ("www.", "m.", "mobile.", "web."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def platform_of(url: str) -> str:
    host = _host(url)
    for name, rx in _PLATFORMS:
        if rx.search(host):
            return name
    return host or "other"


KNOWN_PLATFORMS = {name for name, _ in _PLATFORMS}


def is_known_platform(url: str) -> bool:
    return platform_of(url) in KNOWN_PLATFORMS


def clean_url(raw: str) -> str:
    """Matndan olingan havola oxiridagi tinish belgilarini olib tashlaydi."""
    url = raw.strip().rstrip(".,;:!?)]}>'\"")
    if not re.match(r"https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url


def find_url(text: str | None) -> str | None:
    if not text:
        return None
    m = URL_RE.search(text)
    if m:
        return clean_url(m.group(0))
    m = BARE_URL_RE.search(text)
    return clean_url(m.group(1)) if m else None


def normalize_url(url: str) -> str:
    """Kesh kaliti uchun havolani bir xil ko'rinishga keltiradi (kuzatuv parametrlarisiz)."""
    p = urlsplit(url.strip())
    host = _host(url)
    path = re.sub(r"/{2,}", "/", p.path).rstrip("/") or "/"
    platform = platform_of(url)
    query = dict(parse_qsl(p.query))

    if platform == "youtube":
        video_id = None
        if host == "youtu.be":
            video_id = path.strip("/").split("/")[0]
        elif path == "/watch":
            video_id = query.get("v")
        elif m := re.match(r"^/(shorts|live|embed|v)/([\w-]{6,})", path):
            video_id = m.group(2)
        if video_id:
            prefix = "music." if host.startswith("music.") else ""
            return f"https://{prefix}youtube.com/watch?v={video_id}"
        return urlunsplit(("https", host, path, p.query, ""))

    if platform in _STRIP_QUERY:
        new_query = ""
    elif platform in _KEEP_QUERY:
        keep = _KEEP_QUERY[platform]
        new_query = urlencode(sorted((k, v) for k, v in query.items() if k in keep))
    else:
        new_query = p.query
    return urlunsplit(("https", host, path, new_query, ""))


def wants_format_choice(url: str) -> bool:
    """YouTube'da odamlar ko'pincha MP3 ham so'raydi — shuning uchun tanlov beramiz."""
    host = _host(url)
    return platform_of(url) == "youtube" and not host.startswith("music.")


def is_audio_site(url: str) -> bool:
    host = _host(url)
    return host.startswith("music.youtube.") or platform_of(url) == "soundcloud" or host.endswith(
        "bandcamp.com"
    )


def prefers_gallery(url: str) -> bool:
    """Rasm bo'lishi mumkin bo'lgan postlar — avval gallery-dl (rasm+video aralash karusellar)."""
    platform = platform_of(url)
    path = urlsplit(url).path
    if platform == "tiktok" and "/photo/" in path:
        return True
    if platform == "instagram" and re.match(r"^/(?:[\w.]+/)?p/", path):
        return True
    return False


async def is_public_url(url: str) -> bool:
    """SSRF himoyasi: localhost, ichki tarmoq va bulut metadata manzillarini rad etadi."""
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    if p.scheme.lower() not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan")):
        return False
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        return True  # DNS ishlamasa ham yuklovchining o'zi xato beradi
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            return False
    return True


# ----------------------------------------------------------------------------------
# Format tanlash
# ----------------------------------------------------------------------------------
def _format_sort(res: int) -> list[str]:
    # res — eng kichik tomon bo'yicha (vertikal 1080x1920 => 1080). h264 + mp4 hamma
    # Telegram ilovalarida (iPhone ham) muammosiz o'ynaydi.
    return [f"res:{res}", "vcodec:h264", "acodec:aac", "ext:mp4:m4a"]


def _video_selector() -> str:
    return f"bv*{NO_WATERMARK}+ba/b{NO_WATERMARK}/bv*+ba/b"


def _ladder(quality: int) -> list[int]:
    steps = [q for q in (1080, 720, 480, 360, 240, 144) if q < quality]
    return [quality, *steps]


def _size_of(fmt: dict) -> int | None:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if size:
        return int(size)
    parts = fmt.get("requested_formats") or []
    sizes = [p.get("filesize") or p.get("filesize_approx") for p in parts]
    if parts and all(sizes):
        return int(sum(sizes))
    # Davomiylik va bitreyt bo'yicha taxmin
    tbr, duration = fmt.get("tbr"), fmt.get("duration")
    if tbr and duration:
        return int(tbr * 1000 / 8 * duration)
    return None


def choose_video_format(info: dict, max_bytes: int, quality: int) -> tuple[str, int | None]:
    """Hajm chegarasiga sig'adigan eng yaxshi suv belgisiz formatni tanlaydi.

    Qaytaradi: (format_id, taxminiy hajm). Hech qaysi sifat sig'masa DownloadError("too_big").
    """
    last_size = None
    seen: set[str] = set()
    for res in _ladder(quality):
        opts = {
            "format": _video_selector(),
            "format_sort": _format_sort(res),
            "quiet": True,
            "no_warnings": True,
            "simulate": True,
            "logger": _QuietLogger(),
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                chosen = ydl.process_ie_result(copy.deepcopy(info), download=False)
            except yt_dlp.utils.DownloadError as e:
                raise DownloadError("failed", str(e)) from e
        format_id = chosen.get("format_id")
        if not format_id or format_id in seen:
            continue
        seen.add(format_id)
        size = _size_of({**chosen, "duration": info.get("duration")})
        last_size = size
        if size is None or size <= max_bytes:
            return format_id, size
    raise DownloadError("too_big", f"{last_size} bytes")


def audio_bitrate(duration: float | None, max_bytes: int) -> int:
    """MP3 hajmi chegaradan oshmasligi uchun bitreytni tanlaydi (kbit/s)."""
    if not duration:
        return 192
    fits = max_bytes * 8 / duration / 1000 * 0.95
    for kbps in (192, 160, 128, 96, 64, 48):
        if kbps <= fits:
            return kbps
    raise DownloadError("too_big", f"audio {duration}s")


class _QuietLogger:
    def debug(self, msg):  # noqa: D401
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        log.debug("yt-dlp: %s", msg)

    def error(self, msg):
        log.debug("yt-dlp error: %s", msg)


# ----------------------------------------------------------------------------------
# Xatolarni tasniflash
# ----------------------------------------------------------------------------------
def classify_error(text: str) -> str:
    msg = text.lower()
    if any(s in msg for s in ("is live", "live event", "livestream", "currently live")):
        return "live"
    if any(s in msg for s in ("larger than max-filesize", "file is larger")):
        return "too_big"
    if any(s in msg for s in ("unsupported url", "no suitable extractor", "is not a valid url")):
        return "unsupported"
    if any(s in msg for s in (
        "login", "log in", "sign in", "cookies", "private", "authentication",
        "rate-limit", "rate limit", "not available in your country", "age-restricted",
        "age restricted", "confirm your age", "members-only", "http error 401",
        "http error 403", "restricted",
    )):
        return "private"
    if any(s in msg for s in (
        "not found", "404", "unavailable", "does not exist", "has been removed", "deleted",
        "no video", "there is no video",
    )):
        return "not_found"
    return "failed"


# ----------------------------------------------------------------------------------
# Fayllarni tayyorlash
# ----------------------------------------------------------------------------------
def kind_of(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in PHOTO_EXT:
        return "photo"
    if ext in ANIMATION_EXT:
        return "animation"
    return "document"


def list_files(workdir: str) -> list[str]:
    files = []
    for name in sorted(os.listdir(workdir)):
        path = os.path.join(workdir, name)
        if os.path.isfile(path) and not name.endswith(JUNK_SUFFIXES) and os.path.getsize(path) > 0:
            files.append(path)
    return files


async def _run(*cmd: str, timeout: float = 120) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")


async def probe_video(path: str) -> tuple[int | None, int | None, int | None]:
    """ffprobe orqali eni, bo'yi va davomiyligini oladi (Telegram'da to'g'ri ko'rinishi uchun)."""
    try:
        code, out, _ = await _run(
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:stream_side_data=rotation:format=duration",
            "-of", "json", path, timeout=30,
        )
        if code != 0:
            return None, None, None
        data = json.loads(out)
        stream = (data.get("streams") or [{}])[0]
        w, h = stream.get("width"), stream.get("height")
        rotation = 0
        for sd in stream.get("side_data_list") or []:
            rotation = int(sd.get("rotation") or rotation)
        if abs(rotation) in (90, 270):
            w, h = h, w
        duration = (data.get("format") or {}).get("duration")
        return w, h, int(float(duration)) if duration else None
    except (OSError, ValueError, asyncio.TimeoutError):
        return None, None, None


async def to_mp4(path: str) -> str:
    """webm/mkv/mov ni qayta kodlamasdan mp4 ga o'tkazadi (Telegram'da video sifatida o'ynashi uchun)."""
    if path.lower().endswith(".mp4"):
        return path
    out = os.path.splitext(path)[0] + ".remux.mp4"
    try:
        code, _, _ = await _run(
            "ffmpeg", "-y", "-v", "error", "-i", path, "-map", "0", "-c", "copy",
            "-movflags", "+faststart", out, timeout=180,
        )
    except (OSError, asyncio.TimeoutError):
        code = 1
    if code == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
        os.remove(path)
        return out
    if os.path.exists(out):
        os.remove(out)
    return path


# ----------------------------------------------------------------------------------
# Asosiy yuklovchi
# ----------------------------------------------------------------------------------
@dataclass
class _Ctx:
    url: str
    kind: str  # video | audio
    workdir: str
    progress: Progress
    deadline: float
    meta: dict = field(default_factory=dict)


class Downloader:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    async def download(self, url: str, kind: str, workdir: str,
                       progress: Progress | None = None) -> Result:
        ctx = _Ctx(url, kind, workdir, progress or Progress(),
                   time.monotonic() + self.cfg.download_timeout)
        if kind == "audio":
            order = [self._ytdlp]
        elif prefers_gallery(url):
            order = [self._gallery, self._ytdlp]
        else:
            order = [self._ytdlp, self._gallery]

        first_error: DownloadError | None = None
        for method in order:
            try:
                result = await method(ctx)
            except DownloadError as e:
                log.info("%s %s: %s", method.__name__, url, e)
                if e.code in FATAL_CODES:
                    raise
                first_error = first_error or e
                _clear(workdir)
                continue
            if result.files:
                result.platform = platform_of(url)
                return result
            _clear(workdir)
        raise first_error or DownloadError("failed", "fayl topilmadi")

    # ---------------- yt-dlp ----------------
    def _base_opts(self, ctx: _Ctx) -> dict:
        def hook(d: dict) -> None:
            if time.monotonic() > ctx.deadline:
                raise _Timeout()
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if total:
                    ctx.progress.percent = min(99, int(d.get("downloaded_bytes", 0) * 100 / total))
            elif d.get("status") == "finished":
                ctx.progress.stage = "process"

        opts = {
            "outtmpl": os.path.join(ctx.workdir, "%(id).60s_%(autonumber)02d.%(ext)s"),
            "noplaylist": True,
            "playlistend": 10,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": _QuietLogger(),
            "restrictfilenames": True,
            "windowsfilenames": True,
            "overwrites": True,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "extractor_retries": 2,
            "concurrent_fragment_downloads": 4,
            "max_filesize": self.cfg.max_bytes,
            "progress_hooks": [hook],
        }
        if self.cfg.cookies:
            opts["cookiefile"] = self.cfg.cookies
        if self.cfg.proxy:
            opts["proxy"] = self.cfg.proxy
        return opts

    async def _ytdlp(self, ctx: _Ctx) -> Result:
        return await asyncio.to_thread(self._ytdlp_sync, ctx)

    def _ytdlp_sync(self, ctx: _Ctx) -> Result:
        base = self._base_opts(ctx)
        try:
            # 1) Ma'lumot olish (yuklamasdan): jonli efir, davomiylik va hajmni tekshirish
            with yt_dlp.YoutubeDL({**base, "format": "bv*+ba/b*"}) as ydl:
                info = ydl.extract_info(ctx.url, download=False)
            if not info:
                raise DownloadError("not_found")
            if info.get("_type") == "playlist" and platform_of(ctx.url) in ("youtube", "soundcloud", "vk"):
                raise DownloadError("unsupported", "pleylist")  # 10 ta videoni birdan yuklamaymiz
            entries = _entries(info)
            if not entries:
                raise DownloadError("not_found", "entries yo'q")
            if any(e.get("is_live") for e in entries):
                raise DownloadError("live")
            duration = sum(e.get("duration") or 0 for e in entries) or None
            if self.cfg.max_duration and duration and duration > self.cfg.max_duration:
                raise DownloadError("too_long", f"{duration}s")

            # 2) Format tanlash va yuklash
            opts = dict(base)
            if ctx.kind == "audio":
                kbps = audio_bitrate(duration, self.cfg.max_bytes)
                opts.update({
                    "format": "ba/b",
                    "max_filesize": self.cfg.max_bytes * 4,  # manba kattaroq bo'lishi mumkin
                    "writethumbnail": True,
                    "postprocessors": [
                        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                         "preferredquality": str(kbps)},
                        {"key": "FFmpegMetadata", "add_metadata": True},
                        {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
                        {"key": "EmbedThumbnail", "already_have_thumbnail": False},
                    ],
                })
            else:
                if len(entries) == 1 and entries[0].get("formats"):
                    fmt, _ = choose_video_format(entries[0], self.cfg.max_bytes,
                                                 self.cfg.video_quality)
                else:
                    fmt = _video_selector()
                opts.update({
                    "format": fmt,
                    "format_sort": _format_sort(self.cfg.video_quality),
                    "merge_output_format": "mp4",
                })

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.process_ie_result(ydl.sanitize_info(info), download=True)
        except DownloadError:
            raise
        except _Timeout:
            raise DownloadError("timeout")
        except yt_dlp.utils.YoutubeDLError as e:
            if isinstance(getattr(e, "exc_info", (None, None))[1], _Timeout):
                raise DownloadError("timeout")
            raise DownloadError(classify_error(str(e)), str(e)[:500])

        paths = list_files(ctx.workdir)
        if ctx.kind == "audio":
            paths = [p for p in paths if kind_of(p) == "audio"]
        if not paths:
            # yt-dlp max_filesize'dan oshgan faylni jimgina tashlab ketadi
            raise DownloadError("too_big", "yt-dlp fayl qaytarmadi")

        first = entries[0]
        if ctx.kind == "audio":
            title = first.get("track") or clean_title(first)
            performer = first.get("artist") or first.get("creator") or first.get("uploader")
        else:
            title = clean_title(first if len(entries) == 1 else info)
            performer = None
        return Result(files=[MediaFile(p, kind_of(p)) for p in paths], title=title,
                      performer=performer)

    # ---------------- gallery-dl ----------------
    async def _gallery(self, ctx: _Ctx) -> Result:
        remaining = ctx.deadline - time.monotonic()
        if remaining <= 5:
            raise DownloadError("timeout")
        cmd = [
            sys.executable, "-m", "gallery_dl",
            "-D", ctx.workdir,
            "--range", "1-10",
            "--filesize-max", f"{self.cfg.max_mb}M",
            "--http-timeout", "30",
            "-R", "3",
            "--no-mtime",
            "--write-metadata",
            "-o", "output.progress=false",
        ]
        if self.cfg.cookies:
            cmd += ["-C", self.cfg.cookies]
        if self.cfg.proxy:
            cmd += ["--proxy", self.cfg.proxy]
        cmd += ["--", ctx.url]
        try:
            code, out, err = await _run(*cmd, timeout=remaining)
        except asyncio.TimeoutError:
            raise DownloadError("timeout")
        except OSError as e:
            raise DownloadError("failed", f"gallery-dl ishga tushmadi: {e}")

        paths = list_files(ctx.workdir)
        if not paths:
            raise DownloadError(classify_error(err or out or "failed"), (err or out)[-500:])
        if code != 0:
            log.info("gallery-dl qisman xato (%s): %s", code, err[-300:])
        return Result(files=[MediaFile(p, kind_of(p)) for p in paths],
                      title=_gallery_title(ctx.workdir))


_OWNER_TITLE_RE = re.compile(r"^(video|post|reel|photo|story)\s+(by|from)\s+\S+", re.IGNORECASE)


def clean_title(info: dict) -> str:
    """Sarlavhadan akkaunt egasining nomini olib tashlaydi.

    yt-dlp Instagram'da "Video by username", X/Twitter'da "Ism - matn" ko'rinishida beradi.
    """
    title = (info.get("title") or "").strip()
    description = (info.get("description") or "").strip()
    if not title or _OWNER_TITLE_RE.match(title):
        title = description.splitlines()[0].strip() if description else ""
    for name in (info.get("uploader"), info.get("channel"), info.get("uploader_id")):
        if name and title.lower().startswith(f"{name} - ".lower()):
            title = title[len(name) + 3:].strip()
    return title


def _entries(info: dict) -> list[dict]:
    if info.get("_type") in ("playlist", "multi_video"):
        return [e for e in (info.get("entries") or []) if e][:10]
    return [info]


def _gallery_title(workdir: str) -> str:
    for name in sorted(os.listdir(workdir)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(workdir, name), encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        for key in ("description", "content", "title", "desc"):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _clear(workdir: str) -> None:
    for name in os.listdir(workdir):
        path = os.path.join(workdir, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except OSError:
                pass


async def prepare_files(result: Result, max_bytes: int) -> list[MediaFile]:
    """Videolarni mp4 ga o'tkazadi, o'lchamlarini aniqlaydi va chegaradan katta fayllarni tashlaydi."""
    ready: list[MediaFile] = []
    for f in result.files:
        if f.kind == "video":
            f.path = await to_mp4(f.path)
            f.kind = kind_of(f.path)
            f.width, f.height, f.duration = await probe_video(f.path)
        if os.path.getsize(f.path) > max_bytes:
            log.info("Chegaradan katta fayl tashlandi: %s", f.path)
            continue
        ready.append(f)
    return ready


def versions() -> dict[str, str]:
    out = {"yt-dlp": yt_dlp.version.__version__}
    try:
        import gallery_dl.version

        out["gallery-dl"] = gallery_dl.version.__version__
    except ImportError:
        out["gallery-dl"] = "o'rnatilmagan"
    return out
