import json
import random
import scrapy
from scrapy_playwright.page import PageMethod
from datetime import datetime

USER_AGENTS = [
    # small rotation of realistic desktop UA strings
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
]


class WalmartSpider(scrapy.Spider):
    name = "walmart"
    allowed_domains = ["walmart.com"]

    def __init__(self, search_term='laptop', min_price=0, max_price=float('inf'), num_products=10, *args, **kwargs):
        super(WalmartSpider, self).__init__(*args, **kwargs)
        self.search_term = search_term
        self.min_price = float(min_price) if min_price else 0
        self.max_price = float(max_price) if max_price else float('inf')
        self.num_products = int(num_products)
        self.results_found = 0

    def _first_text(self, el, *selectors):
        for s in selectors:
            v = el.css(s).get()
            if v:
                return v.strip()
        return None

    def _parse_price(self, txt):
        if not txt:
            return None
        import re
        m = re.search(r"[\d,]+(?:\.\d+)?", txt)
        if not m:
            return None
        try:
            return float(m.group(0).replace(',', ''))
        except Exception:
            return None

    def start_requests(self):
        url = f"https://www.walmart.com/search?q={self.search_term}"
        
        # 1. Reuse storage state if available (manual captcha solve)
        meta = {
            "playwright": True,
            "playwright_include_page": True, # Vital for debugging
            "playwright_page_methods": [
                PageMethod("wait_for_selector", "div#main-content, script[id='__NEXT_DATA__']", {"timeout": 30000}),
                # Scroll a bit to trigger lazy loading if we fall back to DOM scraping
                PageMethod("evaluate", "window.scrollBy(0, document.body.scrollHeight)"),
                PageMethod("wait_for_timeout", 2000), 
            ],
        }

        # Check for storage state (look in the package directory so tests and runs agree)
        from pathlib import Path
        base = Path(__file__).resolve().parents[1]
        storage_path = base / 'walmart_storage.json'
        if storage_path.exists():
            meta["playwright_context"] = {"storageState": str(storage_path)}
            self.logger.info("Loaded manual captcha session.")

        yield scrapy.Request(url, meta=meta, callback=self.parse)

    def parse(self, response):
        # `response.meta` may not exist in unit tests (Response not tied to a Request).
        try:
            resp_meta = response.meta
        except AttributeError:
            resp_meta = {}

        page = resp_meta.get("playwright_page")
        
        # METHOD A: The "Precision" Method (JSON Data)
        # Walmart injects the entire product state into a script tag. 
        # Extracting this is clean, fast, and gives 100% accurate data.
        next_data = response.xpath('//script[@id="__NEXT_DATA__"]/text()').get()
        
        if next_data:
            self.logger.info("Found __NEXT_DATA__ JSON blob. Extracting structured data...")
            try:
                data = json.loads(next_data)
                # Navigate the JSON Jungle
                props = data.get('props', {}).get('pageProps', {}).get('initialData', {}).get('searchResult', {}).get('itemStacks', [])
                
                items = []
                for stack in props:
                    items.extend(stack.get('items', []))

                for item in items:
                    if self.results_found >= self.num_products: break
                    if item.get('__typename') != 'Product': continue

                    product = {
                        'name': item.get('name'),
                        'price': item.get('priceInfo', {}).get('currentPrice', {}).get('price'),
                        'image': item.get('image'),
                        'link': f"https://www.walmart.com{item.get('canonicalUrl', '')}",
                        'source': 'json_extraction'
                    }

                    # Filter Logic
                    if product['price']:
                        p = float(product['price'])
                        if p < self.min_price or p > self.max_price:
                            continue

                    self.results_found += 1
                    yield product
                
                return # Exit if JSON method worked
            except Exception as e:
                self.logger.error(f"JSON extraction failed: {e}. Falling back to DOM.")

        # METHOD B: The "Brute Force" Method (DOM Scraping)
        # Updated selectors for 2025 structure
        self.logger.info("Falling back to DOM scraping...")
        
        # Selectors: These are more robust than '.normal'
        product_cards = response.css('div[data-item-id]')
        
        if not product_cards:
            self.logger.warning("No product cards found. Possible Captcha or Layout change.")
            # Dump HTML for debugging
            from pathlib import Path
            debug_path = Path(__file__).parent.parent.parent / f"debug_failed_{datetime.now().timestamp()}.html"
            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write(response.text)
            self.logger.info(f"Saved debug HTML to {debug_path}")
            return

        for card in product_cards:
            if self.results_found >= self.num_products: break

            # Try multiple selectors for each field
            name = (card.css('span[data-automation-id="product-title"]::text').get() or 
                    card.css('a span.w_iUH7::text').get() or 
                    card.css('.f6.f5-l::text').get())
            
            price_text = (card.css('div[data-automation-id="product-price"] div::text').get() or 
                          card.css('.aa88::text').get() or 
                          "0")
            
            # Clean price
            import re
            price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
            price = float(price_match.group(1).replace(',', '')) if price_match else 0

            image = (card.css('img[data-testid="productTileImage"]::attr(src)').get() or 
                     card.css('img::attr(src)').get())
            
            link = card.css('a::attr(href)').get()
            if link and not link.startswith('http'):
                link = "https://www.walmart.com" + link

            # detect missing fields so we can optionally follow the detail page
            missing = []
            if not name:
                missing.append('name')
            if not price:
                missing.append('price')
            if not image:
                missing.append('image')
            if not link:
                missing.append('link')

            # if critical fields missing, follow the detail page to enrich
            if missing and link:
                self.logger.info('Missing fields on list card — following detail for %s missing=%s', link, missing)
                detail_methods = [
                    PageMethod("set_viewport_size", {"width": 1200, "height": 900}),
                    PageMethod("goto", link, {"wait_until": "domcontentloaded"}),
                    PageMethod("wait_for_selector", "body"),
                    PageMethod("wait_for_timeout", 500),
                ]
                partial = {
                    'name': name,
                    'price': price,
                    'image': image,
                    'link': link,
                    'incomplete': True,
                    'missing_fields': missing,
                }
                yield scrapy.Request(link, callback=self.parse_product_detail, meta={
                    'playwright': True,
                    'playwright_page_methods': detail_methods,
                    'partial_item': partial,
                })
                continue

            if price < self.min_price or price > self.max_price:
                continue

            self.results_found += 1
            yield {
                'name': name.strip() if name else 'Unknown',
                'price': price,
                'image': image,
                'link': link,
                'source': 'dom_scrape'
            }

    def parse_product_detail(self, response):
        """Parse a product detail page to enrich a previously yielded partial
        item. Expects `partial_item` in `response.meta`.
        """
        partial = response.meta.get('partial_item', {})
        self.logger.debug('Parsing product detail for %s', partial.get('link'))

        # fallback selectors on product detail pages (also collect gallery thumbnails)
        name = (self._first_text(response, 'h1.prod-ProductTitle::text', 'h1[itemprop="name"]::text', 'h1::text') or partial.get('name'))
        price_txt = (self._first_text(response, 'span.price-characteristic::attr(content)', 'meta[itemprop="price"]::attr(content)', 'span.price::text') or '')
        price = None
        if price_txt:
            price = float(price_txt) if price_txt.replace('.','',1).isdigit() else None
        else:
            price = partial.get('price')

        # gather hero + gallery images (src and srcset)
        images = []
        hero = response.css('img.prod-hero-image::attr(src)').get() or response.css('img[itemprop="image"]::attr(src)').get()
        if hero:
            images.append(hero)
        # common gallery/thumb selectors
        for sel in ['ul.slider-list img::attr(src)', 'div.carousel img::attr(src)', 'div.thumbnail-list img::attr(src)', 'img[itemprop="image"]::attr(src)', 'img::attr(srcset)']:
            for v in response.css(sel).getall():
                if v:
                    if ',' in v:
                        # pick first src from srcset
                        first = v.split(',')[0].strip().split(' ')[0]
                        images.append(first)
                    else:
                        images.append(v)

        # fallback to any img tags in the product area
        if not images:
            for v in response.css('div.product-image-gallery img::attr(src)').getall():
                if v:
                    images.append(v)

        image = images[0] if images else partial.get('image')
        description = self._first_text(response, 'div.about-desc::text', 'div.prod-product-about div::text', 'meta[name="description"]::attr(content)') or partial.get('description')


        merged = {
            'name': name,
            'price': price,
            'image': image,
            'link': partial.get('link') or response.url,
            'description': description or partial.get('description'),
        }

        missing = [k for k, v in merged.items() if k in ('name','price','image','link') and not v]
        merged['incomplete'] = bool(missing)
        merged['missing_fields'] = missing

        if merged['incomplete']:
            self.logger.warning('Detail page parse still incomplete for %s — missing=%s', merged['link'], missing)
        else:
            self.logger.info('Enriched item from detail page: %s', merged['link'])

        yield merged
