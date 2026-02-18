import os
import glob
import sys

# make project importable for tests
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# ensure inner package directory (walmart_scraper/walmart_scraper) is importable
PKG_DIR = os.path.join(ROOT, 'walmart_scraper')
if PKG_DIR not in sys.path:
    sys.path.insert(0, PKG_DIR)

import json
import pytest

from app import detect_captcha


def _load_debug_html():
    files = glob.glob('walmart_scraper/debug_wallet_*.html')
    if not files:
        pytest.skip('no debug HTML saved (run a scrape with debug=true)')
    with open(files[0], 'r', encoding='utf-8') as f:
        return f.read()


def test_detect_captcha_on_blocked_page():
    html = _load_debug_html()
    assert detect_captcha(html) is True


def test_detect_captcha_negative():
    assert not detect_captcha('<html><body><div>normal content</div></body></html>')
