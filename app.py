import os
import subprocess
import json
import time
import uuid
import logging
import re
from datetime import datetime
from pathlib import Path

import requests
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
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "scrape.log", encoding="utf-8"),
    ],
)
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

def _product_missing_fields(product):
    required = ("name", "price", "image", "link")
    return [field for field in required if not product.get(field)]

def _product_is_valid(product):
    return len(_product_missing_fields(product)) == 0

def _save_products_to_db(products, search_term=None):
    """Save scraped products to DB and record image URLs (best-effort).

    Returns a list of dicts describing what was created/updated and any warnings.
    """
    saved = []
    total_products = len(products)
    logger.info('Saving %d products to DB (search_term=%s)', total_products, search_term)

    try:
        with SessionLocal() as session:
            for p in products:
                link = p.get('link')
                name = p.get('name')
                price = p.get('price')
                image = p.get('image')
                images = p.get('images') or []
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
                    try:
                        # append incomplete item to a troubleshooting file for offline inspection
                        inc_file = WALMART_DIR / 'incomplete_items.jsonl'
                        with open(inc_file, 'a', encoding='utf-8') as fh:
                            fh.write(json.dumps({'scraped_at': datetime.utcnow().isoformat(), 'search_term': search_term, 'product': p}) + "\n")
                        logger.info('Appended incomplete item -> %s', inc_file)
                    except Exception:
                        logger.exception('Failed to write incomplete item to disk')

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
    """Headed Playwright manual solve with broader selectors + diagnostics.

    - Returns parsed products and the DB save results.
    - Keeps proxy support and persists Playwright storage state.
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
    scrape_run_id = f"interactive-{uuid.uuid4().hex[:8]}"

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)

            # keep optional proxy support
            proxy_str = (request.form.get('proxy') or os.environ.get('WALMART_PROXY') or '').strip()
            if proxy_str:
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
            logger.info('Navigating to %s for interactive solve', search_url)
            try:
                page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
            except PWTimeout:
                logger.error('Initial navigation timed out')
                browser.close()
                return jsonify({'error': 'Failed to open page for manual captcha solve'}), 500

            # wait for product grid (human solve may be required)
            try:
                page.wait_for_selector('div[data-item-id], div.search-result-gridview-item-wrapper', timeout=300000)
            except PWTimeout:
                browser.close()
                return jsonify({'error': 'Timed out waiting for product grid'}), 504

            elems = page.query_selector_all('div[data-item-id]') or page.query_selector_all('div.search-result-gridview-item-wrapper')
            logger.info('Found %d product candidate elements (run_id=%s)', len(elems), scrape_run_id)
            try:
                page_marker_script = """
                () => {
                    const phrases = ['about this item', 'product details', 'view all item details'];
                    const out = [];
                    const nodes = document.querySelectorAll('body *');
                    for (const node of nodes) {
                        const text = (node.textContent || '').replace(/\\s+/g, ' ').trim();
                        if (!text) continue;
                        const low = text.toLowerCase();
                        let matched = null;
                        for (const p of phrases) {
                            if (low.includes(p)) {
                                matched = p;
                                break;
                            }
                        }
                        if (!matched) continue;
                        out.push({
                            phrase: matched,
                            tag: (node.tagName || '').toLowerCase(),
                            cls: node.className || '',
                            aria: node.getAttribute('aria-label') || '',
                            txt: text.slice(0, 220),
                            html: (node.outerHTML || '').replace(/\\s+/g, ' ').slice(0, 260),
                        });
                        if (out.length >= 25) break;
                    }
                    return out;
                }
                """
                page_markers = page.evaluate(page_marker_script) or []
                logger.info(
                    'Interactive page markers run_id=%s marker_count=%d',
                    scrape_run_id,
                    len(page_markers),
                )
                for pidx, pm in enumerate(page_markers, start=1):
                    logger.debug(
                        'Interactive page marker run_id=%s marker=%d phrase=%s tag=%s class=%s aria=%s text="%s" html="%s"',
                        scrape_run_id,
                        pidx,
                        pm.get('phrase'),
                        pm.get('tag'),
                        pm.get('cls'),
                        pm.get('aria'),
                        (pm.get('txt') or '')[:180],
                        (pm.get('html') or '')[:220],
                    )
            except Exception as page_marker_err:
                logger.debug('Interactive page marker capture failed run_id=%s error=%s', scrape_run_id, page_marker_err)

            def _normalize_product_link(raw_link):
                if not raw_link:
                    return None
                link = raw_link.strip()
                if link.startswith('/'):
                    link = f"https://www.walmart.com{link}"
                # Sponsored cards often use /sp/track with rd=<real product url>.
                try:
                    from urllib.parse import urlparse, parse_qs, unquote
                    parsed = urlparse(link)
                    if '/sp/track' in parsed.path:
                        qs = parse_qs(parsed.query)
                        rd = qs.get('rd', [None])[0]
                        if rd:
                            resolved = unquote(rd)
                            if resolved.startswith('/'):
                                resolved = f"https://www.walmart.com{resolved}"
                            if resolved.startswith('http'):
                                logger.debug('Resolved sponsored link -> product link run_id=%s track=%s resolved=%s', scrape_run_id, link, resolved)
                                return resolved
                        # Some tracking links include a raw /ip/... suffix without rd param.
                        m = re.search(r'(/ip/[^\s\?&#]+[^\s]*)', unquote(link))
                        if m:
                            candidate = m.group(1)
                            if candidate.startswith('/'):
                                candidate = f"https://www.walmart.com{candidate}"
                            logger.debug('Resolved sponsored link by /ip suffix run_id=%s track=%s resolved=%s', scrape_run_id, link, candidate)
                            return candidate
                except Exception as e:
                    logger.debug('Link normalization failed run_id=%s link=%s error=%s', scrape_run_id, link, e)
                return link

            def _parse_price_value(text):
                if not text:
                    return None
                s = str(text).replace('\xa0', ' ').strip()
                # Highest priority: discounted labels (Now/Clearance/Reduced/Sale)
                labeled_decimal = re.search(
                    r"(?:now|clearance|reduced(?:\s+from)?|sale(?:\s+price)?)\s*\$?\s*([0-9][0-9,]*\.[0-9]{2})",
                    s,
                    flags=re.IGNORECASE,
                )
                if labeled_decimal:
                    try:
                        return float(labeled_decimal.group(1).replace(',', ''))
                    except Exception:
                        return None

                labeled_compact = re.search(
                    r"(?:now|clearance|reduced(?:\s+from)?|sale(?:\s+price)?)\s*\$?\s*([0-9][0-9,]{2,})",
                    s,
                    flags=re.IGNORECASE,
                )
                if labeled_compact:
                    try:
                        raw = labeled_compact.group(1).replace(',', '')
                        return float(raw) / 100.0 if len(raw) >= 3 else float(raw)
                    except Exception:
                        return None

                # Walmart often includes "current price $10.29" in the same node.
                current_price_match = re.search(r"current\s+price\s*\$?\s*([0-9][0-9,]*\.[0-9]{2})", s, flags=re.IGNORECASE)
                if current_price_match:
                    try:
                        return float(current_price_match.group(1).replace(',', ''))
                    except Exception:
                        return None

                # Prefer explicit decimal currency matches.
                decimal_currency = re.findall(r"\$\s*([0-9][0-9,]*\.[0-9]{1,2})", s)
                if decimal_currency:
                    try:
                        return float(decimal_currency[-1].replace(',', ''))
                    except Exception:
                        return None

                # Fallback for any decimal number in text.
                m2 = re.search(r"\b([0-9][0-9,]*\.[0-9]{2})\b", s)
                if m2:
                    try:
                        return float(m2.group(1).replace(',', ''))
                    except Exception:
                        return None

                # Last resort: integer-looking currency amount (e.g. "$1029").
                # If "current price" exists in the same text, this value is usually cents.
                compact_currency = re.findall(r"\$\s*([0-9][0-9,]*)", s)
                if compact_currency:
                    num = compact_currency[-1].replace(',', '')
                    try:
                        if re.search(r"current\s+price", s, flags=re.IGNORECASE) and len(num) >= 3:
                            return float(num) / 100.0
                        return float(num)
                    except Exception:
                        return None
                return None

            def _clean_title_text(raw_title, item_idx):
                """Normalize title and remove embedded pricing noise from card text."""
                raw = (raw_title or '').replace('\xa0', ' ').strip()
                if not raw:
                    logger.debug('Interactive title clean item=%d success=False reason=empty_raw run_id=%s', item_idx, scrape_run_id)
                    return 'Unknown Item'

                lines = [re.sub(r'\s+', ' ', ln).strip() for ln in raw.splitlines()]
                lines = [ln for ln in lines if ln]

                def _looks_like_price_line(s):
                    low = s.lower()
                    if re.search(r'\$\s*[0-9]', s):
                        return True
                    if re.search(r'\bcurrent\s+price\b|\bwas\s+\$|\bnow\s+\$|\bclearance\b|\bsale\b', low):
                        return True
                    if re.search(r'^\+?\$[0-9]+(?:\.[0-9]{2})?\s+shipping$', low):
                        return True
                    if re.search(r'^[0-9]+(?:\.[0-9]{2})?\s*/\s*ea$', low):
                        return True
                    return False

                # Prefer the first meaningful non-price line from multiline title blocks.
                candidate = ''
                for ln in lines:
                    if len(ln) < 3:
                        continue
                    if _looks_like_price_line(ln):
                        continue
                    candidate = ln
                    break
                if not candidate:
                    candidate = lines[0] if lines else raw

                # Remove trailing price fragments still attached to the same line.
                candidate = re.sub(r'\s+\$[0-9][0-9,]*(?:\.[0-9]{2})?(?:\s*/\s*ea)?\s*$', '', candidate)
                candidate = re.sub(r'\s+(?:current\s+price|now|was|clearance|sale)\s+\$[0-9][0-9,]*(?:\.[0-9]{2})?\s*$', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'\s+', ' ', candidate).strip(' -\t\r\n')

                # Last-ditch protection: if candidate is still mostly price-y, use raw first token line.
                if _looks_like_price_line(candidate):
                    fallback = re.sub(r'\s+', ' ', (lines[0] if lines else raw)).strip()
                    candidate = re.sub(r'\s+\$[0-9][0-9,]*(?:\.[0-9]{2})?.*$', '', fallback).strip()

                cleaned = candidate or 'Unknown Item'
                logger.debug(
                    'Interactive title clean item=%d raw="%s" cleaned="%s" changed=%s run_id=%s',
                    item_idx, raw[:180], cleaned[:180], raw[:180] != cleaned[:180], scrape_run_id
                )
                return cleaned

            def _extract_quick_description(card_el, item_idx, product_name):
                """Fast card-only description extraction. Avoids detail-page navigation."""
                def _log_description_markers():
                    marker_script = """
                    (el) => {
                        const phrases = ['about this item', 'product details', 'view all item details'];
                        const results = [];
                        const nodes = el.querySelectorAll('*');
                        for (const node of nodes) {
                            const text = (node.textContent || '').replace(/\\s+/g, ' ').trim();
                            if (!text) continue;
                            const low = text.toLowerCase();
                            let matched = null;
                            for (const p of phrases) {
                                if (low.includes(p)) {
                                    matched = p;
                                    break;
                                }
                            }
                            if (!matched) continue;
                            results.push({
                                phrase: matched,
                                tag: (node.tagName || '').toLowerCase(),
                                cls: node.className || '',
                                aria: node.getAttribute('aria-label') || '',
                                txt: text.slice(0, 240),
                                html: (node.outerHTML || '').replace(/\\s+/g, ' ').slice(0, 280),
                            });
                            if (results.length >= 18) break;
                        }
                        const dangerous = [];
                        const dh = el.querySelectorAll('div.dangerous-html');
                        for (const d of dh) {
                            const t = (d.textContent || '').replace(/\\s+/g, ' ').trim();
                            dangerous.push(t.slice(0, 280));
                            if (dangerous.length >= 4) break;
                        }
                        return {
                            matches: results,
                            dangerous_count: dh.length,
                            dangerous_samples: dangerous,
                        };
                    }
                    """
                    try:
                        marker_data = card_el.evaluate(marker_script)
                        logger.debug(
                            'Interactive description markers item=%d run_id=%s matches=%d dangerous_html_count=%d samples=%s',
                            item_idx,
                            scrape_run_id,
                            len(marker_data.get('matches') or []),
                            marker_data.get('dangerous_count', 0),
                            marker_data.get('dangerous_samples') or [],
                        )
                        for marker_idx, m in enumerate((marker_data.get('matches') or []), start=1):
                            logger.debug(
                                'Interactive description marker item=%d marker=%d phrase=%s tag=%s class=%s aria=%s text="%s" html="%s" run_id=%s',
                                item_idx,
                                marker_idx,
                                m.get('phrase'),
                                m.get('tag'),
                                m.get('cls'),
                                m.get('aria'),
                                (m.get('txt') or '')[:180],
                                (m.get('html') or '')[:220],
                                scrape_run_id,
                            )
                    except Exception as marker_err:
                        logger.debug(
                            'Interactive description markers item=%d success=False error=%s run_id=%s',
                            item_idx,
                            marker_err,
                            scrape_run_id,
                        )

                _log_description_markers()

                # Expand inline "Product details" sections when present.
                expand_selectors = [
                    'button[aria-label="Product details"]',
                    'button[aria-label*="details"]',
                    'button[data-dca-id][aria-label="Product details"]',
                    'button:has-text("View all item details")',
                    'button:has-text("About this item")',
                ]

                selectors = [
                    'div.dangerous-html',
                    'div.dangerous-html.mb3',
                    'div[data-testid="product-details"]',
                    'div[data-automation-id="product-details"]',
                    'div.search-result-productdescription',
                    'div.prod-ProductCard-description',
                    '[data-automation-id="product-abstract"]',
                    '[data-testid="product-description"]',
                    'div[class*="line-clamp"]',
                ]
                max_rounds = 10
                selector_attempt = 0
                for round_no in range(1, max_rounds + 1):
                    for expand_idx, expand_sel in enumerate(expand_selectors, start=1):
                        try:
                            btn = card_el.query_selector(expand_sel)
                            if not btn:
                                logger.debug(
                                    'Interactive quick description round=%d expand=%d item=%d selector=%s success=False reason=no_button run_id=%s',
                                    round_no, expand_idx, item_idx, expand_sel, scrape_run_id
                                )
                                continue
                            expanded_state = (btn.get_attribute('aria-expanded') or '').strip().lower()
                            if expanded_state == 'true':
                                logger.debug(
                                    'Interactive quick description round=%d expand=%d item=%d selector=%s success=True reason=already_expanded run_id=%s',
                                    round_no, expand_idx, item_idx, expand_sel, scrape_run_id
                                )
                            else:
                                btn.click(timeout=700)
                                logger.info(
                                    'Interactive quick description round=%d expand=%d item=%d selector=%s success=True run_id=%s',
                                    round_no, expand_idx, item_idx, expand_sel, scrape_run_id
                                )
                        except Exception as e:
                            logger.debug(
                                'Interactive quick description round=%d expand=%d item=%d selector=%s success=False error=%s run_id=%s',
                                round_no, expand_idx, item_idx, expand_sel, e, scrape_run_id
                            )

                    for selector in selectors:
                        selector_attempt += 1
                        try:
                            node = card_el.query_selector(selector)
                            txt = (node.inner_text() or '').strip() if node else ''
                            if txt:
                                txt = re.sub(r'\s+', ' ', txt).strip()
                                # remove duplicated section heading prefix
                                txt = re.sub(r'^\s*product details\s*[:\-]?\s*', '', txt, flags=re.IGNORECASE)
                            # reject title-only / near-title strings
                            name_norm = re.sub(r'\s+', ' ', (product_name or '').strip()).lower()
                            txt_norm = (txt or '').lower()
                            too_similar_to_title = bool(name_norm and (txt_norm == name_norm or txt_norm.startswith(name_norm)) and len(txt_norm) <= len(name_norm) + 18)

                            if txt and len(txt) >= 40 and not too_similar_to_title:
                                clean = re.sub(r'\s+', ' ', txt).strip()
                                logger.info(
                                    'Interactive quick description extracted item=%d round=%d attempt=%d selector=%s chars=%d run_id=%s',
                                    item_idx, round_no, selector_attempt, selector, len(clean), scrape_run_id
                                )
                                return clean, f'card:{selector}'
                            logger.debug(
                                'Interactive quick description round=%d attempt=%d item=%d selector=%s success=False run_id=%s',
                                round_no, selector_attempt, item_idx, selector, scrape_run_id
                            )
                        except Exception as e:
                            logger.debug(
                                'Interactive quick description round=%d attempt=%d item=%d selector=%s error=%s run_id=%s',
                                round_no, selector_attempt, item_idx, selector, e, scrape_run_id
                            )
                    try:
                        card_el.evaluate("(n) => n && n.scrollIntoView({block:'center', inline:'nearest'})")
                    except Exception:
                        pass
                    try:
                        page.wait_for_timeout(75)
                    except Exception:
                        pass

                # Fallback: derive a clean sentence from card text without title/price noise.
                try:
                    raw = (card_el.inner_text() or '').strip()
                    lines = [re.sub(r'\s+', ' ', ln).strip() for ln in raw.splitlines()]
                    filtered = []
                    name_norm = (product_name or '').strip().lower()
                    for ln in lines:
                        low = ln.lower()
                        if not ln or len(ln) < 12:
                            continue
                        if name_norm and low == name_norm:
                            continue
                        if '$' in ln or 'current price' in low or 'options from' in low or 'shipping' in low:
                            continue
                        if 'pickup' in low or 'delivery' in low or 'add to cart' in low:
                            continue
                        filtered.append(ln)
                    if filtered:
                        joined = ' '.join(filtered[:2]).strip()
                        if len(joined) >= 24:
                            logger.info(
                                'Interactive quick description extracted item=%d source=card_text_fallback chars=%d run_id=%s',
                                item_idx, len(joined), scrape_run_id
                            )
                            return joined, 'card:card_text_fallback'
                except Exception as e:
                    logger.debug('Interactive quick description card_text fallback failed item=%d error=%s run_id=%s', item_idx, e, scrape_run_id)

                logger.warning('Interactive quick description not found item=%d run_id=%s', item_idx, scrape_run_id)
                return None, None

            def _extract_key_item_features(context_obj, product_link, item_idx):
                """Target Walmart PDP 'Key Item Features' section via fast HTTP fetch in same session."""
                if not product_link:
                    logger.debug(
                        'Interactive key-features item=%d success=False reason=no_link run_id=%s',
                        item_idx, scrape_run_id
                    )
                    return None, None

                attempt_errors = []
                html = ''
                for fetch_attempt in range(1, 4):
                    try:
                        resp = context_obj.request.get(product_link, timeout=7000)
                        status = resp.status
                        html = resp.text() if status < 500 else ''
                        logger.debug(
                            'Interactive key-features fetch item=%d attempt=%d status=%s bytes=%d run_id=%s',
                            item_idx, fetch_attempt, status, len(html or ''), scrape_run_id
                        )
                        if status in (200, 201) and html:
                            break
                    except Exception as fetch_err:
                        attempt_errors.append(str(fetch_err))
                        logger.debug(
                            'Interactive key-features fetch item=%d attempt=%d success=False error=%s run_id=%s',
                            item_idx, fetch_attempt, fetch_err, scrape_run_id
                        )

                if not html:
                    logger.warning(
                        'Interactive key-features item=%d success=False reason=empty_html errors=%s run_id=%s',
                        item_idx, attempt_errors[:2], scrape_run_id
                    )
                    return None, None

                # Diagnostics to understand misses across Walmart layout variants.
                try:
                    heading_hits = re.findall(r'Key\s*Item\s*Features', html, flags=re.IGNORECASE)
                    li_hits = re.findall(r'<li\b', html, flags=re.IGNORECASE)
                    ph3_hits = re.findall(r'class="[^"]*\bph3\b[^"]*"', html, flags=re.IGNORECASE)
                    view_all_hits = re.findall(r'View all item details', html, flags=re.IGNORECASE)
                    ai_hits = re.findall(r'Generated by AI', html, flags=re.IGNORECASE)
                    logger.debug(
                        'Interactive key-features diagnostics item=%d run_id=%s heading_hits=%d li_hits=%d ph3_hits=%d view_all_hits=%d ai_hits=%d html_bytes=%d',
                        item_idx,
                        scrape_run_id,
                        len(heading_hits),
                        len(li_hits),
                        len(ph3_hits),
                        len(view_all_hits),
                        len(ai_hits),
                        len(html),
                    )
                    hm = re.search(r'Key\s*Item\s*Features', html, flags=re.IGNORECASE)
                    if hm:
                        ctx = html[max(0, hm.start() - 220): min(len(html), hm.start() + 320)]
                        ctx = re.sub(r'\s+', ' ', ctx).strip()
                        logger.debug(
                            'Interactive key-features heading context item=%d run_id=%s snippet="%s"',
                            item_idx, scrape_run_id, ctx[:280]
                        )
                except Exception as diag_err:
                    logger.debug(
                        'Interactive key-features diagnostics item=%d success=False error=%s run_id=%s',
                        item_idx, diag_err, scrape_run_id
                    )

                def _clean_li_text(li_html):
                    txt = re.sub(r'<[^>]+>', ' ', li_html)
                    txt = re.sub(r'&nbsp;|&#160;', ' ', txt, flags=re.IGNORECASE)
                    txt = re.sub(r'&amp;', '&', txt)
                    txt = re.sub(r'&quot;|&#34;', '"', txt)
                    txt = re.sub(r'&#39;|&apos;', "'", txt)
                    txt = re.sub(r'\s+', ' ', txt).strip()
                    return txt

                def _format_feature_list(raw_items):
                    cleaned = []
                    seen = set()
                    for li in raw_items:
                        txt = _clean_li_text(li)
                        if not txt or len(txt) < 4:
                            continue
                        low = txt.lower()
                        if low in seen:
                            continue
                        seen.add(low)
                        cleaned.append(txt)
                        if len(cleaned) >= 8:
                            break
                    if not cleaned:
                        return None
                    return '; '.join(cleaned[:6]), len(cleaned)

                # Try 1: explicit "ph3 -> ul/li" structure (like user-provided snippet).
                try:
                    ph3_blocks = re.findall(
                        r'<div[^>]*class="[^"]*\bph3\b[^"]*"[^>]*>(.*?)</div>',
                        html,
                        flags=re.IGNORECASE | re.DOTALL,
                    )
                    for bidx, block in enumerate(ph3_blocks, start=1):
                        lis = re.findall(r'<li[^>]*>(.*?)</li>', block, flags=re.IGNORECASE | re.DOTALL)
                        if not lis:
                            continue
                        formatted = _format_feature_list(lis)
                        if formatted:
                            text, count = formatted
                            logger.info(
                                'Interactive key-features extracted item=%d source=ph3_ul_li block=%d count=%d chars=%d run_id=%s',
                                item_idx, bidx, count, len(text), scrape_run_id
                            )
                            return text, 'pdp:key_item_features_ph3'
                    logger.debug(
                        'Interactive key-features item=%d source=ph3_ul_li success=False run_id=%s',
                        item_idx, scrape_run_id
                    )
                except Exception as parse_err:
                    logger.debug(
                        'Interactive key-features item=%d source=ph3_ul_li success=False error=%s run_id=%s',
                        item_idx, parse_err, scrape_run_id
                    )

                # Try 2: explicit heading + nearby list items (both before/after heading).
                try:
                    m = re.search(r'Key\s*Item\s*Features', html, flags=re.IGNORECASE)
                    if m:
                        start = max(0, m.start() - 14000)
                        end = min(len(html), m.start() + 14000)
                        window = html[start:end]
                        lis = re.findall(r'<li[^>]*>(.*?)</li>', window, flags=re.IGNORECASE | re.DOTALL)
                        formatted = _format_feature_list(lis)
                        if formatted:
                            text, count = formatted
                            logger.info(
                                'Interactive key-features extracted item=%d source=heading_window_li count=%d chars=%d run_id=%s',
                                item_idx, count, len(text), scrape_run_id
                            )
                            return text, 'pdp:key_item_features'
                        logger.debug(
                            'Interactive key-features item=%d source=heading_window_li success=False reason=no_li_near_heading run_id=%s',
                            item_idx, scrape_run_id
                        )
                    else:
                        logger.debug(
                            'Interactive key-features item=%d source=heading_li success=False reason=no_heading run_id=%s',
                            item_idx, scrape_run_id
                        )
                except Exception as parse_err:
                    logger.debug(
                        'Interactive key-features item=%d source=heading_li success=False error=%s run_id=%s',
                        item_idx, parse_err, scrape_run_id
                    )

                # Try 3: JSON-like keyItemFeatures arrays embedded in scripts.
                try:
                    jm = re.search(
                        r'"keyItemFeatures"\s*:\s*\[(.*?)\]',
                        html,
                        flags=re.IGNORECASE | re.DOTALL
                    )
                    if jm:
                        raw_block = jm.group(1)
                        quoted = re.findall(r'"([^"\\\\]*(?:\\\\.[^"\\\\]*)*)"', raw_block)
                        clean_items = []
                        for q in quoted:
                            txt = q.encode('utf-8').decode('unicode_escape', errors='ignore')
                            txt = re.sub(r'\s+', ' ', txt).strip()
                            if txt and len(txt) >= 4:
                                clean_items.append(txt)
                            if len(clean_items) >= 8:
                                break
                        if clean_items:
                            text = '; '.join(clean_items[:6])
                            logger.info(
                                'Interactive key-features extracted item=%d source=json_keyItemFeatures count=%d chars=%d run_id=%s',
                                item_idx, len(clean_items), len(text), scrape_run_id
                            )
                            return text, 'pdp:key_item_features_json'
                    logger.debug(
                        'Interactive key-features item=%d source=json_keyItemFeatures success=False run_id=%s',
                        item_idx, scrape_run_id
                    )
                except Exception as parse_err:
                    logger.debug(
                        'Interactive key-features item=%d source=json_keyItemFeatures success=False error=%s run_id=%s',
                        item_idx, parse_err, scrape_run_id
                    )

                logger.warning(
                    'Interactive key-features item=%d success=False reason=not_found run_id=%s',
                    item_idx, scrape_run_id
                )
                return None, None

            for i, el in enumerate(elems[:num_products]):
                try:
                    # TITLE: multiple fallbacks
                    name_el = el.query_selector('span.normal') or el.query_selector('span[data-automation-id="product-title"]') or el.query_selector('a > span') or el.query_selector('h2')
                    raw_name = name_el.inner_text().strip() if name_el else 'Unknown Item'
                    name = _clean_title_text(raw_name, i)

                    # PRICE: multi-selector attempts + full-card regex fallback
                    raw_price_text = ''
                    price = None
                    try:
                        # Walmart often splits dollars/cents; combine explicitly first.
                        dollars_el = el.query_selector('span.price-characteristic')
                        cents_el = el.query_selector('span.price-mantissa')
                        if dollars_el:
                            dollars = (dollars_el.get_attribute('content') or dollars_el.inner_text() or '').strip()
                            cents = (cents_el.get_attribute('content') or cents_el.inner_text() or '').strip() if cents_el else ''
                            dollars_digits = re.sub(r'[^0-9]', '', dollars)
                            cents_digits = re.sub(r'[^0-9]', '', cents)
                            if dollars_digits:
                                if cents_digits:
                                    cents_digits = cents_digits[:2].ljust(2, '0')
                                    price = float(f"{int(dollars_digits)}.{cents_digits}")
                                    raw_price_text = f"${int(dollars_digits)}.{cents_digits}"
                                else:
                                    price = float(int(dollars_digits))
                                    raw_price_text = f"${int(dollars_digits)}"
                                logger.debug(
                                    'Interactive price split parse item=%d success=True dollars=%s cents=%s price=%s',
                                    i, dollars_digits, cents_digits, price
                                )
                    except Exception as split_err:
                        logger.debug('Interactive price split parse item=%d success=False error=%s', i, split_err)

                    price_attempts = [
                        ('div[data-automation-id="product-price"]', 'inner_text'),
                        ('div[data-automation-id="product-price"] span', 'inner_text'),
                        ('span.price-characteristic', 'attr_content'),
                        ('span[data-automation-id="product-price"]', 'inner_text'),
                        ('[itemprop="price"]', 'attr_content'),
                        ('span[class*="price"]', 'inner_text'),
                    ]
                    for attempt_no, (selector, mode) in enumerate(price_attempts, start=1):
                        if price is not None:
                            break
                        try:
                            node = el.query_selector(selector)
                            if not node:
                                logger.debug('Interactive price attempt %d item=%d selector=%s success=False reason=no_node', attempt_no, i, selector)
                                continue
                            candidate = (node.get_attribute('content') if mode == 'attr_content' else node.inner_text()) or ''
                            candidate = candidate.strip()
                            candidate_price = _parse_price_value(candidate)
                            logger.debug(
                                'Interactive price attempt %d item=%d selector=%s raw="%s" success=%s',
                                attempt_no, i, selector, candidate[:120], bool(candidate_price is not None)
                            )
                            if candidate_price is not None:
                                raw_price_text = candidate
                                price = candidate_price
                                break
                        except Exception as attempt_err:
                            logger.debug('Interactive price attempt %d item=%d selector=%s success=False error=%s', attempt_no, i, selector, attempt_err)

                    if price is None:
                        card_text = (el.inner_text() or '').strip()
                        price = _parse_price_value(card_text)
                        raw_price_text = card_text[:160]
                        logger.debug('Interactive price fallback item=%d source=card_text success=%s raw="%s"', i, bool(price is not None), raw_price_text)

                    logger.debug('Interactive parse - item %d raw price: "%s"', i, raw_price_text)

                    # IMAGE
                    img_el = el.query_selector('img')
                    image = img_el.get_attribute('src') if img_el else None

                    # LINK
                    link_el = el.query_selector('a')
                    raw_link = link_el.get_attribute('href') if link_el else None
                    link = _normalize_product_link(raw_link)
                    logger.debug('Interactive link parse item=%d run_id=%s raw_link=%s normalized_link=%s', i, scrape_run_id, raw_link, link)

                    # SHORT DESCRIPTION (if present on card)
                    description, description_source = _extract_quick_description(el, i, name)
                    if (not description) or (description_source == 'card:card_text_fallback'):
                        kf_desc, kf_source = _extract_key_item_features(context, link, i)
                        if kf_desc:
                            description = kf_desc
                            description_source = kf_source
                            logger.info(
                                'Interactive description replaced by key-features item=%d source=%s chars=%d run_id=%s',
                                i, description_source, len(description), scrape_run_id
                            )

                    products.append({
                        'name': name,
                        'price': price,
                        'image': image,
                        'link': link,
                        'description': description,
                        'description_source': description_source,
                    })
                    logger.info('Parsed interactive item %d: %s — $%s', i, (name[:60] + '...') if len(name) > 60 else name, price)
                except Exception as e:
                    logger.exception('Failed to parse interactive element %s', e)

            # persist storage state
            try:
                context.storage_state(path=str(storage_path))
                logger.info('Saved Playwright storage state -> %s', storage_path)
            except Exception:
                logger.exception('Failed to save storage state')

            browser.close()

        # Save to DB and log details
        try:
            saved = _save_products_to_db(products, search_term=search_term)
        except Exception:
            logger.exception('DB save failed for interactive products')
            saved = []

        # Force-print saved IDs/status for clarity
        for s in saved:
            logger.info('DB save result: %s', s)

        resp = {'count': len(products), 'products': products, 'saved': saved}
        try:
            if storage_path.exists():
                resp['storage_state'] = str(storage_path)
        except Exception:
            logger.exception('Error checking storage_state file for interactive flow')

        logger.info('Interactive captcha solved — returning %d products', len(products))
        return jsonify(resp)

    except Exception as e:
        logger.exception('Interactive captcha flow failed')
        return jsonify({'error': str(e)}), 500

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

    scrape_run_id = f"run-{uuid.uuid4().hex[:10]}"
    logger.info(
        "Scrape request received run_id=%s search_term=%s target_count=%s min_price=%s max_price=%s",
        scrape_run_id, search_term, num_products, min_price, max_price
    )

    def _load_scrapy_output(path):
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            parsed = []
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed.append(json.loads(line))
                except Exception:
                    logger.warning('run_id=%s failed to parse scrapy output line: %s', scrape_run_id, line[:200])
            logger.warning('run_id=%s scrapy JSON malformed; parsed %d JSONL rows', scrape_run_id, len(parsed))
            return parsed

    max_attempts = 3
    attempt = 0
    collected = []
    seen_links = set()
    while len(collected) < num_products and attempt < max_attempts:
        attempt += 1
        output_path = _unique_output_file()
        output_name = output_path.name
        remaining_target = num_products - len(collected)
        max_pages = 8 + (attempt - 1) * 4

        scrapy_command = [
            'python', '-m', 'scrapy', 'crawl', 'walmart',
            '-a', f'search_term={search_term}',
            '-a', f'min_price={min_price}',
            '-a', f'max_price={max_price}',
            '-a', f'num_products={remaining_target}',
            '-a', f'max_pages={max_pages}',
            '-a', f'scrape_run_id={scrape_run_id}-a{attempt}',
            '-o', output_name
        ]
        logger.info(
            'run_id=%s attempt=%s starting scrapy cmd=%s',
            scrape_run_id, attempt, ' '.join(scrapy_command)
        )

        started = time.time()
        try:
            proc = subprocess.run(
                scrapy_command,
                check=True,
                cwd=str(WALMART_DIR),
                timeout=600,
                capture_output=True,
                text=True,
            )
            elapsed = round(time.time() - started, 2)
            stdout_tail = (proc.stdout or '')[-1500:]
            stderr_tail = (proc.stderr or '')[-1500:]
            logger.debug('run_id=%s attempt=%s scrapy stdout tail:\n%s', scrape_run_id, attempt, stdout_tail)
            logger.debug('run_id=%s attempt=%s scrapy stderr tail:\n%s', scrape_run_id, attempt, stderr_tail)
            logger.info('run_id=%s attempt=%s scrapy completed in %ss', scrape_run_id, attempt, elapsed)
        except subprocess.TimeoutExpired:
            logger.exception('run_id=%s attempt=%s scrapy timed out', scrape_run_id, attempt)
            return jsonify({'error': 'Scraping timed out'}), 504
        except subprocess.CalledProcessError as e:
            logger.exception('run_id=%s attempt=%s scrapy failed', scrape_run_id, attempt)
            return jsonify({'error': 'Scrapy failed', 'detail': (e.stderr or str(e))[-800:]}), 500

        try:
            products = _load_scrapy_output(output_path)
        except FileNotFoundError:
            logger.error('run_id=%s attempt=%s output missing at %s', scrape_run_id, attempt, output_path)
            return jsonify({'error': 'Scrape output missing'}), 500

        logger.info('run_id=%s attempt=%s parsed %s raw products', scrape_run_id, attempt, len(products))
        for idx, product in enumerate(products, start=1):
            missing = _product_missing_fields(product)
            link = product.get('link')
            logger.info(
                'run_id=%s attempt=%s product_idx=%s field_status title=%s price=%s image=%s link=%s description=%s shipping=%s image_urls_count=%s missing=%s',
                scrape_run_id,
                attempt,
                idx,
                bool(product.get('name')),
                bool(product.get('price') is not None),
                bool(product.get('image')),
                bool(link),
                bool(product.get('description')),
                bool(product.get('shipping')),
                len(product.get('images') or []),
                missing,
            )
            if link and link in seen_links:
                logger.debug('run_id=%s attempt=%s duplicate product skipped link=%s', scrape_run_id, attempt, link)
                continue
            if not _product_is_valid(product):
                logger.warning(
                    'run_id=%s attempt=%s rejected product idx=%s missing=%s link=%s',
                    scrape_run_id, attempt, idx, missing, link
                )
                continue
            if link:
                seen_links.add(link)
            collected.append(product)
            logger.info(
                'run_id=%s attempt=%s accepted product idx=%s collected=%s/%s link=%s',
                scrape_run_id, attempt, idx, len(collected), num_products, link
            )
            if len(collected) >= num_products:
                break

        logger.info(
            'run_id=%s attempt=%s complete; collected=%s/%s',
            scrape_run_id, attempt, len(collected), num_products
        )

    products = collected[:num_products]
    logger.info(
        'run_id=%s scrape finished collected=%s requested=%s attempts=%s shortfall=%s',
        scrape_run_id, len(products), num_products, attempt, max(0, num_products - len(products))
    )

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

    resp = {'count': len(products), 'products': products, 'saved': saved, 'run_id': scrape_run_id, 'requested_count': num_products}
    if debug_html_path:
        resp['debug_html'] = str(debug_html_path)
    if debug_screenshot_path:
        resp['debug_screenshot'] = str(debug_screenshot_path)
    if captcha_detected:
        resp['captcha_detected'] = True
    if len(products) < num_products:
        resp['shortfall'] = num_products - len(products)

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
