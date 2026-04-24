# Ocado Shopper 🛒

Reads your **Apple Reminders "Food Shopping" list** and adds everything to your Ocado basket automatically. Prefers your favourited products; falls back to top-rated with a review log.

---

## Setup (one time)

### 1. Install dependencies

```bash
pip install playwright keyring
playwright install chromium
```

### 2. Store your Ocado password in macOS Keychain

```bash
python -c "import keyring; keyring.set_password('ocado', 'your@email.com', 'yourpassword')"
```

You only need to do this once. Your password is stored encrypted in Keychain — never in the script.

---

## How to use

```bash
python ocado_shopper.py
```

It will ask for your email, retrieve the password from Keychain, then open a browser and start working through your list.

---

## Reminders format

The script parses quantities from your reminder names:

| Format | Meaning |
|---|---|
| `2x oat milk` or `x2 oat milk` | Add 2 of this item |
| `500g chicken breast` | Find closest pack to 500g |
| `1kg salmon fillet` | Find closest pack to 1kg |
| `berries` | Add 1, pick largest if weight-based |

**Tips for better matching:**
- Be specific: `alpro soya yoghurt` beats `yoghurt`
- Favourite items on Ocado directly — the script will always prefer these
- Over time your favourites do the heavy lifting

---

## What it does

1. Reads all **incomplete** reminders from "Food Shopping"
2. Logs in to Ocado (reuses saved session if available)
3. For each item:
   - Searches Ocado
   - ★ If a **favourited** result is found → adds it
   - ⚠️ If not → adds top/best match, logs alternatives for your review
4. Prints a summary and saves a log to `~/ocado_logs/`

You then **review the basket** and place the order yourself.

---

## Review log

After running, you'll see a summary like:

```
✅  Added to basket (8 items):
    • oat milk × 2 ★ favourite
      Oatly Oat Drink Barista 1L | £1.80 | 1L | £1.80/L

⚠️   Needs your review (2 items):

    500g chicken breast — matched to 500g (no favourite)
    Added: Waitrose British Chicken Breast 520g | £4.50 | £8.65/kg
    Alternatives:
      1. Ocado British Chicken Breast 300g | £2.80 | £9.33/kg
      2. Waitrose British Chicken Breast 1kg | £8.00 | £8.00/kg

    chicken thighs — no weight specified — picked largest available
    Added: Waitrose British Chicken Thighs 1kg | £5.50 | £5.50/kg
    Alternatives:
      1. Waitrose British Chicken Thighs 500g | £3.20 | £6.40/kg
```

Full logs are saved as JSON in `~/ocado_logs/` for reference.

---

## Files

| File | Purpose |
|---|---|
| `ocado_shopper.py` | Main script |
| `~/.ocado_session.json` | Saved browser session (auto-created, permissions 600) |
| `~/ocado_logs/` | Per-run review logs |

---

## Settings

At the top of `ocado_shopper.py`:

```python
HEADLESS = False   # Set True to run without a visible browser window
```

Start with `False` so you can see what's happening. Switch to `True` once you're confident.

---

## Troubleshooting

**"No password found in Keychain"** — Re-run the keychain setup command in step 2.

**Items not matching well** — Favourite the correct product on Ocado directly. Next run will pick it up.

**Script breaks after Ocado update** — The selectors in `extract_product_info()` and `add_to_basket()` may need updating. Open an issue or tweak the CSS selectors to match the new layout.

**Session expired** — Delete `~/.ocado_session.json` and re-run. It will log in fresh.
