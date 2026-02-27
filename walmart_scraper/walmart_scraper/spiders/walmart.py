import json
import random
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy
from scrapy_playwright.page import PageMethod

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
]


class WalmartSpider(scrapy.Spider):
    name = "walmart"
    allowed_domains = ["walmart.com"]

    custom_settings = {
        "LOG_LEVEL": "DEBUG",
    }

    def __init__(
        self,
        search_term="laptop",
        min_price=0,
        max_price=float("inf"),
        num_products=10,
        scrape_run_id=None,
        max_pages=8,
        *args,
        **kwargs,
    ):
        super(WalmartSpider, self).__init__(*args, **kwargs)
        self.search_term = search_term
        self.min_price = float(min_price) if min_price else 0
        self.max_price = float(max_price) if max_price else float("inf")
        self.num_products = int(num_products)
        self.max_pages = max(1, int(max_pages))
        self.scrape_run_id = scrape_run_id or f"run-{int(datetime.utcnow().timestamp())}"
        self.results_found = 0
        self.seen_links = set()
        self.pages_processed = 0
        self.card_attempts = 0

    def _log(self, level, message, **ctx):
        base = {
            "run_id": self.scrape_run_id,
            "search_term": self.search_term,
            "found": self.results_found,
            "target": self.num_products,
            "pages_processed": self.pages_processed,
        }
        base.update(ctx)
        context = " ".join(f"{k}={base[k]!r}" for k in sorted(base.keys()))
        getattr(self.logger, level)(f"{message} | {context}")

    def _first_text(self, el, *selectors):
        for s in selectors:
            v = el.css(s).get()
            if v:
                return v.strip()
        return None

    def _parse_price(self, txt):
        if not txt:
            return None
        m = re.search(r"[\d,]+(?:\.\d+)?", txt)
        if not m:
            return None
        try:
            return float(m.group(0).replace(",", ""))
        except Exception:
            return None

    def _attempt_extract(self, node, field_name, attempts, card_idx=None):
        """Try selectors in order and emit attempt-level logs.

        attempts format: [{"selector": "...", "extract": "text|attr|all_attr", "attr": "src"}]
        """
        for attempt_idx, attempt in enumerate(attempts, start=1):
            selector = attempt["selector"]
            extract_mode = attempt.get("extract", "text")
            attr = attempt.get("attr")
            value = None
            err = None
            try:
                if extract_mode == "text":
                    value = node.css(selector).get()
                    value = value.strip() if isinstance(value, str) else value
                elif extract_mode == "attr":
                    if not attr:
                        raise ValueError("attr extraction requires attr key")
                    value = node.css(f"{selector}::attr({attr})").get()
                    value = value.strip() if isinstance(value, str) else value
                elif extract_mode == "all_attr":
                    if not attr:
                        raise ValueError("all_attr extraction requires attr key")
                    value = [v.strip() for v in node.css(f"{selector}::attr({attr})").getall() if v and v.strip()]
                else:
                    raise ValueError(f"unsupported extract mode: {extract_mode}")
            except Exception as e:
                err = str(e)

            ok = bool(value)
            self._log(
                "debug",
                "field extraction attempt",
                field=field_name,
                card_index=card_idx,
                attempt=attempt_idx,
                selector=selector,
                extract=extract_mode,
                success=ok,
                error=err,
            )
            if ok:
                return value, attempt_idx
        return None, None

    def _extract_shipping(self, node, card_idx=None):
        shipping_attempts = [
            {"selector": 'span[data-automation-id="fulfillment-badge"]', "extract": "text"},
            {"selector": 'div[data-testid="shippingMessage"]', "extract": "text"},
            {"selector": 'span:contains("shipping")', "extract": "text"},
        ]
        shipping, attempt_idx = self._attempt_extract(node, "shipping", shipping_attempts, card_idx=card_idx)
        if shipping:
            self._log("info", "shipping extracted", card_index=card_idx, attempt=attempt_idx, value=shipping[:140])
        else:
            self._log("warning", "shipping extraction failed on card", card_index=card_idx)
        return shipping

    def _normalize_link(self, link):
        if not link:
            return None
        if link.startswith("http"):
            return link
        return f"https://www.walmart.com{link}"

    def _is_price_allowed(self, price):
        if price is None:
            return False
        return self.min_price <= float(price) <= self.max_price

    def _required_missing(self, product):
        required_fields = ("name", "price", "image", "link")
        return [k for k in required_fields if not product.get(k)]

    def _is_valid_product(self, product):
        if self._required_missing(product):
            return False
        return self._is_price_allowed(product.get("price"))

    def _extract_images_from_response(self, response):
        images = []
        selectors = [
            "img.prod-hero-image",
            "img[itemprop='image']",
            "ul.slider-list img",
            "div.carousel img",
            "div.thumbnail-list img",
            "div.product-image-gallery img",
        ]
        for selector in selectors:
            srcs = response.css(f"{selector}::attr(src)").getall()
            srcsets = response.css(f"{selector}::attr(srcset)").getall()
            for src in srcs:
                if src:
                    images.append(src.strip())
            for srcset in srcsets:
                if not srcset:
                    continue
                first = srcset.split(",")[0].strip().split(" ")[0]
                if first:
                    images.append(first)
        deduped = []
        seen = set()
        for img in images:
            if img and img not in seen:
                seen.add(img)
                deduped.append(img)
        return deduped

    def _build_next_page_url(self, current_url):
        parsed = urlparse(current_url)
        query = parse_qs(parsed.query)
        current_page = int(query.get("page", ["1"])[0] or "1")
        next_page = current_page + 1
        query["page"] = [str(next_page)]
        query["q"] = [self.search_term]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True))), next_page

    def _request_for_url(self, url, page_number):
        ua = random.choice(USER_AGENTS)
        meta = {
            "playwright": True,
            "playwright_include_page": True,
            "page_number": page_number,
            "playwright_page_methods": [
                PageMethod("set_extra_http_headers", {"user-agent": ua}),
                PageMethod("wait_for_selector", "div#main-content, script[id='__NEXT_DATA__']", {"timeout": 30000}),
                PageMethod("evaluate", "window.scrollBy(0, document.body.scrollHeight)"),
                PageMethod("wait_for_timeout", 1500),
            ],
        }
        base = Path(__file__).resolve().parents[1]
        storage_path = base / "walmart_storage.json"
        if storage_path.exists():
            meta["playwright_context"] = {"storageState": str(storage_path)}
            self._log("info", "loaded storage state", storage_path=str(storage_path), page_number=page_number)
        return scrapy.Request(url, meta=meta, headers={"User-Agent": ua}, callback=self.parse)

    def _maybe_schedule_next_page(self, response):
        if self.results_found >= self.num_products:
            self._log("info", "target reached; no next page request needed")
            return None

        try:
            page_number = int(response.meta.get("page_number", 1))
        except Exception:
            page_number = 1
        if page_number >= self.max_pages:
            self._log("warning", "max pages reached before target", page_number=page_number, max_pages=self.max_pages)
            return None

        next_href = response.css('a[aria-label="Next Page"]::attr(href)').get()
        if next_href:
            next_url = self._normalize_link(next_href)
            next_page = page_number + 1
        else:
            next_url, next_page = self._build_next_page_url(response.url)

        self._log("info", "requesting next page to continue filling target", next_page=next_page, next_url=next_url)
        return self._request_for_url(next_url, page_number=next_page)

    def start_requests(self):
        first_url = f"https://www.walmart.com/search?q={self.search_term}&page=1"
        self._log(
            "info",
            "starting search scrape",
            min_price=self.min_price,
            max_price=self.max_price,
            max_pages=self.max_pages,
            first_url=first_url,
        )
        yield self._request_for_url(first_url, page_number=1)

    def parse(self, response):
        self.pages_processed += 1
        try:
            page_number = int(response.meta.get("page_number", 1))
        except Exception:
            page_number = 1
        self._log("info", "processing search response", page_number=page_number, status=getattr(response, "status", None), url=response.url)

        next_data = response.xpath('//script[@id="__NEXT_DATA__"]/text()').get()
        if next_data:
            self._log("info", "found __NEXT_DATA__ json blob", page_number=page_number)
            try:
                data = json.loads(next_data)
                item_stacks = (
                    data.get("props", {})
                    .get("pageProps", {})
                    .get("initialData", {})
                    .get("searchResult", {})
                    .get("itemStacks", [])
                )
                items = []
                for stack in item_stacks:
                    items.extend(stack.get("items", []))
                self._log("info", "json extraction candidate count", page_number=page_number, candidates=len(items))

                for idx, item in enumerate(items, start=1):
                    if self.results_found >= self.num_products:
                        break
                    if item.get("__typename") != "Product":
                        self._log("debug", "skipping non-product json item", item_index=idx, typename=item.get("__typename"))
                        continue

                    link = self._normalize_link(item.get("canonicalUrl"))
                    if link in self.seen_links:
                        self._log("debug", "duplicate link skipped", item_index=idx, link=link)
                        continue

                    product = {
                        "name": item.get("name"),
                        "price": item.get("priceInfo", {}).get("currentPrice", {}).get("price"),
                        "image": item.get("image"),
                        "images": [item.get("image")] if item.get("image") else [],
                        "shipping": item.get("fulfillmentLabel"),
                        "description": item.get("description"),
                        "link": link,
                        "source": "json_extraction",
                    }

                    if product.get("price") is not None:
                        try:
                            product["price"] = float(product["price"])
                            self._log("debug", "price parsed from json", item_index=idx, price=product["price"])
                        except Exception:
                            product["price"] = self._parse_price(str(product.get("price")))
                            self._log("debug", "price fallback parsed from json string", item_index=idx, price=product["price"])

                    missing = self._required_missing(product)
                    self._log("info", "json product extraction result", item_index=idx, link=product.get("link"), missing_fields=missing)
                    if self._is_valid_product(product):
                        self.seen_links.add(link)
                        self.results_found += 1
                        self._log("info", "json product accepted", item_index=idx, link=link)
                        yield product
                        continue

                    self._log(
                        "warning",
                        "json product rejected",
                        item_index=idx,
                        link=link,
                        missing_fields=missing,
                        price=product.get("price"),
                    )

                if self.results_found < self.num_products:
                    next_req = self._maybe_schedule_next_page(response)
                    if next_req:
                        yield next_req
                return
            except Exception as e:
                self._log("error", "json extraction failed, switching to dom", page_number=page_number, error=str(e))

        self._log("warning", "falling back to dom scraping", page_number=page_number)
        product_cards = response.css("div[data-item-id]")
        if not product_cards:
            self._log("error", "no product cards found", page_number=page_number, url=response.url)
            debug_path = Path(__file__).parent.parent.parent / f"debug_failed_{datetime.now().timestamp()}.html"
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(response.text)
            self._log("info", "saved debug html", debug_path=str(debug_path))
            return

        self._log("info", "dom card candidates found", page_number=page_number, candidates=len(product_cards))
        for card_idx, card in enumerate(product_cards, start=1):
            if self.results_found >= self.num_products:
                break
            self.card_attempts += 1
            self._log("info", "processing product card", card_index=card_idx, card_attempt=self.card_attempts)

            name_attempts = [
                {"selector": 'span[data-automation-id="product-title"]::text', "extract": "text"},
                {"selector": "a span.w_iUH7::text", "extract": "text"},
                {"selector": ".f6.f5-l::text", "extract": "text"},
            ]
            price_attempts = [
                {"selector": 'div[data-automation-id="product-price"] div::text', "extract": "text"},
                {"selector": ".aa88::text", "extract": "text"},
                {"selector": "span.price-characteristic::attr(content)", "extract": "text"},
            ]
            image_attempts = [
                {"selector": 'img[data-testid="productTileImage"]', "extract": "attr", "attr": "src"},
                {"selector": "img", "extract": "attr", "attr": "src"},
            ]
            link_attempts = [
                {"selector": "a", "extract": "attr", "attr": "href"},
            ]

            name, name_attempt = self._attempt_extract(card, "name", name_attempts, card_idx=card_idx)
            price_text, price_attempt = self._attempt_extract(card, "price_text", price_attempts, card_idx=card_idx)
            image, image_attempt = self._attempt_extract(card, "image", image_attempts, card_idx=card_idx)
            raw_link, link_attempt = self._attempt_extract(card, "link", link_attempts, card_idx=card_idx)
            link = self._normalize_link(raw_link)
            shipping = self._extract_shipping(card, card_idx=card_idx)

            price = self._parse_price(price_text) if price_text else None
            self._log(
                "info",
                "card field extraction summary",
                card_index=card_idx,
                name_ok=bool(name),
                price_ok=bool(price),
                image_ok=bool(image),
                link_ok=bool(link),
                name_attempt=name_attempt,
                price_attempt=price_attempt,
                image_attempt=image_attempt,
                link_attempt=link_attempt,
            )

            if link in self.seen_links:
                self._log("debug", "duplicate card link skipped", card_index=card_idx, link=link)
                continue

            product = {
                "name": name.strip() if name else None,
                "price": price,
                "image": image,
                "images": [image] if image else [],
                "shipping": shipping,
                "description": None,
                "link": link,
                "source": "dom_scrape",
            }
            missing = self._required_missing(product)

            if missing and link:
                self._log("warning", "card missing required fields; requesting detail page", card_index=card_idx, link=link, missing_fields=missing)
                detail_ua = random.choice(USER_AGENTS)
                detail_methods = [
                    PageMethod("set_extra_http_headers", {"user-agent": detail_ua}),
                    PageMethod("set_viewport_size", {"width": 1200, "height": 900}),
                    PageMethod("goto", link, {"wait_until": "domcontentloaded"}),
                    PageMethod("wait_for_selector", "body"),
                    PageMethod("wait_for_timeout", 500),
                ]
                yield scrapy.Request(
                    link,
                    callback=self.parse_product_detail,
                    headers={"User-Agent": detail_ua},
                    meta={
                        "playwright": True,
                        "playwright_page_methods": detail_methods,
                        "partial_item": product,
                        "card_index": card_idx,
                        "page_number": page_number,
                    },
                )
                continue

            if not self._is_valid_product(product):
                self._log("warning", "card rejected after extraction", card_index=card_idx, link=link, missing_fields=missing, price=price)
                continue

            self.seen_links.add(link)
            self.results_found += 1
            self._log("info", "card accepted", card_index=card_idx, link=link)
            yield product

        if self.results_found < self.num_products:
            next_req = self._maybe_schedule_next_page(response)
            if next_req:
                yield next_req

    def parse_product_detail(self, response):
        partial = response.meta.get("partial_item", {}) or {}
        card_index = response.meta.get("card_index")
        self._log("info", "processing detail page", card_index=card_index, detail_url=response.url)

        name_attempts = [
            {"selector": "h1.prod-ProductTitle::text", "extract": "text"},
            {"selector": 'h1[itemprop="name"]::text', "extract": "text"},
            {"selector": "h1::text", "extract": "text"},
        ]
        price_attempts = [
            {"selector": "span.price-characteristic", "extract": "attr", "attr": "content"},
            {"selector": 'meta[itemprop="price"]', "extract": "attr", "attr": "content"},
            {"selector": "span.price::text", "extract": "text"},
        ]
        description_attempts = [
            {"selector": "#product-description p::text", "extract": "text"},
            {"selector": '[data-testid="product-description"]::text', "extract": "text"},
            {"selector": 'meta[name="description"]', "extract": "attr", "attr": "content"},
        ]
        shipping_attempts = [
            {"selector": '[data-testid="fulfillment-summary"]::text', "extract": "text"},
            {"selector": "span:contains('shipping')::text", "extract": "text"},
            {"selector": 'div[data-automation-id="fulfillment-badge"]::text', "extract": "text"},
        ]

        name, _ = self._attempt_extract(response, "detail_name", name_attempts, card_idx=card_index)
        price_txt, _ = self._attempt_extract(response, "detail_price_text", price_attempts, card_idx=card_index)
        description, _ = self._attempt_extract(response, "detail_description", description_attempts, card_idx=card_index)
        shipping, _ = self._attempt_extract(response, "detail_shipping", shipping_attempts, card_idx=card_index)

        price = self._parse_price(price_txt) if price_txt else partial.get("price")
        images = self._extract_images_from_response(response)
        if not images and partial.get("images"):
            images = list(partial.get("images"))
        image = images[0] if images else partial.get("image")

        # JSON-LD fallback for description and shipping hints.
        try:
            ld_nodes = response.xpath('//script[@type="application/ld+json"]/text()').getall()
            for ld in ld_nodes:
                if not ld or not ld.strip():
                    continue
                parsed = json.loads(ld)
                objects = parsed if isinstance(parsed, list) else [parsed]
                for obj in objects:
                    if not isinstance(obj, dict):
                        continue
                    if not description and obj.get("description"):
                        description = obj.get("description")
                        self._log("debug", "description extracted from json-ld", card_index=card_index)
                    if not name and obj.get("name"):
                        name = obj.get("name")
                        self._log("debug", "name extracted from json-ld", card_index=card_index)
        except Exception as e:
            self._log("warning", "json-ld parse failed on detail page", card_index=card_index, error=str(e))

        merged = {
            "name": name or partial.get("name"),
            "price": price,
            "image": image,
            "images": images if images else ([image] if image else []),
            "shipping": shipping or partial.get("shipping"),
            "description": description or partial.get("description"),
            "link": partial.get("link") or response.url,
            "source": "detail_enrichment",
        }

        missing = self._required_missing(merged)
        merged["incomplete"] = bool(missing)
        merged["missing_fields"] = missing
        merged["detail_url"] = response.url

        if not self._is_valid_product(merged):
            self._log("warning", "detail page product rejected", card_index=card_index, link=merged.get("link"), missing_fields=missing, price=merged.get("price"))
            return

        if merged.get("link") in self.seen_links:
            self._log("debug", "detail page product duplicate skipped", card_index=card_index, link=merged.get("link"))
            return

        self.seen_links.add(merged.get("link"))
        self.results_found += 1
        self._log("info", "detail page product accepted", card_index=card_index, link=merged.get("link"), image_count=len(merged.get("images", [])))
        yield merged
