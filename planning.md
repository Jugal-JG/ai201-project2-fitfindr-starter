# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for items that match a keyword description, an optional size filter, and an optional price ceiling. Returns a ranked list of matching listings sorted by relevance score (keyword overlap).

**Input parameters:**
- `description` (str): Natural-language keywords describing the desired item (e.g., "vintage graphic tee"). Used to score listings by overlap with title, description, and style_tags.
- `size` (str | None): Size string to filter by (e.g., "M", "W30"). Case-insensitive substring match. Pass `None` to skip size filtering.
- `max_price` (float | None): Maximum price in dollars, inclusive. Pass `None` to skip price filtering.

**What it returns:**
A list of listing dicts sorted by relevance (highest score first). Each dict contains: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), `platform`. Returns an empty list — never raises — when nothing matches.

**What happens if it fails or returns nothing:**
The agent sets `session["error"]` to a friendly message explaining no listings matched and suggesting the user broaden their search (e.g., relax the size or raise the price limit). The agent returns early without calling `suggest_outfit` or `create_fit_card`.

---

### Tool 2: suggest_outfit

**What it does:**
Given a thrifted item the user is considering and their current wardrobe, uses an LLM (Groq) to suggest 1–2 specific, complete outfit combinations that incorporate the new item and named pieces from the wardrobe.

**Input parameters:**
- `new_item` (dict): A listing dict representing the item the user found (output of `search_listings`, top result).
- `wardrobe` (dict): A wardrobe dict with an `items` key holding a list of wardrobe item dicts (each has `id`, `name`, `category`, `colors`, `style_tags`, optional `notes`). May be an empty list.

**What it returns:**
A non-empty string with outfit suggestions. If the wardrobe is populated, suggestions reference specific named wardrobe pieces. If the wardrobe is empty, the LLM offers general styling advice (what categories and vibes pair well with the item).

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, the tool still succeeds — it falls back to general styling guidance rather than crashing. If the LLM call itself fails, the tool returns a short error string describing the issue instead of raising an exception.

---

### Tool 3: create_fit_card

**What it does:**
Takes the outfit suggestion text and the thrifted item's listing dict, then uses an LLM at higher temperature to generate a 2–4 sentence casual, shareable caption — the kind a real person would post as an OOTD on Instagram or TikTok.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`.
- `new_item` (dict): The listing dict for the thrifted item (used for title, price, and platform).

**What it returns:**
A 2–4 sentence caption string that feels authentic and casual, mentions the item name, price, and platform naturally once each, and captures the outfit vibe in specific terms. Returns a descriptive error string (not an exception) if `outfit` is empty or whitespace-only.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, the tool returns `"Could not generate a fit card — no outfit suggestion was provided."` without calling the LLM. If the LLM call fails, it returns an error string with the reason.

---

### Additional Tools (if any)

None for the required milestone. (Stretch: `compare_price` tool to estimate value fairness.)

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop in `run_agent()` is a sequential, state-gated pipeline:

1. **Parse** the raw query string with a regex/heuristic pass to extract `description`, `size`, and `max_price`. Store in `session["parsed"]`.
2. **Search** — call `search_listings(description, size, max_price)`. Store results in `session["search_results"]`.
   - **Gate:** if results list is empty → set `session["error"]`, return early. Do NOT continue.
3. **Select** the top result (index 0) and store in `session["selected_item"]`.
4. **Suggest** — call `suggest_outfit(selected_item, wardrobe)`. Store in `session["outfit_suggestion"]`.
5. **Fit card** — call `create_fit_card(outfit_suggestion, selected_item)`. Store in `session["fit_card"]`.
6. Return the completed session.

The loop does not call all tools unconditionally — it gates on the search result. If search returns nothing, steps 4–6 are skipped entirely.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict initialized by `_new_session()`. Each step writes its output into a named key:

- `session["parsed"]` — extracted query parameters, read by the search call.
- `session["search_results"]` — full list of matching listings from `search_listings`.
- `session["selected_item"]` — the top listing dict, passed as `new_item` to both `suggest_outfit` and `create_fit_card`.
- `session["wardrobe"]` — the user's wardrobe, passed directly to `suggest_outfit`.
- `session["outfit_suggestion"]` — the string from `suggest_outfit`, passed as `outfit` to `create_fit_card`.
- `session["fit_card"]` — the final caption string.
- `session["error"]` — set on early termination; `None` on success.

No global variables. Every tool call reads from and writes to this single dict, so state is always traceable.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Sets `session["error"]` = "No listings found for '[description]' in size [size] under $[max_price]. Try broadening your search." Returns session early — does not call downstream tools. |
| suggest_outfit | Wardrobe is empty | Falls back to general LLM styling advice ("here's how you'd typically style this item") rather than crashing or returning an empty string. |
| create_fit_card | Outfit input is empty or whitespace-only | Returns a fixed error string without calling the LLM: "Could not generate a fit card — no outfit suggestion was provided." |

---

## Architecture

```
User query (natural language)
        │
        ▼
┌───────────────────┐
│   run_agent()     │  ◄── session dict initialized here
│   Planning Loop   │
└───────┬───────────┘
        │
        ▼
  [Parse query]
  description, size, max_price → session["parsed"]
        │
        ▼
  search_listings(description, size, max_price)
        │
        ├── empty list ──► set session["error"] ──► RETURN EARLY
        │
        └── results found
              │  session["search_results"], session["selected_item"]
              ▼
  suggest_outfit(selected_item, wardrobe)
        │
        ├── empty wardrobe ──► general styling advice (still returns string)
        │
        └── wardrobe has items ──► specific outfit combos
              │  session["outfit_suggestion"]
              ▼
  create_fit_card(outfit_suggestion, selected_item)
        │
        └── session["fit_card"]
              │
              ▼
        Return session to caller (app.py / Gradio UI)
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **Tool 1 (`search_listings`):** Give Claude the Tool 1 spec from this file plus the `load_listings()` docstring. Ask it to implement keyword scoring using title + description + style_tags overlap (case-insensitive split on whitespace/punctuation), then filter by size (substring, case-insensitive) and max_price. Verify by testing 3 queries: one that returns results, one that returns nothing due to price, one that returns nothing due to size.
- **Tool 2 (`suggest_outfit`):** Give Claude the Tool 2 spec and the wardrobe schema from `wardrobe_schema.json`. Ask it to build a Groq prompt that names the new item's title/category/style_tags and lists wardrobe items by name and style_tags, requesting 1–2 specific outfit combinations. Verify with both `get_example_wardrobe()` (should name specific pieces) and `get_empty_wardrobe()` (should give general advice).
- **Tool 3 (`create_fit_card`):** Give Claude the Tool 3 spec. Ask it to build a higher-temperature Groq prompt that produces casual, first-person OOTD captions. Verify by calling it with 2 different items and checking the captions feel distinct and authentic.

**Milestone 4 — Planning loop and state management:**

- Give Claude the Architecture diagram and State Management section above plus the `_new_session()` stub. Ask it to implement `run_agent()` following the gated pipeline exactly. Verify with the two CLI test cases already in `agent.py __main__`: the happy path (graphic tee) should reach `fit_card`, the impossible query (ballgown under $5) should return only an `error`.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent parses the query and extracts: `description="vintage graphic tee"`, `size=None` (none specified), `max_price=30.0`. It calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. The function loads all listings, filters to those priced ≤ $30, scores each by keyword overlap with the description (matching against title, description text, and style_tags), and returns a ranked list. Result: two matches — `lst_006` "Graphic Tee — 2003 Tour Bootleg Style" ($24, score 4) and `lst_002` "Y2K Baby Tee — Butterfly Print" ($18, score 1). Top result: `lst_006`.

**Step 2:**
The agent stores `lst_006` as `session["selected_item"]` and calls `suggest_outfit(new_item=lst_006, wardrobe=get_example_wardrobe())`. The wardrobe has 10 items, so the LLM is prompted with the new item's details (black graphic tee, grunge/streetwear tags) and the wardrobe list. The LLM returns: "Pair this faded bootleg tee with your baggy dark-wash jeans and chunky white sneakers for a 90s streetwear look — tuck the front corner slightly for shape. For a grungier take, swap the sneakers for your black combat boots and throw your vintage denim jacket on top."

**Step 3:**
The agent stores the suggestion in `session["outfit_suggestion"]` and calls `create_fit_card(outfit=<suggestion>, new_item=lst_006)`. The LLM generates a casual caption at higher temperature. Result: "found this faded bootleg tee on depop for $24 and it was literally made for my baggy jeans era 🖤 combat boots + denim jacket and it's a full look, no notes"

**Final output to user:**
The Gradio UI displays:
- **Found:** "Graphic Tee — 2003 Tour Bootleg Style — $24, depop (good condition)"
- **Outfit suggestion:** the two-option paragraph from Step 2
- **Fit card:** the caption from Step 3

If Step 1 had returned no results (e.g., query was "designer ballgown under $5"), the UI would display only the error message — "No listings found for 'designer ballgown' under $5.00. Try raising your budget or broadening the description." — and Steps 2–3 would not run.
