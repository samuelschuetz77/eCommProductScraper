import random
import scrapy
from scrapy_playwright.page import PageMethod

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

    def __init__(self, search_term=None, min_price=None, max_price=None, num_products=None, *args, **kwargs):
        super(WalmartSpider, self).__init__(*args, **kwargs)
        self.search_term = search_term
        self.min_price = float(min_price) if min_price else 0
        self.max_price = float(max_price) if max_price else float('inf')
        self.num_products = int(num_products) if num_products else 2

    def start_requests(self):
        url = f"https://www.walmart.com/search?q={self.search_term}"

        # rotate a plausible user-agent and set Accept-Language header
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept-Language': 'en-US,en;q=0.9',
        }

        # Playwright page-method sequence to mimic a brief human session and
        # attempt to load lazy content (scrolling) so we can find more items.
        # scroll-until-ready evaluator: repeatedly scroll until the page
        # contains at least `num_products` product nodes or the timeout elapses.
        scroll_eval = (
            "async (target) => {\n"
            "  const start = Date.now();\n"
            "  const timeout = 15000;\n"
            "  const selector = 'div[data-item-id], div.search-result-gridview-item-wrapper, div.product-grid-list-view';\n"
            "  while (Date.now() - start < timeout) {\n"
            "    const n = document.querySelectorAll(selector).length;\n"
            "    if (n >= target) return true;\n"
            "    window.scrollBy(0, window.innerHeight);\n"
            "    await new Promise(r => setTimeout(r, 500));\n"
            "  }\n"
            "  return false;\n"
            "}"
        )

        # add a slightly longer timeout for pages that load slowly
        playwright_page_methods = [
            PageMethod("set_viewport_size", {"width": 1280, "height": 900}),
            PageMethod("goto", "https://www.walmart.com"),
            PageMethod("wait_for_timeout", 700),
            PageMethod("goto", url, {"wait_until": "domcontentloaded", "timeout": 60000}),
            PageMethod("wait_for_selector", "body", {"timeout": 60000}),
            PageMethod("evaluate", scroll_eval, self.num_products),
            PageMethod("wait_for_timeout", 1200),
        ]

        # reuse a previously saved Playwright storage state (if present) so we can
        # continue a session that was manually solved via /captcha/interactive
        try:
            from pathlib import Path
            base = Path(__file__).resolve().parents[1]
            storage_file = base / 'walmart_storage.json'
            playwright_context = {'storageState': str(storage_file)} if storage_file.exists() else None
        except Exception:
            storage_file = None
            playwright_context = None

        meta = dict(
            playwright=True,
            playwright_page_methods=playwright_page_methods,
        )
        if playwright_context:
            meta['playwright_context'] = playwright_context

        yield scrapy.Request(
            url,
            headers=headers,
            meta=meta,
        )

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

    def parse(self, response):
        count = 0
        # prefer explicit product containers, but accept several variants
        product_nodes = response.css("div[data-item-id], div.search-result-gridview-item-wrapper, div.product-grid-list-view")
        self.logger.info('Found %d product nodes on page', len(product_nodes))

        for product in product_nodes:
            if count >= self.num_products:
                break

            name = self._first_text(product, 'span.normal::text', 'a.product-title-link::text', 'h2.product-title::text')
            price_txt = self._first_text(product, 'span.f3::text', 'span.price-characteristic::attr(content)', 'span.price-main::text', 'meta[itemprop="price"]::attr(content)')
            price = self._parse_price(price_txt)

            # image handling: try several attributes (may be lazy-loaded)
            image = (product.css('img::attr(src)').get()
                     or product.css('img::attr(data-src)').get()
                     or (product.css('img::attr(srcset)').get() or '').split(',')[0].split(' ')[0]
                     or None)

            link = product.css('a::attr(href)').get()
            link = response.urljoin(link) if link else None

            # collect additional thumbnail URLs if present on the list card
            thumbs = [
                v.strip() for v in (
                    product.css('img::attr(srcset)').get() or ''
                ).split(',') if v.strip()
            ]
            images = [image] + thumbs if image else thumbs

            incomplete = False
            missing = []
            if not name:
                missing.append('name')
            if price is None:
                missing.append('price')
            if not image:
                missing.append('image')
            if not link:
                missing.append('link')
            if missing:
                incomplete = True

            item = {
                'name': name,
                'price': price,
                'image': image,
                'images': images if images else [],
                'link': link,
                'incomplete': incomplete,
                'missing_fields': missing,
            }

            if incomplete:
                self.logger.debug('Incomplete item found (may be placeholder/ad): %s', missing)

                # If we have a link, follow the product detail page to try and fill
                # missing fields — more reliable for title/price/image.
                if link:
                    self.logger.info('Following detail page to enrich incomplete item: %s', link)
                    detail_methods = [
                        PageMethod("set_viewport_size", {"width": 1200, "height": 900}),
                        PageMethod("goto", link, {"wait_until": "domcontentloaded"}),
                        PageMethod("wait_for_selector", "body"),
                        PageMethod("wait_for_timeout", 500),
                    ]
                    yield scrapy.Request(link, callback=self.parse_product_detail, meta={
                        'playwright': True,
                        'playwright_page_methods': detail_methods,
                        'partial_item': item,
                    })
                    continue

            # always yield items (we'll mark completeness later in DB); this lets us
            # capture entries that might be missing prices but have useful info.
            self.logger.info('Yielding item link=%s name=%s price=%s incomplete=%s', link, name, price, incomplete)
            yield item
            count += 1

        if count == 0:
            self.logger.info('No items yielded from parse — page may be blocked or selectors need updating')

    def parse_product_detail(self, response):
        """Parse a product detail page to enrich a previously yielded partial
        item. Expects `partial_item` in `response.meta`.
        """
        partial = response.meta.get('partial_item', {})
        self.logger.debug('Parsing product detail for %s', partial.get('link'))

        # fallback selectors on product detail pages (also collect gallery thumbnails)
        name = (self._first_text(response, 'h1.prod-ProductTitle::text', 'h1[itemprop="name"]::text', 'h1::text') or partial.get('name'))
        price_txt = (self._first_text(response, 'span.price-characteristic::attr(content)', 'meta[itemprop="price"]::attr(content)', 'span.price::text') or '')
        price = self._parse_price(price_txt) if price_txt else partial.get('price')

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

        self.logger.info('Yielding enriched item: %s (incomplete=%s)', merged.get('link'), merged.get('incomplete'))
        yield merged
