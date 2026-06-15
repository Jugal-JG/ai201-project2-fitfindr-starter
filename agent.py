"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural-language query
    using regex heuristics — no LLM needed for this step.

    Returns a dict with keys: description (str), size (str|None), max_price (float|None).
    """
    # Extract max_price: match "$30", "under $30", "under 30", "30 dollars", etc.
    price_match = re.search(
        r"(?:under\s+)?\$?(\d+(?:\.\d+)?)\s*(?:dollars?|bucks?)?", query, re.I
    )
    max_price = float(price_match.group(1)) if price_match else None

    # Extract size: look for "size XS/S/M/L/XL/XXL" or "in a M" or standalone
    # Also handles waist sizes like "W28", "W30 L30"
    size_match = re.search(
        r"\b(?:size\s+)?([Ww]\d{2}(?:\s+[Ll]\d{2})?|XXS|XS|S/M|M/L|XL|XXL|XS|S\b|M\b|L\b)",
        query,
    )
    size = size_match.group(1).strip() if size_match else None

    # Description: strip price and size tokens, collapse whitespace
    description = query
    if price_match:
        description = description[:price_match.start()] + description[price_match.end():]
    if size_match:
        description = description[:size_match.start()] + description[size_match.end():]
    # Remove filler words left behind
    description = re.sub(r"\b(?:under|in|size|a|an|the|for|and|or)\b", " ", description, flags=re.I)
    description = re.sub(r"\s+", " ", description).strip(" ,.-")

    return {"description": description, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Returns:
        Session dict. Check session["error"] first — if not None, the
        interaction ended early and outfit_suggestion / fit_card will be None.
    """
    # Step 1: initialize session
    session = _new_session(query, wardrobe)

    # Step 2: parse query → description, size, max_price
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Step 3: search — GATE: stop here if nothing found
    results = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    session["search_results"] = results

    if not results:
        parts = [f"No listings found for '{parsed['description']}'"]
        if parsed["size"]:
            parts.append(f"in size {parsed['size']}")
        if parsed["max_price"] is not None:
            parts.append(f"under ${parsed['max_price']:.2f}")
        parts.append("- try broadening your description, relaxing the size, or raising your budget.")
        session["error"] = " ".join(parts)
        return session  # early exit — do NOT call suggest_outfit or create_fit_card

    # Step 4: select top result
    session["selected_item"] = results[0]

    # Step 5: suggest outfit — state flows from selected_item + wardrobe
    session["outfit_suggestion"] = suggest_outfit(
        new_item=session["selected_item"],
        wardrobe=session["wardrobe"],
    )

    # Step 6: create fit card — state flows from outfit_suggestion + selected_item
    session["fit_card"] = create_fit_card(
        outfit=session["outfit_suggestion"],
        new_item=session["selected_item"],
    )

    # Step 7: return completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Parsed:  {session['parsed']}")
        print(f"Found:   {session['selected_item']['title']} — ${session['selected_item']['price']}")
        print(f"\nOutfit:  {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")
        # State verification: confirm the same dict flowed through
        assert session["selected_item"] is session["search_results"][0], \
            "FAIL: selected_item is not search_results[0]"
        print("\n[State check] selected_item === search_results[0] PASS")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
    assert session2["fit_card"] is None, "FAIL: fit_card should be None on error path"
    assert session2["outfit_suggestion"] is None, "FAIL: outfit_suggestion should be None on error path"
    print("[State check] fit_card is None PASS")
    print("[State check] outfit_suggestion is None PASS")
