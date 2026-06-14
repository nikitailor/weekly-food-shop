#!/usr/bin/env python3
"""
ocado_shopper.py
Reads your Apple Reminders "Food Shopping" list and adds items to your Ocado basket.
- Prefers favourited items
- Falls back to top-rated result, logging alternatives for review
- Handles quantities (2x, 500g) and flags ambiguous weights
"""

import subprocess
import re
import time
import random
import json
import os
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ── Config ────────────────────────────────────────────────────────────────────
SHOPPING_LIST_FILE = os.path.join(os.path.dirname(__file__), "shopping_list.txt")
SESSION_FILE       = os.path.expanduser("~/.ocado_session.json")
LOG_DIR            = os.path.expanduser("~/ocado_logs")
OCADO_URL          = "https://www.ocado.com"
OCADO_LOGIN_URL    = "https://www.ocado.com/authentication?target=/"
HEADLESS           = os.environ.get("OCADO_HEADLESS", "false").lower() == "true"


# ── Shopping list ─────────────────────────────────────────────────────────────
def get_shopping_list(path: str = SHOPPING_LIST_FILE) -> list[str]:
    """Read items from shopping_list.txt — one item per line, # lines are comments."""
    with open(path) as f:
        lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    return lines


# ── Quantity parsing ──────────────────────────────────────────────────────────
WEIGHT_RE    = re.compile(r'^(\d+(?:\.\d+)?)\s*(g|kg|ml|l)\s+(.+)$', re.IGNORECASE)
QUANTITY_RE  = re.compile(r'^(\d+)\s*x\s*(.+)$', re.IGNORECASE)
QUANTITY_RE2 = re.compile(r'^x\s*(\d+)\s+(.+)$', re.IGNORECASE)

def parse_item(raw: str) -> dict:
    """
    Parse a reminder string into a structured item dict.
    Returns: {name, count, weight_g, weight_unit, raw, weight_specified}
    """
    item = {"raw": raw, "name": raw, "count": 1,
            "weight_g": None, "weight_unit": None, "weight_specified": False}

    # Weight prefix: 500g chicken breast
    m = WEIGHT_RE.match(raw)
    if m:
        val, unit, name = m.group(1), m.group(2).lower(), m.group(3).strip()
        item["name"]           = name
        item["weight_unit"]    = unit
        item["weight_specified"] = True
        if unit in ("kg", "l"):
            item["weight_g"] = float(val) * 1000
        else:
            item["weight_g"] = float(val)
        return item

    # Count prefix: 2x oat milk  /  x2 oat milk
    for rx in (QUANTITY_RE, QUANTITY_RE2):
        m = rx.match(raw)
        if m:
            item["count"] = int(m.group(1))
            item["name"]  = m.group(2).strip()
            return item

    return item


# ── Logging ───────────────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)

def new_log() -> dict:
    return {"date": datetime.now().isoformat(), "added": [], "review": [], "errors": []}

def save_log(log: dict):
    filename = os.path.join(LOG_DIR, f"ocado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(filename, "w") as f:
        json.dump(log, f, indent=2)
    return filename

def print_summary(log: dict):
    print("\n" + "═"*60)
    print("  OCADO SHOPPER — SUMMARY")
    print("═"*60)

    if log["added"]:
        print(f"\n✅  Added to basket ({len(log['added'])} items):")
        for a in log["added"]:
            fav = " ★ favourite" if a.get("favourite") else ""
            print(f"    • {a['name']} × {a['count']}{fav}")
            print(f"      {a['product']} | {a['price']} | {a['size']} | {a['per_unit']}")

    if log["review"]:
        print(f"\n⚠️   Needs your review ({len(log['review'])} items):")
        for r in log["review"]:
            print(f"\n    {r['raw']} — {r['reason']}")
            print(f"    Added: {r['picked']['title']} | {r['picked']['price']} | {r['picked']['size']} | {r['picked']['per_unit']}")
            if r.get("alternatives"):
                print(f"    Alternatives:")
                for i, alt in enumerate(r["alternatives"], 1):
                    print(f"      {i}. {alt['title']} | {alt['price']} | {alt['size']} | {alt['per_unit']}")

    if log["errors"]:
        print(f"\n❌  Errors ({len(log['errors'])} items):")
        for e in log["errors"]:
            print(f"    • {e['raw']}: {e['error']}")

    print("\n" + "═"*60)


# ── Browser session ───────────────────────────────────────────────────────────
def load_cookies(context):
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE) as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        return True
    return False

def save_cookies(context):
    cookies = context.cookies()
    # Restrict file permissions before writing
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    with os.fdopen(os.open(SESSION_FILE, flags, 0o600), "w") as f:
        json.dump(cookies, f)

def is_logged_in(page) -> bool:
    return "authentication" not in page.url and page.query_selector("[data-test='account-menu']") is not None

def dismiss_cookie_banner(page):
    """Wait for and dismiss Ocado's OneTrust cookie consent banner."""
    cookie_selectors = [
        "button#onetrust-accept-btn-handler",
        "button#accept-recommended-btn-handler",
        "button[id*='accept']",
        "[class*='cookie'] button[class*='accept']",
    ]
    for selector in cookie_selectors:
        try:
            page.wait_for_selector(selector, timeout=8000, state="visible")
            page.click(selector)
            print("   ✅ Cookie banner dismissed.")
            human_delay(1.0, 1.5)
            return
        except Exception:
            continue
    print("   (No cookie banner found — continuing.)")

def login(page, email: str, password: str):
    print("🔐  Logging in to Ocado...")
    page.goto(OCADO_LOGIN_URL, wait_until="networkidle")
    print(f"   Page title: {page.title()} | URL: {page.url}")
    page.screenshot(path="login_page.png", full_page=True)
    dismiss_cookie_banner(page)

    # Try multiple selectors for the email field
    email_selectors = ["#email", "input[name='email']", "input[type='email']", "[autocomplete='email']"]
    filled = False
    for sel in email_selectors:
        try:
            page.wait_for_selector(sel, timeout=20000, state="visible")
            page.fill(sel, email)
            filled = True
            break
        except Exception:
            continue

    if not filled:
        # Dump all input fields and frames to help diagnose selector issues
        inputs = page.query_selector_all("input")
        print(f"   Found {len(inputs)} input element(s) on page:")
        for inp in inputs:
            print(f"     id={inp.get_attribute('id')} name={inp.get_attribute('name')} "
                  f"type={inp.get_attribute('type')} autocomplete={inp.get_attribute('autocomplete')}")
        frames = page.frames
        print(f"   Found {len(frames)} frame(s): {[f.url for f in frames]}")
        # Check inside any iframes for input fields
        for frame in frames[1:]:
            frame_inputs = frame.query_selector_all("input")
            if frame_inputs:
                print(f"   Frame {frame.url} has {len(frame_inputs)} input(s):")
                for inp in frame_inputs:
                    print(f"     id={inp.get_attribute('id')} name={inp.get_attribute('name')} "
                          f"type={inp.get_attribute('type')}")
        page.screenshot(path="login_failed.png", full_page=True)
        raise RuntimeError("Could not find email field on Ocado login page. Screenshot saved as login_failed.png")

    page.fill("input[name='password'], #password, input[type='password']", password)
    page.click("[data-test='login-button'], button[type='submit']")
    page.wait_for_url(lambda url: "authentication" not in url, timeout=20000)
    print("✅  Logged in.")


# ── Scraping helpers ──────────────────────────────────────────────────────────
def human_delay(min_s=0.8, max_s=2.2):
    time.sleep(random.uniform(min_s, max_s))

def parse_price_text(text: str) -> str:
    """Return price string, cleaned up."""
    return text.strip() if text else "—"

def extract_product_info(card) -> dict:
    """Extract title, price, size, per_unit from a search result card."""
    def safe(selector, attr="innerText"):
        el = card.query_selector(selector)
        if not el:
            return "—"
        return (el.inner_text() if attr == "innerText" else el.get_attribute(attr) or "—").strip()

    title    = safe("[class*='productTitle'], [data-test='product-title'], h4")
    price    = safe("[class*='price']:not([class*='perUnit']), [data-test='product-price']")
    size     = safe("[class*='productSize'], [data-test='product-size'], [class*='size']")
    per_unit = safe("[class*='perUnit'], [data-test='price-per-unit']")

    return {"title": title, "price": price, "size": size, "per_unit": per_unit}

def search_products(page, query: str) -> list:
    """Search Ocado and return list of product card elements."""
    search_url = f"{OCADO_URL}/search?entry={query.replace(' ', '+')}"
    page.goto(search_url, wait_until="networkidle")
    human_delay()
    cards = page.query_selector_all("[class*='ProductCard'], [data-test='product-card'], li[class*='product']")
    return cards

def is_favourited(card) -> bool:
    """Check if a product card is marked as a favourite."""
    fav = card.query_selector("[class*='favourite'][class*='active'], [data-test='fav-button'][aria-pressed='true'], [class*='Favourite'][class*='selected']")
    return fav is not None

def add_to_basket(card, page):
    """Click the add-to-basket button on a product card."""
    btn = card.query_selector("[data-test='add-to-trolley'], button[class*='add'], [class*='AddButton']")
    if btn:
        btn.click()
        human_delay(0.5, 1.2)
    else:
        raise RuntimeError("Could not find add-to-basket button")

def get_weight_grams(size_str: str) -> float | None:
    """Parse a size string like '500g' or '1kg' into grams."""
    m = re.search(r'(\d+(?:\.\d+)?)\s*(g|kg|ml|l)', size_str, re.IGNORECASE)
    if not m:
        return None
    val, unit = float(m.group(1)), m.group(2).lower()
    return val * 1000 if unit in ("kg", "l") else val


# ── Core item processing ──────────────────────────────────────────────────────
def process_item(page, item: dict, log: dict):
    name  = item["name"]
    count = item["count"]
    raw   = item["raw"]

    print(f"\n🔍  Searching: {raw}")
    cards = search_products(page, name)

    if not cards:
        log["errors"].append({"raw": raw, "error": "No results found on Ocado"})
        print(f"   ❌  No results found.")
        return

    # ── Extract info from all cards ──
    products = []
    for card in cards[:8]:
        info = extract_product_info(card)
        info["card"]       = card
        info["favourited"] = is_favourited(card)
        info["weight_g"]   = get_weight_grams(info["size"])
        products.append(info)

    # ── Check for favourites first ──
    favourites = [p for p in products if p["favourited"]]

    if favourites:
        chosen = favourites[0]
        for _ in range(count):
            add_to_basket(chosen["card"], page)
            human_delay(0.4, 0.9)
        log["added"].append({
            "raw": raw, "name": name, "count": count,
            "favourite": True,
            "product": chosen["title"],
            "price": chosen["price"],
            "size": chosen["size"],
            "per_unit": chosen["per_unit"]
        })
        print(f"   ★  Favourite found: {chosen['title']} × {count}")
        return

    # ── No favourite — apply weight logic or pick top result ──
    reason = None
    candidates = products

    if item["weight_specified"] and item["weight_g"]:
        target = item["weight_g"]
        # Find closest size >= target
        weighted = [(abs(p["weight_g"] - target), p) for p in products if p["weight_g"] is not None]
        weighted.sort(key=lambda x: x[0])
        if weighted:
            candidates = [w[1] for w in weighted]
        chosen = candidates[0]
        reason = f"matched to {item['raw']} (no favourite)"

    elif not item["weight_specified"] and item["weight_g"] is None:
        # No weight given and item looks weight-based — pick largest
        with_weight = [p for p in products if p["weight_g"] is not None]
        if with_weight:
            with_weight.sort(key=lambda p: p["weight_g"], reverse=True)
            chosen  = with_weight[0]
            candidates = with_weight
            reason  = "no weight specified — picked largest available"
        else:
            chosen = products[0]
            reason = "no favourite, picked top result"
    else:
        chosen = products[0]
        reason = "no favourite, picked top result"

    # Add to basket
    for _ in range(count):
        add_to_basket(chosen["card"], page)
        human_delay(0.4, 0.9)

    alternatives = [
        {"title": p["title"], "price": p["price"], "size": p["size"], "per_unit": p["per_unit"]}
        for p in candidates[1:4]
    ]

    log["review"].append({
        "raw": raw, "reason": reason,
        "picked": {"title": chosen["title"], "price": chosen["price"],
                   "size": chosen["size"], "per_unit": chosen["per_unit"]},
        "alternatives": alternatives
    })
    print(f"   ⚠️   Added (needs review): {chosen['title']} × {count} — {reason}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # 1. Credentials
    email    = os.environ.get("OCADO_EMAIL", "").strip()
    password = os.environ.get("OCADO_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError(
            "OCADO_EMAIL and OCADO_PASSWORD environment variables must be set.\n"
            "Locally: export OCADO_EMAIL=you@example.com OCADO_PASSWORD=yourpassword\n"
            "In GitHub Actions: add them as repository secrets."
        )

    # 2. Shopping list
    print(f"\n📋  Reading shopping list from {SHOPPING_LIST_FILE}...")
    raw_items = get_shopping_list()
    if not raw_items:
        print("No incomplete reminders found. Nothing to do.")
        return
    items = [parse_item(r) for r in raw_items]
    print(f"   Found {len(items)} items: {', '.join(i['raw'] for i in items)}")

    log = new_log()

    # 3. Browser
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-GB",
            timezone_id="Europe/London",
            java_script_enabled=True,
            extra_http_headers={"Accept-Language": "en-GB,en;q=0.9"},
        )
        # Hide webdriver flag that bot detectors look for
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en'] });
        """)

        # Load saved session if available
        loaded = load_cookies(context)
        page = context.new_page()

        if loaded:
            page.goto(OCADO_URL, wait_until="networkidle")
            if not is_logged_in(page):
                login(page, email, password)
                save_cookies(context)
        else:
            login(page, email, password)
            save_cookies(context)

        # 4. Process each item
        for item in items:
            try:
                process_item(page, item, log)
            except Exception as e:
                log["errors"].append({"raw": item["raw"], "error": str(e)})
                print(f"   ❌  Error: {e}")
            human_delay(1.0, 2.5)

        browser.close()

    # 5. Summary
    log_file = save_log(log)
    print_summary(log)
    print(f"\n📄  Full log saved to: {log_file}\n")


if __name__ == "__main__":
    main()
