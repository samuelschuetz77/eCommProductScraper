Usage notes — proxy & UA rotation

Quick guide to proxy rotation + UA rotation added to the Scrapy project.

What I changed
- Enabled AutoThrottle + randomized delays in `walmart_scraper/settings.py`
- Added `RandomUserAgentMiddleware` and `RotatingProxyMiddleware` (in `middlewares.py`)
- Playwright launch options include a small anti-detection flag
- Spider now injects a per-request User-Agent into Playwright page methods

How to provide proxies
- Option A (recommended for local testing): set the PROXY_LIST environment variable when running the spider.
  Example (PowerShell):
    $env:PROXY_LIST = "http://user:pass@1.2.3.4:8000,http://5.6.7.8:3128"
    scrapy crawl walmart

- Manual captcha solve behind a proxy: POST to `/captcha/interactive` with optional `proxy` form field (or set `WALMART_PROXY` environment variable). Example proxy format: `http://user:pass@host:port`.
  This opens the headed browser on the chosen proxy so manual solves validate that IP/session combination.

- Option B: edit `walmart_scraper/settings.py` and populate `PROXY_LIST = ["http://...", "http://..."]`.

Notes on behaviour
- For Playwright requests the middleware injects the proxy into `request.meta['playwright_context']` so the browser context uses that proxy.
- The middleware also sets `request.meta['proxy']` for non-Playwright requests so Scrapy's HttpProxyMiddleware will use it.
- User-Agent rotation is provided by `RandomUserAgentMiddleware` and the spider additionally sets headers for Playwright pages.

Security & ethics
- Use residential proxies you are authorized to use. Abide by the site's Terms of Service and robots.txt for any scraping work.

If you want, I can:
- Add an integration example using a proxy provider (Bright Data / Oxylabs / Smartproxy)
- Add a small CLI helper to validate proxy list before running the spider
