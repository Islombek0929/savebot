"""DNS zaxirasi (DNS-over-HTTPS) testlari — tarmoqsiz, soxta javoblar bilan."""
import io
import json
import socket

import pytest

from savebot import dnsfix


@pytest.fixture(autouse=True)
def clean_cache():
    dnsfix._cache.clear()
    dnsfix._doh_first.clear()
    yield
    dnsfix._cache.clear()
    dnsfix._doh_first.clear()


def fake_system(blocked):
    real = dnsfix._original_getaddrinfo

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if host in blocked:
            raise socket.gaierror(-3, "Temporary failure in name resolution")
        return real(host, port, family, type, proto, flags)
    return getaddrinfo


def test_fallback_used_only_when_system_dns_fails(monkeypatch):
    monkeypatch.setattr(dnsfix, "_original_getaddrinfo",
                        fake_system({"instagram.ftas2-2.fna.fbcdn.net"}))
    asked = []

    def fake_query(name, timeout=5.0):
        asked.append(name)
        return ["157.240.1.1"]

    monkeypatch.setattr(dnsfix, "doh_query", fake_query)
    res = dnsfix._getaddrinfo("instagram.ftas2-2.fna.fbcdn.net", 443, 0, socket.SOCK_STREAM)
    assert res[0][4][0] == "157.240.1.1" and res[0][4][1] == 443
    assert asked == ["instagram.ftas2-2.fna.fbcdn.net"]
    dnsfix._getaddrinfo("127.0.0.1", 80)  # ishlayotgan nomlar uchun DoH so'ralmaydi
    assert asked == ["instagram.ftas2-2.fna.fbcdn.net"]


def test_fallback_raises_original_error_when_doh_fails(monkeypatch):
    monkeypatch.setattr(dnsfix, "_original_getaddrinfo", fake_system({"nope.example"}))
    monkeypatch.setattr(dnsfix, "doh_query", lambda name, timeout=5.0: [])
    with pytest.raises(socket.gaierror):
        dnsfix._getaddrinfo("nope.example", 443)


def test_doh_query_parses_and_caches(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=None, context=None):
        calls.append(req.full_url)
        if "1.1.1.1" in req.full_url:
            raise OSError("blocked")  # birinchi server ishlamasa — keyingisi
        body = {"Status": 0, "Answer": [
            {"name": "x.com.", "type": 5, "TTL": 100, "data": "alias.x.com."},
            {"name": "alias.x.com.", "type": 1, "TTL": 120, "data": "1.2.3.4"},
        ]}
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(dnsfix.urllib.request, "urlopen", fake_urlopen)
    assert dnsfix.doh_query("x.com") == ["1.2.3.4"]
    assert "8.8.8.8/resolve?name=x.com" in calls[-1]
    n = len(calls)
    assert dnsfix.resolve("x.com") == ["1.2.3.4"] and len(calls) == n  # keshdan


def test_install_respects_env(monkeypatch):
    monkeypatch.setattr(dnsfix, "_installed", False)
    monkeypatch.setenv("DOH_FALLBACK", "0")
    original = socket.getaddrinfo
    dnsfix.install()
    assert socket.getaddrinfo is original


def test_gethostbyname_fallback(monkeypatch):
    def failing(host):
        raise socket.gaierror(-3, "Temporary failure in name resolution")

    monkeypatch.setattr(dnsfix, "_original_gethostbyname", failing)
    monkeypatch.setattr(dnsfix, "doh_query", lambda name, timeout=5.0: ["84.54.107.98"])
    assert dnsfix._gethostbyname("instagram.ftas2-2.fna.fbcdn.net") == "84.54.107.98"
    with pytest.raises(socket.gaierror):
        dnsfix._gethostbyname("localhost")


def test_after_one_failure_same_domain_skips_slow_system_dns(monkeypatch):
    system_calls = []

    def slow_failing(host, port, family=0, type=0, proto=0, flags=0):
        system_calls.append(host)
        if host.endswith("fbcdn.net"):
            raise socket.gaierror(-3, "Temporary failure in name resolution")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, port))]

    monkeypatch.setattr(dnsfix, "_original_getaddrinfo", slow_failing)
    monkeypatch.setattr(dnsfix, "doh_query", lambda name, timeout=5.0: ["84.54.107.98"])
    dnsfix._getaddrinfo("instagram.ftas2-2.fna.fbcdn.net", 443)
    assert "instagram.ftas2-2.fna.fbcdn.net" in system_calls
    system_calls.clear()
    res = dnsfix._getaddrinfo("instagram.ftas2-1.fna.fbcdn.net", 443)  # boshqa server, o'sha domen
    assert res[0][4][0] == "84.54.107.98"
    assert "instagram.ftas2-1.fna.fbcdn.net" not in system_calls  # tizim DNS kutilmadi
    dnsfix._getaddrinfo("api.telegram.org", 443)  # boshqa domenlar odatdagidek
    assert "api.telegram.org" in system_calls
