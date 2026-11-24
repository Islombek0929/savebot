import pytest

from savebot.downloader import (
    classify_error,
    clean_title,
    find_url,
    is_audio_site,
    is_public_url,
    normalize_url,
    platform_of,
    prefers_gallery,
)


@pytest.mark.parametrize("text,expected", [
    ("qara https://www.instagram.com/reel/Cxyz123/?igsh=abc.", "https://www.instagram.com/reel/Cxyz123/?igsh=abc"),
    ("(https://vm.tiktok.com/ZMabc/)", "https://vm.tiktok.com/ZMabc/"),
    ("instagram.com/p/ABC/ shu", "https://instagram.com/p/ABC/"),
    ("youtu.be/dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ"),
    ("salom", None),
    ("email@instagram.com", None),
])
def test_find_url(text, expected):
    assert find_url(text) == expected


@pytest.mark.parametrize("url,platform", [
    ("https://www.instagram.com/reel/x/", "instagram"),
    ("https://vt.tiktok.com/abc/", "tiktok"),
    ("https://m.youtube.com/watch?v=1", "youtube"),
    ("https://youtu.be/abc", "youtube"),
    ("https://x.com/a/status/1", "twitter"),
    ("https://pin.it/abc", "pinterest"),
    ("https://ru.pinterest.com/pin/1/", "pinterest"),
    ("https://fb.watch/abc/", "facebook"),
    ("https://www.threads.net/@a/post/1", "threads"),
    ("https://example.com/v.mp4", "example.com"),
    ("https://notinstagram.com/x", "notinstagram.com"),
])
def test_platform_of(url, platform):
    assert platform_of(url) == platform


def test_normalize_strips_tracking():
    a = normalize_url("https://www.instagram.com/reel/ABC/?igsh=1&utm_source=ig")
    b = normalize_url("https://instagram.com/reel/ABC")
    assert a == b == "https://instagram.com/reel/ABC"


def test_normalize_youtube_variants_equal():
    variants = [
        "https://youtu.be/dQw4w9WgXcQ?si=xyz",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s",
        "https://m.youtube.com/watch?feature=share&v=dQw4w9WgXcQ",
        "https://youtube.com/shorts/dQw4w9WgXcQ?feature=share",
    ]
    assert {normalize_url(v) for v in variants} == {"https://youtube.com/watch?v=dQw4w9WgXcQ"}


def test_normalize_keeps_query_for_unknown_sites():
    assert normalize_url("https://site.com/video?id=5") == "https://site.com/video?id=5"
    assert normalize_url("https://www.facebook.com/watch/?v=123&ref=x") == "https://facebook.com/watch?v=123"


def test_format_choice_and_gallery():
    assert is_audio_site("https://music.youtube.com/watch?v=abc")
    assert not is_audio_site("https://youtu.be/abc")
    assert prefers_gallery("https://www.tiktok.com/@u/photo/123")
    assert prefers_gallery("https://www.instagram.com/p/ABC/")
    assert not prefers_gallery("https://www.instagram.com/reel/ABC/")


def test_clean_title_removes_owner():
    assert clean_title({"title": "Video by some.user", "description": "Ajoyib kun\n#tag"}) == "Ajoyib kun"
    assert clean_title({"title": "Elon - hello world", "uploader": "Elon"}) == "hello world"
    assert clean_title({"title": "Oddiy sarlavha"}) == "Oddiy sarlavha"
    assert clean_title({"title": "Post by x"}) == ""


@pytest.mark.parametrize("msg,code", [
    ("ERROR: [Instagram] abc: Requested content is not available, rate-limit reached or login required", "private"),
    ("ERROR: Unsupported URL: https://x.y", "unsupported"),
    ("ERROR: Unsupported URL: https://site.com/page.html", "unsupported"),
    ("ERROR: Sign in to confirm your age", "private"),
    ("ERROR: [youtube] x: Video unavailable", "not_found"),
    ("ERROR: something weird", "failed"),
])
def test_classify_error(msg, code):
    assert classify_error(msg) == code


@pytest.mark.parametrize("url", [
    "http://localhost:8081/file",
    "http://127.0.0.1/x",
    "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.5/v.mp4",
    "http://[::1]/x",
    "ftp://example.com/x",
    "file:///etc/passwd",
])
async def test_is_public_url_blocks_internal(url):
    assert not await is_public_url(url)


async def test_is_public_url_allows_public_ip():
    assert await is_public_url("https://8.8.8.8/video.mp4")


def test_texts_complete_and_guess():
    from savebot.texts import _T, LANGS, guess_lang, progress_bar
    for key, variants in _T.items():
        assert set(variants) == set(LANGS), key  # har bir matn 3 tilda bor
    assert guess_lang("ru") == "ru" and guess_lang("kk") == "ru" and guess_lang("uz") == "uz"
    assert guess_lang("en-US") == "en" and guess_lang(None) == "uz"
    assert progress_bar(50) == "▰▰▰▰▰▱▱▱▱▱"
