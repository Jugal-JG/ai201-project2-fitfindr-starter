"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive substring (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
    """
    listings = load_listings()

    # Step 1: filter by price and size
    candidates = []
    for item in listings:
        if max_price is not None and item["price"] > max_price:
            continue
        if size is not None:
            if size.lower() not in item["size"].lower():
                continue
        candidates.append(item)

    # Step 2: score by keyword overlap with description
    # Tokenize description into lowercase words, stripping punctuation
    query_words = set(re.findall(r"[a-z0-9]+", description.lower()))

    scored = []
    for item in candidates:
        # Build a bag of words from title, description text, and style_tags
        text = " ".join([
            item["title"],
            item["description"],
            " ".join(item["style_tags"]),
        ])
        item_words = set(re.findall(r"[a-z0-9]+", text.lower()))
        score = len(query_words & item_words)
        if score > 0:
            scored.append((score, item))

    # Step 3: sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offers general styling advice for the item.
    """
    try:
        client = _get_groq_client()
    except ValueError as e:
        return f"[suggest_outfit error] {e}"

    item_summary = (
        f"Title: {new_item.get('title', 'Unknown item')}\n"
        f"Category: {new_item.get('category', '')}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
        f"Colors: {', '.join(new_item.get('colors', []))}\n"
        f"Condition: {new_item.get('condition', '')}\n"
        f"Price: ${new_item.get('price', '')}"
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        prompt = (
            "You are a thrift-savvy fashion stylist. A user just found this item:\n\n"
            f"{item_summary}\n\n"
            "They have no wardrobe on file yet. Give them general styling advice: "
            "what types of bottoms, shoes, and layers pair well with this piece, "
            "and what overall vibe or aesthetic it suits. Be specific and conversational, "
            "2–3 sentences max."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {w['name']} ({w['category']}): {', '.join(w.get('style_tags', []))}"
            + (f" — {w['notes']}" if w.get("notes") else "")
            for w in wardrobe_items
        )
        prompt = (
            "You are a thrift-savvy fashion stylist. A user just found this item:\n\n"
            f"{item_summary}\n\n"
            "Their current wardrobe includes:\n"
            f"{wardrobe_lines}\n\n"
            "Suggest 1–2 complete outfit combinations that incorporate the new item "
            "with specific named pieces from their wardrobe above. Be concrete — name "
            "the exact pieces. Keep it conversational and under 5 sentences total."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[suggest_outfit error] Could not generate outfit suggestion: {e}"


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, returns an error message string.
    """
    if not outfit or not outfit.strip():
        return "Could not generate a fit card — no outfit suggestion was provided."

    title = new_item.get("title", "this piece")
    price = new_item.get("price", "?")
    platform = new_item.get("platform", "a thrift app")

    prompt = (
        "You are writing an authentic, casual OOTD caption for Instagram or TikTok — "
        "the kind a real person posts, not a brand. "
        "Write 2–4 sentences based on the outfit below.\n\n"
        f"The thrifted item: {title} — found on {platform} for ${price}\n"
        f"The outfit: {outfit}\n\n"
        "Rules:\n"
        "- First-person voice, casual and genuine (not a product description)\n"
        "- Mention the item name, price, and platform exactly once each, naturally\n"
        "- Capture the specific vibe of the outfit\n"
        "- No hashtags, no em-dashes, no bullet points — just flowing sentences\n"
        "- Sound different each time; don't start with 'just' or 'found'\n"
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.1,  # higher temp for caption variety
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[create_fit_card error] Could not generate fit card: {e}"
