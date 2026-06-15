# FitFindr

A thrift-shopping agent that searches secondhand listings, suggests outfits using your wardrobe, and generates a shareable caption — all from one natural-language query.

**Demo Video:** https://drive.google.com/file/d/1ID-Nu_qIHf4w7akdf6GJ07tJOve5ZXmK/view?usp=sharing

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root with your Groq API key (free at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Open the URL shown in your terminal (usually `http://localhost:7860`).

Run tests:

```bash
pytest tests/
```

---

## Tool Inventory

### Tool 1: `search_listings(description, size, max_price)`

**Purpose:** Finds secondhand listings that match a keyword description, with optional size and price filters. No LLM involved — pure data filtering and scoring.

| Parameter       | Type             | Meaning                                                                                                                                               |
| --------------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `description` | `str`          | Natural-language keywords (e.g.`"vintage graphic tee"`). Scored against each listing's title, description text, and style_tags.                     |
| `size`        | `str \| None`   | Size to filter by (e.g.`"M"`, `"W30"`). Case-insensitive substring match — `"m"` matches `"S/M"`, `"M/L"`, `"M"`. Pass `None` to skip. |
| `max_price`   | `float \| None` | Maximum price in dollars, inclusive. Pass `None` to skip.                                                                                           |

**Returns:** A list of listing dicts sorted by relevance score (highest first). Each dict contains: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), `platform`. Returns `[]` on no match — never raises.

---

### Tool 2: `suggest_outfit(new_item, wardrobe)`

**Purpose:** Uses an LLM (Groq `llama-3.3-70b-versatile`) to suggest 1–2 complete outfit combinations that pair the new thrifted item with pieces from the user's wardrobe.

| Parameter    | Type     | Meaning                                                                                                                                                                          |
| ------------ | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `new_item` | `dict` | A listing dict — the item the user is considering buying. Passed from `search_listings` output.                                                                               |
| `wardrobe` | `dict` | A wardrobe dict with an `items` key. Each wardrobe item has: `id`, `name`, `category`, `colors` (list), `style_tags` (list), `notes` (optional str). May be empty. |

**Returns:** A non-empty string. If the wardrobe has items, the suggestions reference specific named wardrobe pieces. If the wardrobe is empty, it returns general styling advice instead. Returns an error string (not an exception) if the LLM call fails.

---

### Tool 3: `create_fit_card(outfit, new_item)`

**Purpose:** Generates a casual, shareable 2–4 sentence OOTD caption using an LLM at higher temperature (`1.1`) for variety.

| Parameter    | Type     | Meaning                                                                                 |
| ------------ | -------- | --------------------------------------------------------------------------------------- |
| `outfit`   | `str`  | The outfit suggestion string from `suggest_outfit`. Guarded against empty/whitespace. |
| `new_item` | `dict` | The listing dict — used for title, price, and platform in the caption.                 |

**Returns:** A 2–4 sentence first-person caption that mentions the item name, price, and platform once each. Returns a fixed error string `"Could not generate a fit card — no outfit suggestion was provided."` if `outfit` is empty or whitespace-only — without calling the LLM.

---

## Planning Loop

The loop in `run_agent()` is a **sequential, state-gated pipeline** — it does not call all three tools unconditionally. Each step gates the next.

```
User query (natural language)
        |
        v
[1] _parse_query()
    regex extracts: description, size, max_price
    stored in session["parsed"]
        |
        v
[2] search_listings(description, size, max_price)
        |
        +-- results == [] --> set session["error"] --> RETURN EARLY
        |                     (suggest_outfit and create_fit_card never called)
        |
        +-- results found
              |
              v
          session["selected_item"] = results[0]
              |
              v
[3] suggest_outfit(selected_item, wardrobe)
        |
        +-- empty wardrobe --> general styling advice (still returns string)
        |
        +-- wardrobe has items --> specific outfit combos naming wardrobe pieces
              |
              v
          session["outfit_suggestion"] = <LLM string>
              |
              v
[4] create_fit_card(outfit_suggestion, selected_item)
              |
              v
          session["fit_card"] = <LLM caption>
              |
              v
        Return session to caller
```

**Key decision point:** After `search_listings` runs, the loop checks `if not results`. If true, it builds a specific error message that includes the query, size, and price that failed, and returns immediately. Steps 3 and 4 are skipped entirely — `suggest_outfit` is never called with empty input.

---

## State Management

All state lives in a single `session` dict, initialized fresh for each call to `run_agent()`. Every tool reads its inputs from the session and writes its output back to a named key.

| Key                              | Written by                       | Read by                                 |
| -------------------------------- | -------------------------------- | --------------------------------------- |
| `session["parsed"]`            | `_parse_query()`               | `search_listings` call                |
| `session["search_results"]`    | `search_listings`              | gate check, item selection              |
| `session["selected_item"]`     | loop (index 0 of results)        | `suggest_outfit`, `create_fit_card` |
| `session["wardrobe"]`          | `_new_session()` (from caller) | `suggest_outfit`                      |
| `session["outfit_suggestion"]` | `suggest_outfit`               | `create_fit_card`                     |
| `session["fit_card"]`          | `create_fit_card`              | returned to UI                          |
| `session["error"]`             | loop (on early exit)             | UI handler                              |

No global variables. The item found by `search_listings` flows directly into `suggest_outfit` as the same dict object — there is no re-entry, no re-prompting the user, and no hardcoded values between steps.

---

## Error Handling

| Tool                | Failure mode                           | What the agent does                                                                                                                                                                                                                                                           |
| ------------------- | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `search_listings` | No listings match the query            | Sets `session["error"]` to: `"No listings found for 'designer ballgown' in size XXS under $5.00 - try broadening your description, relaxing the size, or raising your budget."` Returns session immediately. `suggest_outfit` and `create_fit_card` are never called. |
| `suggest_outfit`  | `wardrobe["items"]` is empty         | Calls the LLM with a different prompt asking for general styling advice ("what types of bottoms and shoes pair well with this piece"). Returns a non-empty string — does not crash or return `""`.                                                                         |
| `create_fit_card` | `outfit` is empty or whitespace-only | Returns `"Could not generate a fit card — no outfit suggestion was provided."` immediately, without calling the LLM.                                                                                                                                                       |

**Concrete examples from testing:**

```
# Failure 1 — search returns empty list
>>> search_listings("designer ballgown", size="XXS", max_price=5)
[]

# Full agent on same query
>>> session["error"]
"No listings found for 'designer ballgown' in size XXS under $5.00 - try broadening your description, relaxing the size, or raising your budget."
>>> session["fit_card"]
None

# Failure 2 — empty wardrobe
>>> suggest_outfit(results[0], get_empty_wardrobe())
"This Y2K baby tee is begging to be paired with some high-waisted mom jeans or a
 flowy skirt for a cute, cottagecore look. You can also dress it down with distressed
 denim shorts and sneakers, or layer it under a cardigan for a preppy twist."

# Failure 3 — empty outfit string
>>> create_fit_card("", results[0])
"Could not generate a fit card — no outfit suggestion was provided."
```

---

## AI Tool Usage

### Instance 1: Implementing `search_listings`

**What I gave Claude:** The Tool 1 spec block from `planning.md` (inputs, return value, failure mode) plus the `load_listings()` docstring from `utils/data_loader.py`. I asked it to implement keyword scoring using word-overlap across title, description text, and style_tags.

**What it produced:** A working implementation using `str.split()` for tokenization.

**What I changed:** I replaced `str.split()` with `re.findall(r"[a-z0-9]+", text.lower())` to correctly handle hyphenated tags like `"graphic tee"` and punctuation in titles (em-dashes). This matters because `"graphic tee"` as a style tag split on the space would produce two tokens, and the query `"graphic tee"` would score an extra match — the regex approach treats each word uniformly regardless of the surrounding punctuation.

### Instance 2: Implementing the planning loop in `agent.py`

**What I gave Claude:** The `## Architecture` ASCII diagram and the `## Planning Loop` + `## State Management` sections from `planning.md`, plus the `_new_session()` stub already in the file. I asked it to implement `run_agent()` following the gated pipeline exactly.

**What it produced:** A correct sequential loop that gated on the search result.

**What I changed:** The generated `_parse_query()` used a simple `price_match.group(0)` which captured the whole match including "under" — I fixed it to `group(1)` to capture only the numeric part. I also added the size regex to handle waist sizes (`W30 L30`) in addition to standard labels (`XS`, `S/M`, `M/L`, `XL`) since the listings data uses both formats.

---

## Spec Reflection

**What matched:** The gated pipeline design worked exactly as planned. The decision to keep `search_listings` as pure Python (no LLM) made it fast, deterministic, and easy to test in isolation — this was the right call and the tests confirmed it immediately.

**What I had to adjust:** The query parser turned out to be trickier than the spec implied. The planning.md said "regex/heuristic pass" without specifying which regex patterns, and the first attempt missed size formats present in the actual data. Testing against real listings revealed the gap.

**What I'd do differently:** The spec should have listed the exact size formats present in `listings.json` (e.g. `"S/M"`, `"XL (oversized)"`, `"One Size"`) so the parser regex could be designed to match them precisely from the start rather than discovered during testing.

---

## Project Structure

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tests/
│   └── test_tools.py          # 15 pytest tests covering all tools and failure modes
├── tools.py                   # search_listings, suggest_outfit, create_fit_card
├── agent.py                   # run_agent() planning loop + _parse_query()
├── app.py                     # Gradio UI (handle_query wired to run_agent)
├── planning.md                # Spec written before implementation
└── requirements.txt
```
