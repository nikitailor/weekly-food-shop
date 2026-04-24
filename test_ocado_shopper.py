"""
Unit tests for the pure utility functions in ocado_shopper.py.
Browser-dependent functions (login, search, process_item) are not tested here.
"""
import sys
from types import ModuleType
from unittest.mock import MagicMock

# Stub missing optional dependencies so we can import the module
for mod in ("keyring", "playwright", "playwright.sync_api"):
    sys.modules.setdefault(mod, MagicMock())

import ocado_shopper as oc


# ── parse_item ────────────────────────────────────────────────────────────────

class TestParseItem:
    def test_plain_name(self):
        r = oc.parse_item("oat milk")
        assert r["name"] == "oat milk"
        assert r["count"] == 1
        assert r["weight_g"] is None
        assert r["weight_specified"] is False

    def test_count_prefix_2x(self):
        r = oc.parse_item("2x oat milk")
        assert r["name"] == "oat milk"
        assert r["count"] == 2
        assert r["weight_g"] is None

    def test_count_prefix_x2(self):
        r = oc.parse_item("x2 oat milk")
        assert r["name"] == "oat milk"
        assert r["count"] == 2

    def test_weight_grams(self):
        r = oc.parse_item("500g chicken breast")
        assert r["name"] == "chicken breast"
        assert r["weight_g"] == 500.0
        assert r["weight_unit"] == "g"
        assert r["weight_specified"] is True

    def test_weight_kg_converted(self):
        r = oc.parse_item("1kg salmon fillet")
        assert r["name"] == "salmon fillet"
        assert r["weight_g"] == 1000.0
        assert r["weight_unit"] == "kg"

    def test_weight_ml(self):
        r = oc.parse_item("500ml almond milk")
        assert r["name"] == "almond milk"
        assert r["weight_g"] == 500.0
        assert r["weight_unit"] == "ml"

    def test_weight_litres_converted(self):
        r = oc.parse_item("1l orange juice")
        assert r["name"] == "orange juice"
        assert r["weight_g"] == 1000.0
        assert r["weight_unit"] == "l"

    def test_raw_preserved(self):
        raw = "3x greek yoghurt"
        r = oc.parse_item(raw)
        assert r["raw"] == raw

    def test_count_spaces_around_x(self):
        r = oc.parse_item("3x berries")
        assert r["count"] == 3
        assert r["name"] == "berries"


# ── get_weight_grams ──────────────────────────────────────────────────────────

class TestGetWeightGrams:
    def test_grams(self):
        assert oc.get_weight_grams("500g") == 500.0

    def test_kg(self):
        assert oc.get_weight_grams("1.5kg") == 1500.0

    def test_ml(self):
        assert oc.get_weight_grams("750ml") == 750.0

    def test_litres(self):
        assert oc.get_weight_grams("2l") == 2000.0

    def test_embedded_in_string(self):
        assert oc.get_weight_grams("Chicken Breast 300g") == 300.0

    def test_no_match(self):
        assert oc.get_weight_grams("Organic Tomatoes") is None

    def test_case_insensitive(self):
        assert oc.get_weight_grams("500G") == 500.0
        assert oc.get_weight_grams("1KG") == 1000.0


# ── parse_price_text ──────────────────────────────────────────────────────────

class TestParsePriceText:
    def test_strips_whitespace(self):
        assert oc.parse_price_text("  £1.80  ") == "£1.80"

    def test_empty_string(self):
        assert oc.parse_price_text("") == "—"

    def test_none(self):
        assert oc.parse_price_text(None) == "—"

    def test_plain_price(self):
        assert oc.parse_price_text("£4.50") == "£4.50"
