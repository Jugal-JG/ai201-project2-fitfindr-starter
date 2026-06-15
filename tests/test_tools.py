"""
tests/test_tools.py

Isolation tests for each FitFindr tool. Run with: pytest tests/
Each failure mode has at least one dedicated test.
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0

def test_search_empty_results():
    # Impossible query — should return [], not raise
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []

def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=30)
    assert all(item["price"] <= 30 for item in results)

def test_search_size_filter_case_insensitive():
    # "m" should match items with size "M", "S/M", "M/L", etc.
    results = search_listings("top", size="m", max_price=None)
    assert all("m" in item["size"].lower() for item in results)

def test_search_relevance_ordering():
    # The more specific match should rank above a weaker one
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert len(results) >= 2
    # lst_006 has both "graphic tee" and "vintage" in style_tags; should be near top
    titles = [r["title"] for r in results[:3]]
    assert any("graphic" in t.lower() or "tee" in t.lower() or "band" in t.lower()
               for t in titles)

def test_search_returns_no_exception_on_no_price_or_size():
    # Should work fine with all filters off
    results = search_listings("cardigan", size=None, max_price=None)
    assert isinstance(results, list)

def test_search_result_fields():
    results = search_listings("jeans", size=None, max_price=None)
    assert len(results) > 0
    item = results[0]
    for field in ("id", "title", "description", "category", "style_tags",
                  "size", "condition", "price", "colors", "platform"):
        assert field in item, f"Missing field: {field}"


# ── suggest_outfit ────────────────────────────────────────────────────────────

SAMPLE_ITEM = {
    "id": "lst_006",
    "title": "Graphic Tee — 2003 Tour Bootleg Style",
    "category": "tops",
    "style_tags": ["graphic tee", "vintage", "grunge", "streetwear", "band tee"],
    "colors": ["black"],
    "condition": "good",
    "price": 24.0,
    "platform": "depop",
    "description": "Vintage-style bootleg tee with faded graphic.",
    "size": "L",
    "brand": None,
}

EXAMPLE_WARDROBE = {
    "items": [
        {
            "id": "w_001",
            "name": "Baggy straight-leg jeans, dark wash",
            "category": "bottoms",
            "colors": ["dark blue"],
            "style_tags": ["denim", "streetwear", "baggy"],
            "notes": "High-waisted",
        },
        {
            "id": "w_007",
            "name": "Chunky white sneakers",
            "category": "shoes",
            "colors": ["white"],
            "style_tags": ["sneakers", "chunky", "streetwear"],
            "notes": None,
        },
    ]
}

EMPTY_WARDROBE = {"items": []}

def test_suggest_outfit_with_wardrobe_returns_string():
    result = suggest_outfit(SAMPLE_ITEM, EXAMPLE_WARDROBE)
    assert isinstance(result, str)
    assert len(result) > 0

def test_suggest_outfit_empty_wardrobe_does_not_crash():
    # Empty wardrobe must return a non-empty string (general advice), not raise
    result = suggest_outfit(SAMPLE_ITEM, EMPTY_WARDROBE)
    assert isinstance(result, str)
    assert len(result) > 0

def test_suggest_outfit_empty_wardrobe_no_exception():
    # Confirm no exception is raised (same as above but explicit)
    try:
        result = suggest_outfit(SAMPLE_ITEM, EMPTY_WARDROBE)
    except Exception as e:
        pytest.fail(f"suggest_outfit raised an exception with empty wardrobe: {e}")


# ── create_fit_card ───────────────────────────────────────────────────────────

SAMPLE_OUTFIT = (
    "Pair this faded bootleg tee with your baggy dark-wash jeans and chunky "
    "white sneakers for a 90s streetwear look."
)

def test_create_fit_card_returns_string():
    result = create_fit_card(SAMPLE_OUTFIT, SAMPLE_ITEM)
    assert isinstance(result, str)
    assert len(result) > 0

def test_create_fit_card_empty_outfit_returns_error_string():
    # Empty outfit must return an error string, not raise
    result = create_fit_card("", SAMPLE_ITEM)
    assert isinstance(result, str)
    assert "no outfit suggestion" in result.lower() or "could not" in result.lower()

def test_create_fit_card_whitespace_outfit_returns_error_string():
    result = create_fit_card("   ", SAMPLE_ITEM)
    assert isinstance(result, str)
    assert len(result) > 0
    assert "no outfit suggestion" in result.lower() or "could not" in result.lower()

def test_create_fit_card_mentions_platform():
    result = create_fit_card(SAMPLE_OUTFIT, SAMPLE_ITEM)
    assert "depop" in result.lower()

def test_create_fit_card_variety():
    # Two calls with the same inputs should not always produce identical output
    # (high temperature means they CAN be identical occasionally — run 3 times)
    results = {create_fit_card(SAMPLE_OUTFIT, SAMPLE_ITEM) for _ in range(3)}
    # At least 2 distinct outputs across 3 calls at temp=1.1
    assert len(results) >= 2, "create_fit_card output appears identical across calls — check temperature"
