"""The repo, its history and the sdist are public: fixtures must not describe a real install.

See "Public repo hygiene" in CLAUDE.md. Fixtures are scrubbed live captures, so this
checks the parts a machine can check: addresses, emails and UTC offsets. Hand-written
canaries in test code may use any address; fixtures may not.
"""
import ipaddress
import re
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
FIXTURES = TESTS / "fixtures"

_ALLOWED_NETS = [
    ipaddress.ip_network(n)
    for n in ("0.0.0.0/32", "127.0.0.0/8", "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
]
_ALLOWED_EMAIL_DOMAINS = re.compile(
    r"(^|\.)(example|example\.com|example\.net|example\.org|test|invalid|localhost)$"
    r"|^users\.noreply\.github\.com$"
)
_IPV4 = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.])")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
_OFFSET = re.compile(r"T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?([+-]\d{2}:\d{2})")


def ip_violations(text: str) -> list[str]:
    found = []
    for raw in _IPV4.findall(text):
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            continue  # a dotted version string such as 4.0.15.2941
        if not any(addr in net for net in _ALLOWED_NETS):
            found.append(raw)
    return found


def email_violations(text: str) -> list[str]:
    return [m.group(0) for m in _EMAIL.finditer(text)
            if not _ALLOWED_EMAIL_DOMAINS.search(m.group(1).lower())]


def offset_violations(text: str) -> list[str]:
    return [o for o in _OFFSET.findall(text) if o not in ("+00:00", "-00:00")]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


_FIXTURE_FILES = sorted(p for p in FIXTURES.rglob("*") if p.is_file())
_TEST_FILES = sorted(TESTS.rglob("*.py")) + _FIXTURE_FILES


# The detectors themselves: each must flag a planted value and pass a safe one.

def test_ip_detector():
    assert ip_violations('"host": "10.20.30.40", "v": "4.0.15.2941"') == ["10.20.30.40"]
    assert ip_violations('"url": "http://10.20.30.40:8989"') == ["10.20.30.40"]
    assert ip_violations('"tag": "v12.0.5.0", "zip": "plugin-v1.2.0.1.zip"') == []
    assert ip_violations('"a": "192.0.2.10", "b": "0.0.0.0", "c": "127.0.0.1"') == []


def test_email_detector():
    personal = "me@" + "personal-mail.net"  # split, or the repo scan below flags this file
    assert email_violations(f"{personal} x@vpn.example y@host.test") == [personal]
    assert email_violations("1+me@users.noreply.github.com") == []


def test_offset_detector():
    assert offset_violations('"2026-01-02T03:04:05+11:00"') == ["+11:00"]
    assert offset_violations('"2026-01-02T03:04:05.123+00:00", "2026-01-02T03:04:05Z"') == []


# The repo.

@pytest.mark.parametrize("path", _FIXTURE_FILES, ids=lambda p: p.name)
def test_fixture_has_only_documentation_addresses(path):
    assert ip_violations(_read(path)) == []


@pytest.mark.parametrize("path", _FIXTURE_FILES, ids=lambda p: p.name)
def test_fixture_has_only_utc_offsets(path):
    assert offset_violations(_read(path)) == []


@pytest.mark.parametrize("path", _TEST_FILES, ids=lambda p: p.relative_to(TESTS).as_posix())
def test_tests_have_only_example_emails(path):
    assert email_violations(_read(path)) == []
