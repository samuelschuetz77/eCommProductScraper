import os
import subprocess
import json
import time
import uuid
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine.url import make_url

# --- app / logging ---------------------------------------------------------
app = Flask(__name__, static_folder='frontend/build', template_folder='templates')
CORS(app, resources={r"/*": {"origins": "*"}})  # safe for local/dev; restrict in prod
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- database setup -------------------------------------------------------
# Use DATABASE_URL env var (e.g. postgresql://user:pass@host:5432/dbname); fall back to sqlite
DATABASE_URL = (os.environ.get('DATABASE_URL') or '').strip() or f"sqlite:///{Path('data.db').absolute()}"
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)
Base = declarative_base()

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String(1024))
    price = Column(Float)
    image = Column(String(2048))
    link = Column(String(2048), unique=True, index=True)
    search_term = Column(String(256), index=True)
    description = Column(Text)
    source = Column(String(256))
    is_complete = Column(Integer, default=0)  # 0 = incomplete, 1 = complete
    scraped_at = Column(DateTime, default=datetime.utcnow)
    raw = Column(Text)


class ImageURL(Base):
    __tablename__ = 'image_urls'
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, index=True)
    url = Column(String(2048))
    size_kb = Column(Integer)
    scraped_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)
# log DB connection (sanitized)
try:
    url_obj = make_url(DATABASE_URL)
    safe_db = f"{url_obj.drivername}://{url_obj.host or ''}/{url_obj.database or ''}"
except Exception:
    safe_db = DATABASE_URL
logger.info('Database initialized — %s', safe_db)

# --- helpers --------------------------------------------------------------
WALMART_DIR = Path('walmart_scraper')
WALMART_DIR.mkdir(exist_ok=True)

def _unique_output_file():
    ts = int(time.time())
    uid = uuid.uuid4().hex[:8]
    return WALMART_DIR / f"scraped_{ts}_{uid}.json"

def _save_products_to_db(products, search_term=None):
    """Save scraped products to DB and record image URLs (best-effort).

    Returns a list of dicts describing what was created/updated and any warnings.
    """
    saved = []
    import requests
    total_products = len(products)
    logger.info('Saving %d products to DB (search_term=%s)', total_products, search_term)

    try:
        with SessionLocal() as session:
            for p in products:
                link = p.get('link')
                name = p.get('name')
                price = p.get('price')
                image = p.get('image')
                images = p.get('images') or ([] if p.get('images') is None else p.get('images'))
                raw = json.dumps(p)

                is_complete = 1 if (name and price is not None and (image or images) and link) else 0

                existing = None
                if link:
                    existing = session.query(Product).filter_by(link=link).first()

                if existing:
                    existing.name = name or existing.name
                    existing.price = price if price is not None else existing.price
                    existing.image = image or existing.image
                    existing.description = p.get('description') or existing.description
                    existing.is_complete = is_complete
                    existing.scraped_at = datetime.utcnow()
                    existing.raw = raw
                    session.add(existing)
                    prod_id = existing.id
                    logger.info('Updated product id=%s link=%s is_complete=%s', prod_id, link, bool(is_complete))
                    saved.append({'id': prod_id, 'action': 'updated', 'is_complete': bool(is_complete)})
                else:
                    prod = Product(
                        name=name,
                        price=price if price is not None else None,
                        image=image,
                        link=link,
                        search_term=search_term,
                        description=p.get('description'),
                        source=p.get('source'),
                        is_complete=is_complete,
                        scraped_at=datetime.utcnow(),
                        raw=raw,
                    )
                    session.add(prod)
                    session.flush()
                    prod_id = prod.id
                    logger.info('Created product id=%s link=%s is_complete=%s', prod_id, link, bool(is_complete))
                    saved.append({'id': prod_id, 'action': 'created', 'is_complete': bool(is_complete)})

                # record image URL(s) in a separate table and attempt to get size (HEAD)
                images_to_save = []
                if images:
                    images_to_save = images
                elif image:
                    images_to_save = [image]

                for img_url in images_to_save:
                    try:
                        head = requests.head(img_url, timeout=5)
                        size = None
                        if 'Content-Length' in head.headers:
                            size = int(head.headers.get('Content-Length', 0)) // 1024
                        else:
                            size = None
                    except Exception:
                        logger.debug('Failed to HEAD image %s', img_url)
                        size = None

                    try:
                        img = ImageURL(product_id=prod_id, url=img_url, size_kb=size or 0, scraped_at=datetime.utcnow())
                        session.add(img)
                        logger.info('Saved ImageURL for product_id=%s url=%s size_kb=%s', prod_id, img_url, size or 0)
                    except Exception:
                        logger.exception('Failed to save ImageURL for product %s', prod_id)

                # log incomplete items for later inspection
                if not is_complete:
                    logger.warning('Saved incomplete product (missing fields) search=%s link=%s missing=%s', search_term, link, p.get('missing_fields'))

            session.commit()
            logger.info('Committed %d products to DB (search_term=%s)', total_products, search_term)
    except SQLAlchemyError:
        logger.exception('DB error while saving products')
    return saved


# --- captcha helpers & interactive/manual solve ----------------------------
def detect_captcha(html: str) -> bool:
    """Rudimentary detection of bot/challenge pages using keywords.

    Not perfect — used only to trigger manual intervention flow during dev.
    """
    if not html:
        return False
    s = html.lower()
    checks = [
        'robot or human',
        'are you a robot',
        'please verify',
        'challenge',
        '/blocked?url=',
        'px-cloud',
        'captcha',
    ]
    return any(k in s for k in checks)


@app.route('/captcha/debug/<filename>')
def serve_debug_file(filename: str):
    # Serve saved debug HTML/screenshot from WALMART_DIR for local inspection
    path = WALMART_DIR / filename
    if not path.exists():
        return 'Not found', 404
    # allow browser to render the HTML directly
    return send_file(path)


@app.route('/captcha/interactive', methods=['POST'])
def captcha_interactive():
    """Open a headed Playwright browser so a human can solve the captcha.

    - POST params: searchTerm, numProducts (optional)
    - Blocks until either products appear or a timeout (default 5 minutes).
    - Saves storage state (cookies) to WALMART_DIR/walmart_storage.json so future
      automated runs can reuse the session.
    """
    search_term = (request.form.get('searchTerm') or request.args.get('searchTerm') or '').strip()
    if not search_term:
        return jsonify({'error': 'searchTerm is required'}), 400

    try:
        num_products = int(request.form.get('numProducts') or 10)
    except ValueError:
        num_products = 10

    search_url = f"https://www.walmart.com/search?q={search_term}"
    products = []
    storage_path = WALMART_DIR / 'walmart_storage.json'

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)

            # optional proxy for the manual solve (form param `proxy` or env WALMART_PROXY)
            proxy_str = (request.form.get('proxy') or os.environ.get('WALMART_PROXY') or '').strip()
            if proxy_str:
                # normalize and parse credentials if present
                from urllib.parse import urlparse
                if '://' not in proxy_str:
                    proxy_str = 'http://' + proxy_str
                p = urlparse(proxy_str)
                proxy_opts = {'server': f"{p.scheme}://{p.hostname}:{p.port}"}
                if p.username:
                    proxy_opts['username'] = p.username
                    proxy_opts['password'] = p.password
                context = browser.new_context(proxy=proxy_opts)
                logger.info('Launched manual solve browser with proxy=%s', proxy_opts.get('server'))
            else:
                context = browser.new_context()

            page = context.new_page()
            logger.info('Opened headed browser for manual captcha solve; URL=%s', search_url)
            # navigate but don't require 'networkidle' (some sites keep background XHRs open)
            try:
                page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
            except PWTimeout:
                logger.warning('Initial goto timed out; attempting fallback navigation without waiting')
                try:
                    page.goto(search_url, timeout=0)
                except Exception:
                    browser.close()
                    return jsonify({'error': 'Failed to open page for manual captcha solve'}), 500

            # brief pause to allow client-side rendering to start
            page.wait_for_timeout(1000)

            # wait for either product results or user to solve captcha (long timeout)
            try:
                page.wait_for_selector('div[data-item-id], div.search-result-gridview-item-wrapper', timeout=300000)
            except PWTimeout:
                # timeout waiting for results
                browser.close()
                return jsonify({'error': 'Timed out waiting for manual captcha solve'}), 504

            # extract product entries directly from the Playwright page
            elems = page.query_selector_all('div[data-item-id]') or page.query_selector_all('div.search-result-gridview-item-wrapper')
            for el in elems[:num_products]:
                try:
                    name = el.query_selector('span.normal')
                    name = name.inner_text().strip() if name else (el.query_selector('a.product-title-link') and el.query_selector('a.product-title-link').inner_text().strip())
                    price_el = el.query_selector('span.f3') or el.query_selector('span.price-characteristic')
                    price_text = price_el.inner_text().strip() if price_el else None
                    price = None
                    try:
                        # sanitize price string and fall back to 0.0 when parsing fails
                        clean_price = ''.join(ch for ch in (price_text or '') if (ch.isdigit() or ch == '.'))
                        price = float(clean_price) if clean_price else 0.0
                    except (ValueError, TypeError):
                        price = 0.0

                    image = el.query_selector('img')
                    image = image.get_attribute('src') if image else None
                    link_el = el.query_selector('a')
                    link = link_el.get_attribute('href') if link_el else None
                    if link and link.startswith('/'):
                        link = f'https://www.walmart.com{link}'
                    products.append({'name': name, 'price': price, 'image': image, 'link': link})
                except Exception:
                    logger.exception('Failed to parse a product element')

            # save storage state (cookies/localStorage)
            try:
                # ask Playwright to write the storage state file directly (more reliable)
                context.storage_state(path=str(storage_path))
                logger.info('Saved Playwright storage state -> %s', storage_path)
            except Exception:
                logger.exception('Failed to save storage state')

            browser.close()

        # persist to DB (best-effort)
        try:
            saved = _save_products_to_db(products, search_term=search_term)
        except Exception:
            logger.exception('Error while saving products from interactive solve')
            saved = []

        # Build and return response (previously missing) so the client receives results
        resp = {'count': len(products), 'products': products, 'saved': saved}
        try:
            if storage_path.exists():
                resp['storage_state'] = str(storage_path)
        except Exception:
            logger.exception('Error checking storage_state file for interactive flow')

        logger.info('Interactive captcha solved — returning %d products', len(products))
        return jsonify(resp)

    except Exception:
        logger.exception('Interactive captcha flow failed')
        return jsonify({'error': 'Interactive captcha flow failed'}), 500

# --- routes ---------------------------------------------------------------
@app.route('/')
def index():
    # Serve basic HTML (templates/index.html) if frontend not used. In production you
    # would serve the built Svelte app instead (copy build to static folder).
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    # basic validation + limits to avoid long/blocking jobs
    search_term = (request.form.get('searchTerm') or '').strip()
    if not search_term:
        return jsonify({'error': 'searchTerm is required'}), 400

    try:
        num_products = int(request.form.get('numProducts') or 10)
        num_products = max(1, min(num_products, 100))  # cap to 100
    except ValueError:
        num_products = 10

    min_price = request.form.get('minPrice') or ''
    max_price = request.form.get('maxPrice') or ''

    output_path = _unique_output_file()
    output_name = output_path.name

    scrapy_command = [
        'python', '-m', 'scrapy', 'crawl', 'walmart',
        '-a', f'search_term={search_term}',
        '-a', f'min_price={min_price}',
        '-a', f'max_price={max_price}',
        '-a', f'num_products={num_products}',
        '-o', output_name
    ]

    logger.info('Starting scrapy: %s', ' '.join(scrapy_command))

    try:
        subprocess.run(scrapy_command, check=True, cwd=str(WALMART_DIR), timeout=600)
    except subprocess.TimeoutExpired as e:
        logger.exception('Scrapy timed out')
        return jsonify({'error': 'Scraping timed out'}), 504
    except subprocess.CalledProcessError as e:
        logger.exception('Scrapy failed')
        return jsonify({'error': 'Scrapy failed', 'detail': str(e)}), 500

    try:
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
        try:
            products = json.loads(content)
        except json.JSONDecodeError:
            # try to be forgiving: parse as JSON-lines (one JSON object per line)
            products = []
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    products.append(json.loads(line))
                except Exception:
                    logger.warning('Failed to parse a line from scrapy output (truncated): %s', line[:200])
            logger.warning('Scrapy output JSON was malformed; parsed %d objects from lines', len(products))

        logger.info('Scrapy produced output %s -> %d products', output_path, len(products))
    except FileNotFoundError:
        return jsonify({'error': 'Scrape output missing'}), 500

    # If nothing scraped, optionally save the full page HTML + screenshot for debugging
    debug_html_path = None
    debug_screenshot_path = None
    captcha_detected = False

    if len(products) == 0 or request.args.get('debug') == 'true':
        try:
            from playwright.sync_api import sync_playwright
            search_url = f"https://www.walmart.com/search?q={search_term}"
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(search_url, timeout=30000)
                html = page.content()

                ts = int(time.time())
                debug_html_path = WALMART_DIR / f"debug_{search_term}_{ts}.html"
                debug_screenshot_path = WALMART_DIR / f"debug_{search_term}_{ts}.png"

                debug_html_path.write_text(html, encoding='utf-8')
                page.screenshot(path=str(debug_screenshot_path), full_page=True)

                captcha_detected = detect_captcha(html)

                browser.close()
                logger.info('Saved debug HTML (%s) and screenshot (%s)', debug_html_path, debug_screenshot_path)
        except Exception:
            logger.exception('Failed to capture debug HTML/screenshot')

    # persist to DB (best-effort)
    saved = _save_products_to_db(products, search_term=search_term)

    resp = {'count': len(products), 'products': products, 'saved': saved}
    if debug_html_path:
        resp['debug_html'] = str(debug_html_path)
    if debug_screenshot_path:
        resp['debug_screenshot'] = str(debug_screenshot_path)
    if captcha_detected:
        resp['captcha_detected'] = True

    return jsonify(resp)

    # persist to DB (best-effort)
    saved = _save_products_to_db(products, search_term=search_term)

    resp = {'count': len(products), 'products': products, 'saved': saved}
    if debug_html_path:
        resp['debug_html'] = str(debug_html_path)

    return jsonify(resp)

@app.route('/products')
def list_products():
    # simple query endpoint with optional filters
    limit = int(request.args.get('limit', 50))
    limit = min(limit, 500)
    q = request.args.get('q')

    with SessionLocal() as session:
        query = session.query(Product).order_by(Product.scraped_at.desc())
        if q:
            query = query.filter(Product.name.ilike(f"%{q}%"))
        products = query.limit(limit).all()
        out = [
            {
                'id': p.id,
                'name': p.name,
                'price': p.price,
                'image': p.image,
                'link': p.link,
                'search_term': p.search_term,
                'scraped_at': p.scraped_at.isoformat() if p.scraped_at else None,
            }
            for p in products
        ]
    return jsonify(out)

@app.route('/products/download_csv')
def download_products_csv():
    with SessionLocal() as session:
        products = session.query(Product).all()
        if not products:
            return 'No products in database.', 404
        rows = [
            {'id': p.id, 'name': p.name, 'price': p.price, 'link': p.link, 'image': p.image, 'scraped_at': p.scraped_at}
            for p in products
        ]
        df = pd.DataFrame(rows)
        csv_path = WALMART_DIR / 'products_db_export.csv'
        df.to_csv(csv_path, index=False)
    return send_file(csv_path, as_attachment=True)

# keep legacy JSON-download route for compatibility (reads latest file if present)
@app.route('/download_csv')
def download_csv():
    # prefer DB export, fall back to last scraped json file
    try:
        return download_products_csv()
    except Exception:
        # find the most recent scraped_*.json file
        files = sorted(WALMART_DIR.glob('scraped_*.json'), key=os.path.getmtime, reverse=True)
        if not files:
            return "Scraped data not found. Please run a search first.", 404
        json_path = files[0]
        csv_path = WALMART_DIR / 'scraped_data.csv'
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        df = pd.DataFrame(data)
        df.to_csv(csv_path, index=False)
        return send_file(csv_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
