# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

from scrapy import signals

# useful for handling different item types with a single interface
from itemadapter import ItemAdapter


class WalmartScraperSpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(self, response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        pass

    async def process_start(self, start):
        # Called with an async iterator over the spider start() method or the
        # matching method of an earlier spider middleware.
        async for item_or_request in start:
            yield item_or_request

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class WalmartScraperDownloaderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the downloader middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        # Called for each request that goes through the downloader
        # middleware.

        # Must either:
        # - return None: continue processing this request
        # - or return a Response object
        # - or return a Request object
        # - or raise IgnoreRequest: process_exception() methods of
        #   installed downloader middleware will be called
        return None

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.

        # Must either;
        # - return a Response object
        # - return a Request object
        # - or raise IgnoreRequest
        return response

    def process_exception(self, request, exception, spider):
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.

        # Must either:
        # - return None: continue processing this exception
        # - return a Response object: stops process_exception() chain
        # - return a Request object: stops process_exception() chain
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


# ---- New middlewares added: RandomUserAgent + RotatingProxy ----
import os
import random
from urllib.parse import urlparse


class RandomUserAgentMiddleware:
    """Set a random User-Agent header per request.

    Priority: 400 (configured in settings.py). Uses `USER_AGENTS` from
    settings or falls back to `spider.USER_AGENTS` when available.
    """

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def __init__(self, settings):
        self.settings = settings
        # allow users to override USER_AGENTS in settings.py
        self.user_agents = settings.getlist('USER_AGENTS') or None

    def process_request(self, request, spider):
        uas = self.user_agents or getattr(spider, 'USER_AGENTS', None)
        if not uas:
            return None
        ua = random.choice(uas)
        request.headers['User-Agent'] = ua
        spider.logger.debug('UA set: %s', ua)
        return None


class RotatingProxyMiddleware:
    """Attach a proxy per-request. Works for both Scrapy requests and
    Scrapy-Playwright requests by injecting into `request.meta`.

    - Read proxies from setting `PROXY_LIST` or environment variable
      `PROXY_LIST` (comma-separated).
    - For Playwright requests, inject into `playwright_context` as
      `{'proxy': {'server': 'http://host:port', 'username':.., 'password':..}}`.
    - For non-Playwright requests, set `request.meta['proxy']`.
    """

    @classmethod
    def from_crawler(cls, crawler):
        proxies = []
        env = os.environ.get('PROXY_LIST')
        if env:
            proxies = [p.strip() for p in env.split(',') if p.strip()]
        else:
            proxies = crawler.settings.get('PROXY_LIST', []) or []
        return cls(proxies)

    def __init__(self, proxies):
        self.proxies = proxies

    def _pick_proxy(self):
        if not self.proxies:
            return None
        return random.choice(self.proxies)

    def _parse_proxy(self, proxy_url):
        # Accept forms: http://user:pass@host:port or host:port
        if '://' not in proxy_url:
            proxy_url = 'http://' + proxy_url
        parsed = urlparse(proxy_url)
        server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        if parsed.username:
            return {'server': server, 'username': parsed.username, 'password': parsed.password}
        return {'server': server}

    def process_request(self, request, spider):
        proxy = self._pick_proxy()
        if not proxy:
            return None

        # If Playwright is used for this request, inject into playwright_context
        if request.meta.get('playwright') or request.meta.get('playwright_context'):
            ctx = request.meta.setdefault('playwright_context', {})
            ctx['proxy'] = self._parse_proxy(proxy)
            spider.logger.debug('Playwright proxy injected: %s', ctx['proxy'].get('server'))
            return None

        # Otherwise, use Scrapy's HttpProxyMiddleware style (meta['proxy'])
        # credentials may remain in the URL (Scrapy supports that)
        if '://' not in proxy:
            proxy = 'http://' + proxy
        request.meta['proxy'] = proxy
        spider.logger.debug('Meta proxy set: %s', proxy)
        return None
