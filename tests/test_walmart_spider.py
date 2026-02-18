import os
import glob
import sys

# make project importable for tests
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# ensure inner package directory (walmart_scraper/walmart_scraper) is importable
PKG_DIR = os.path.join(ROOT, 'walmart_scraper')
if PKG_DIR not in sys.path:
    sys.path.insert(0, PKG_DIR)

import pytest
from scrapy.http import HtmlResponse

from walmart_scraper.spiders.walmart import WalmartSpider

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, '..'))
WALMART_DIR = os.path.join(ROOT, 'walmart_scraper')


def _load_latest_debug_html():
    pattern = os.path.join(WALMART_DIR, 'debug_wallet_*.html')
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not files:
        pytest.skip('no debug_wallet_*.html fixture present')
    with open(files[0], 'r', encoding='utf-8') as f:
        return f.read()


def test_parse_blocked_page_returns_no_items():
    html = _load_latest_debug_html()
    spider = WalmartSpider(search_term='wallet')
    response = HtmlResponse(url='https://www.walmart.com/search?q=wallet', body=html, encoding='utf-8')

    results = list(spider.parse(response))
    # blocked page should not produce product items
    assert len(results) == 0


def test_start_requests_uses_storage_state_if_present(tmp_path, monkeypatch):
    # create a fake storage state file in the package dir and ensure spider
    # attaches playwright_context to the Request.meta
    import importlib
    from pathlib import Path

    # locate the module's package directory so the spider finds the file
    mod = importlib.import_module('walmart_scraper.spiders.walmart')
    pkg_dir = Path(mod.__file__).resolve().parents[1]
    storage_file = pkg_dir / 'walmart_storage.json'

    # write a minimal storage-state file
    storage_file.write_text('{"origins": []}', encoding='utf-8')

    spider = WalmartSpider(search_term='wallet')
    req = next(spider.start_requests())
    assert req.meta.get('playwright') is True
    assert 'playwright_context' in req.meta
    assert req.meta['playwright_context'].get('storageState') == str(storage_file)

    # cleanup
    storage_file.unlink()


def test_parse_simple_product_snippet():
    html = '''
    <html><body>
      <div data-item-id="1">
        <a href="/ip/1"><span data-automation-id="product-title">Test Product</span></a>
        <div data-automation-id="product-price"><div>$12.34</div></div>
        <img data-testid="productTileImage" src="https://example.com/img.jpg" />
      </div>
    </body></html>
    '''
    spider = WalmartSpider(search_term='test')
    response = HtmlResponse(url='https://www.walmart.com/search?q=test', body=html, encoding='utf-8')

    results = list(spider.parse(response))
    assert len(results) == 1
    r = results[0]
    assert r['name'] == 'Test Product'
    assert abs(r['price'] - 12.34) < 1e-6
    assert r['image'] == 'https://example.com/img.jpg'
    assert '/ip/1' in r['link'] or 'https://www.walmart.com/ip/1' in r['link']


def test_detail_page_enrichment():
    list_html = '''
    <html><body>
      <div data-item-id="1">
        <a href="https://www.walmart.com/ip/1"><span class="normal"></span></a>
        <span class="f3"></span>
        <img src="" />
      </div>
    </body></html>
    '''
    detail_html = '''
    <html><body>
      <h1 class="prod-ProductTitle">Wallet Detail</h1>
      <meta itemprop="price" content="49.99" />
      <img class="prod-hero-image" src="https://example.com/detail.jpg" />
    </body></html>
    '''

    spider = WalmartSpider(search_term='wallet')
    list_resp = HtmlResponse(url='https://www.walmart.com/search?q=wallet', body=list_html, encoding='utf-8')

    # parse the list page to get the Request object for the detail page
    reqs = list(spider.parse(list_resp))
    assert len(reqs) == 1
    req = reqs[0]
    assert isinstance(req, type(list_resp.request)) or hasattr(req, 'meta')

    # simulate a detail page response and call parse_product_detail
    from scrapy import Request
    request = Request(url='https://www.walmart.com/ip/1', meta={'partial_item': {'link': 'https://www.walmart.com/ip/1'}})
    detail_resp = HtmlResponse(url='https://www.walmart.com/ip/1', request=request, body=detail_html, encoding='utf-8')
    enriched = list(spider.parse_product_detail(detail_resp))[0]
    assert enriched['name'] == 'Wallet Detail'
    assert abs(enriched['price'] - 49.99) < 1e-6
    assert enriched['image'] == 'https://example.com/detail.jpg'


def test_parse_two_wallet_products_respects_limit():
    html = '''
    <html><body>
      <div data-item-id="1">
        <a href="/ip/1"><span data-automation-id="product-title">Wallet A</span></a>
        <div data-automation-id="product-price"><div>$10.00</div></div>
        <img data-testid="productTileImage" src="https://example.com/a.jpg" />
      </div>
      <div data-item-id="2">
        <a href="/ip/2"><span data-automation-id="product-title">Wallet B</span></a>
        <div data-automation-id="product-price"><div>$20.00</div></div>
        <img data-testid="productTileImage" src="https://example.com/b.jpg" />
      </div>
      <div data-item-id="3">
        <a href="/ip/3"><span data-automation-id="product-title">Wallet C</span></a>
        <div data-automation-id="product-price"><div>$30.00</div></div>
        <img data-testid="productTileImage" src="https://example.com/c.jpg" />
      </div>
    </body></html>
    '''
    spider = WalmartSpider(search_term='wallet', num_products=2)
    response = HtmlResponse(url='https://www.walmart.com/search?q=wallet', body=html, encoding='utf-8')

    results = list(spider.parse(response))
    # should respect the limit and return exactly 2 products
    assert len(results) == 2
    assert results[0]['name'] == 'Wallet A'
    assert results[1]['name'] == 'Wallet B'
