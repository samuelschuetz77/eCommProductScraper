# Logging Vision

## Goal
Provide exhaustive, actionable scrape logs so failures can be diagnosed without reproducing manually.

## Required Product Fields
- `name` (title)
- `price`
- `image` (primary image)
- `images` (all discovered product image URLs from detail page/gallery when possible)
- `shipping` (best-effort; optional)
- `description` (best-effort; optional)
- `link` (canonical product page URL)

## Search-Level Logging Contract
- Each scrape run gets a `run_id`.
- Log request envelope:
  - search term
  - requested product count
  - price filters
  - attempt number
  - page number
- Log scraper command and completion status for every attempt.
- Log stdout/stderr tails from scraper subprocess for fast diagnosis.
- Log final run outcome:
  - requested count
  - valid collected count
  - attempt count
  - shortfall (if any)

## Product-Level Logging Contract
- For each candidate product, log field status explicitly:
  - title success/failure
  - price success/failure
  - image success/failure
  - link success/failure
  - description success/failure
  - shipping success/failure
  - image URL count
- If rejected, log exact missing required fields.
- If duplicate, log duplicate reason and link.
- If accepted, log accepted reason and running count (`collected=X/Y`).

## Field Attempt Logging (Selector Tries)
- Every extraction path uses ordered attempts.
- Log each attempt with:
  - `field`
  - `attempt` number (`1`, `2`, `3`, ...)
  - selector used
  - extract mode (`text`, `attr`, `all_attr`)
  - success/failure
  - error string (if selector/parse failed)
- If fallback path is entered (JSON -> DOM -> detail page), log transition explicitly.

## Failure Taxonomy
- `JSON extraction failed`: parsing or schema mismatch in `__NEXT_DATA__`.
- `DOM extraction failed`: selectors returned no candidates or required fields.
- `Detail enrichment failed`: detail page visited but required fields still missing.
- `Price filter reject`: product parsed but outside min/max bounds.
- `Duplicate reject`: previously accepted link encountered again.
- `Output parse failure`: malformed scraper output row/line.
- `Subprocess failure`: timeout or crawler non-zero exit.

## Requested Count Behavior
- If user requests `N`, system should continue attempts and paging to obtain `N` valid products.
- Invalid products do not count toward `N`.
- If a candidate fails criteria, keep searching and replace it with another candidate.
- If target cannot be reached after configured hard stops (attempt/page limits):
  - return best-effort results
  - include `shortfall`
  - log precise reason and where collection stopped

## UI Expectations
- Product link text should be displayed as `product page` (not raw URL text).
- Raw URL remains in `href`.

## Persistence and Diagnostics
- Write logs to console and `logs/scrape.log`.
- Keep incomplete/raw product payloads in DB `raw` field for forensic review.
- Keep optional debug HTML/screenshot capture path logging for blocked/captcha states.
