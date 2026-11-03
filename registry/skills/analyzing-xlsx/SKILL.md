---
name: analyzing-xlsx
description: Answer document-QA questions over .xlsx workbooks — lookup, aggregate, table, and plot generation across single sheet, multiple sheets, and multiple files. Also handles a .csv only when it accompanies a workbook in the same question (e.g. joining a .csv export to an .xlsx). For a standalone .csv with no workbook, use analyzing-csv instead.
---

# Analyzing XLSX for Document QA

A workflow for answering questions over `.xlsx` workbooks. Drive `openpyxl`
(plus `pandas` + `matplotlib` for charts) from Python; never dump full sheets
into the model context — filter and aggregate in code, then report the value.

Question shapes to expect:

- **lookup** — find one value at the intersection of a row label and a column
  header (e.g. "Productivity and Business Processes Q4 FY21 operating income").
- **aggregate** — sum / count / group-by across rows, sometimes across sheets
  or files (e.g. "total spent at Swantown", "difference in Australia deals
  between 2007 and 2009").
- **list / dict** — return a structured collection, e.g.
  `{"Liberty": 157.85, "HomeCoreAdvantage": 134.7}` for "compare bill rates
  across vendors". Emit valid JSON on the first line of the answer (no
  markdown fences) so it's machine-parseable.
- **plot_generation** — produce a chart image (histogram, ECDF, stacked area,
  etc.).
- **table** — emit a grouped result as CSV (e.g. "total demand by practice and
  market").

When the question hints at an answer format — decimal (`0.4128`) vs percent
(`41.28%`), integer count vs total amount, name-only vs name-with-code — match
that shape. `0.4128` and `42.54%` carry the same information but read very
differently.

## Toolkit

Bundled with this skill is `/app/skills/analyzing-xlsx/scripts/xlsx_toolkit.py`,
a CLI wrapping the common openpyxl operations so you don't have to re-emit
boilerplate heredocs. Run
`python /app/skills/analyzing-xlsx/scripts/xlsx_toolkit.py --help` for the full
surface.

| Command | Purpose |
|---------|---------|
| `inspect <file> [--sheet S] [--rows N]` | sheet names, dims, first N rows |
| `search <file> [--sheet S] --terms T1 T2 ... [--max N] [--all-cells] [--regex]` | rows matching any keyword/regex (case-insensitive). `--all-cells` reports each match as `sheet:row:col` (use for fuzzy item lookups across many sheets) |
| `headers <file> --sheet S [--row N]` | dump a header row, numbered |
| `compound-header <file> --sheet S --rows R1,R2[,R3]` | flatten a multi-row header into one column-numbered list (e.g. `league / apps` vs. `total / apps`) |
| `uniques <file> --sheet S --header-row N --col C [--limit N]` | distribution of values in a column |
| `rows <file> --sheet S --header-row N [--where COL=VAL ...] [--cols C1,C2] [--limit N]` | filtered, projected rows |
| `cell <file> --sheet S (--a1 A1 \| --row R --col C) [--formula]` | one cell — cached value or formula string |
| `agg <file> --sheet S --header-row N --group COL[,COL] --sum COL [--where ...] [--decimal] [--quantize 0.01]` | group-by sum |
| `multi-agg <file> --sheets S1,S2,... --header-row N --sum COL [--where ...] [--decimal] [--quantize 0.01]` | sum a column across **several sheets that share the same schema**, with per-sheet and grand-total breakdown (e.g. yearly 2007/2008/2009 sheets, or per-warehouse inventory) |
| `csv-peek <file> [--rows N] [--encoding ENC]` | preview a CSV companion (auto-falls-back utf-8-sig → utf-8 → latin-1) |

Each invocation targets one workbook and (optionally) one sheet. For
multi-file or multi-sheet questions where the schemas differ, **fan out**:
issue several `xlsx_toolkit.py` calls in a single shell batch so they run in
parallel rather than sequentially. When the schemas match, prefer `multi-agg`
over fan-out: it gives an explicit per-sheet breakdown so you can verify no
sheet was silently dropped.

```bash
# Same agg across three yearly sheets — schema matches, use multi-agg
python /app/skills/analyzing-xlsx/scripts/xlsx_toolkit.py multi-agg deals.xlsx \
  --sheets 2007,2008,2009 --header-row 1 \
  --where Country=Australia --sum Amount --decimal --quantize 0.01

# Two-file aggregation — different schemas, fan out in parallel
python /app/skills/analyzing-xlsx/scripts/xlsx_toolkit.py inspect file_a.xlsx --rows 5 &
python /app/skills/analyzing-xlsx/scripts/xlsx_toolkit.py inspect file_b.xlsx --rows 5 &
wait
```

Prefer the toolkit's subcommands over inline Python whenever they fit.
Drop back to a custom Python script only for cases the toolkit doesn't
cover (plots, multi-key joins, parent/child row hierarchies, custom transforms).
For complex problems (multi-criteria filtering across many sheets,
hierarchical row labels), a single well-structured inline script is usually
faster than 5+ toolkit invocations.

## The four-phase loop

### Phase 1 — Inspect structure (always do this first)

Never start computing before you know the shape of the data. Run the
preprocessor first — it does this inspect step once and caches the result by
file hash, so re-inspecting the same workbook is instant:

```bash
python /app/skills/analyzing-xlsx/scripts/preprocess.py <xlsx_path>
```

It writes a versioned artifact directory with two files:

- **manifest.json** — read first. `source_file`, `extractor_versions`,
  `config`, plus `warnings` / `limits_applied`. If the workbook was too large
  or extraction failed, `metadata.json` may be absent — check here before
  relying on it.
- **metadata.json** — the sheet list (`sheet_names`) and, per sheet, its
  dimensions (`row_count`, `column_count`) and the first ~10 rows
  (`sample_rows`) — the same information `xlsx_toolkit.py inspect` prints.

The preprocessor tells you where to point the toolkit; `xlsx_toolkit.py` is
still how you pull actual values. To inspect inline instead of (or in addition
to) the cached metadata, use `xlsx_toolkit.py inspect` to list sheets, their
dimensions, and the first ~10 rows of each. For inline use the equivalent is:

```python
from openpyxl import load_workbook
wb = load_workbook(path, data_only=True, read_only=True)
```

`data_only=True` returns cached cell values instead of formula strings;
`read_only=True` is dramatically faster on large files. If the workbook
contains formulas with no cached value, reopen with `data_only=False` to
read the formula strings, then compute. Sometimes you need to open the file
**twice**: once with `data_only=True` for cached values, once with
`data_only=False` to inspect formula structure across cells.

For `.csv` companions: `xlsx_toolkit.py csv-peek` auto-falls-back through
common encodings.

**Build a sheet-name map up front when sheet names are cryptic.** Workbooks
often use codes like `C-1, C-2, C-7(A-1), C-11, C-12, C-16, C-18` (construction
schedules) or `CPT, WC011..WC053, DC1..DC5` (municipalities). The question will
name them in plain English ("line schedule", "DP structure", "Cape Town",
"Stellenbosch"). Before answering, scan each sheet's first ~5 rows and second
column — the descriptive title usually lives there — and build a `code → name`
map. Don't guess.

**Also classify each sheet by category when the question hints at one.** For
South African municipal workbooks: `CPT` is **metropolitan** (Cape Town);
`WC0xx` are **local municipalities** (each one belongs to exactly one
district); `DCn` are **district municipalities**. Rules:

- A question that says "**district** municipality" excludes `CPT` and all
  `WC0xx` sheets — only `DCn` qualifies.
- A question that names a district ("**West Coast**", "**Overberg**",
  "**Cape Winelands**", "**Garden Route**", "**Central Karoo**") refers to
  the subset of `WC0xx` sheets that belong to that district. To find the
  membership, open the corresponding `DCn` sheet — it lists its child local
  municipalities — or read the `name` cell of each `WC0xx` and group by the
  district named there. Do **not** guess membership from alphabetical
  ordering of WC codes.
- A question that names a metro ("**Cape Town**") refers to `CPT` only.

For non-municipal workbooks the same pattern applies whenever sheets are
clustered by an implicit hierarchy (yearly sheets, per-region, per-product
family) — classify before you aggregate, so the question's scope filter has
something to match against.

**If `inspect` shows ≥ 2 sheets with a shared key column and one of them
looks like an event / inventory / transaction log, the answer to an
aggregate-by-entity question is almost always a JOIN + SUM on the log
sheet's quantity column — not a `COUNT` of distinct entities.** Recognition
cues: one sheet is `*_attributes` / `*_master` / `*_list` / `products` /
`vendors` (one row per entity); another is `inventory` / `transactions` /
`sales` / `events` / `timesheets` (many rows per entity with a quantity
column). For "how many products delivered by ACME", "total revenue from US
customers", "cumulative hours by Katie": load the entity sheet for the IDs
of interest, then iterate the log sheet and sum the quantity column where
the ID matches. Returning the count of entity rows (e.g. 14 ACME SKUs)
when the question wanted the total quantity delivered (1,240 units) is
the most common silent failure in this category.

### Phase 2 — Locate the relevant rows / columns

**Before any time / period / category-filter question, run `uniques` on the
relevant column and confirm the question's value is in the distribution.**
If the question asks "Q3 2023 hours" but `uniques --col Date` returns only
2024 values, the answer is "Q3 2023 data is not present in the workbook" —
never substitute the nearest period. Same for pollster filters ("Rutgers-
Eagleton" must literally appear in the source column before you accept any
matching row) and scope filters ("Cloud Solutions SMB" must literally
appear in the relevant dimension column). Do this **before** writing the
aggregation code, not after — substituting the nearest available value is
the most common silent failure for these questions.

Search inside Python rather than streaming raw data through the model.

- **Find the sheet** — `xlsx_toolkit.py search FILE --terms ...` returns
  `sheet:row: contents`. Use 2–4 distinctive keywords from the question. Use
  `--all-cells` when you need every occurrence with its column index (handy
  for items that repeat across many sheets). Use `--regex` for fuzzy matches
  like `r"1/8.*drill"` or to anchor on numeric prefixes.
- **Find the header row** — header is usually not row 1. Once `search`
  surfaces a candidate, run `headers --row N` to confirm the row contains
  all expected column names. Off-by-one on the header row is a top mistake —
  verify it.
- **Handle multi-row headers** — when row N contains group labels
  (`league | cup | total`) and row N+1 contains sub-labels
  (`apps | goals | apps | goals | ...`), a single header row is ambiguous.
  Use `compound-header --rows N,N+1` to get a flattened `column_index ->
  "group / sub"` map, then pick the right column. Example: a footballer's
  Partizan total might show `league apps = 133` (col 3) and `total apps = 170`
  (col 9) — a question framed "with 64 league goals" pins col 3.
- **Match by exact value when possible** — `rows --where Country=Australia`
  uses case-insensitive exact match. Fall back to substring search only
  after exact match returns zero rows. If a column appears empty, run
  `uniques` first to see what values actually exist.

### Phase 3 — Handle the gotchas

| Gotcha | Sign | Fix |
|--------|------|-----|
| Header row not row 1 | First-row values are titles or blanks | Run `headers --row N` for each candidate row until column names appear |
| **Multi-row headers** | One header row gives ambiguous column names like multiple `apps` columns | Use `compound-header --rows R1,R2` to flatten group + sub labels before picking columns |
| **Cryptic sheet/code names** | Sheets are `C-1, WC024, DB-001` rather than human names | Build a code→name map from sheet content before lookups; don't guess from the code |
| Coded values | `vendor='ST'` but question says "Swantown" | Run `uniques` on the column; scan other sheets for an abbreviation legend |
| Synonyms in labels | "public relations" not found; dept is "Communications" | `uniques --col Department` and pick the best match |
| **Question term not in data** | "boring bits" but workbook only has "drill bits" | Do **not** silently substitute a synonym. If the literal item is absent, answer 0 / "not found" rather than guessing the closest match |
| Formulas with no cached value | `cell` returns `None` or formula string | Open the file **twice** — once with `data_only=True` for values, once with `data_only=False` to inspect formulas; compute from inputs if needed |
| Merged cells | Some cells return `None` mid-row | Read with `--formula`, or iterate `ws.merged_cells` in custom code; for forward-fill use `compound-header`'s logic |
| Placeholder strings for missing data | Cells contain `".."`, `"-"`, `"N/A"` rather than `None` | Treat these as missing during sums (`if v in (None, '..', '-', 'N/A'): continue`); don't try to coerce to float |
| Mixed-year data | Question asks 2023 but rows are 2024 | State the mismatch in the answer; don't silently answer for the wrong year |
| CSV encoding | `UnicodeDecodeError` on `utf-8` | `csv-peek` handles it; for custom code, retry with `latin-1` or `utf-8-sig` |
| Multi-file aggregation | Two `.xlsx` (or `.xlsx` + `.csv`) inputs | Fan out toolkit calls in parallel; align column names case-insensitively before combining |
| **Missed sheets in multi-sheet aggregation** | Answer is suspiciously low; matches were found in N sheets but you only summed M of them | Use `multi-agg` (or list the sheet→subtotal table explicitly in your scratch work) so a zero-count sheet is visible rather than silently dropped |
| Decimal precision | Floats accumulating in sums | Pass `--decimal --quantize 0.01` to `agg`/`multi-agg`; in custom code use `Decimal(str(v))` and `quantize(..., ROUND_HALF_UP)` |
| **Count vs distinct-count** | Question says "how many deals" — 7 distinct deal numbers vs. 14 rows | Default to **counting all matching rows**. Only deduplicate when the question explicitly says "unique" or "distinct" |
| **Percentage vs decimal format** | Computed `0.4128`; question expected `41.28%`, or vice versa | Match the dataset's existing convention and any format hint in the question. `41.28`, `41.28%`, and `0.4128` are all plausible "percentage" answers — pick one shape and be consistent |
| **Parent/child rows in cost tables (and dept rosters)** | A row like "Horizontal & Cross Bracing" or "IT" is a heading; its sub-rows are the leaves | Don't sum / count heading rows together with their sub-rows. Inspect column-A indentation/numbering (`14`, `(i)`, `(ii)`, `(iii)`, leading whitespace, bold styling) to identify hierarchy. For "how many IT staff" type questions: if the workbook shows `IT` at indent 0 and `Network`, `Apps`, `Support` at indent 1 below it, count only the indented rows — the "IT" row is the heading, not a person. Sum **only** leaves or **only** headings, never both. The off-by-one ("21 vs 22") almost always comes from counting one heading row as if it were a leaf. |

### Phase 4 — Verify, then deliver

**Before reporting any number, you MUST verify the row label, column
header, and value cells — verifying the value alone is useless because it
confirms the cell you chose, not that you chose the right cell.** When the
answer depends on column choice (a specific quarter, audited vs pre-audit
year, per-region totals), verify **three** cells:

1. **Row-label cell** (typically column A or B of that row) — confirms you
   picked the row whose label literally matches the question's phrasing.
2. **Column-header cell** (row 1 or the relevant header row) — confirms the
   column matches the question's column qualifier ("Q4 FY21" vs "Q4 FY20",
   "audited" vs "pre-audit", "2022/23" vs "2023/24").
3. **Value cell** — confirms the number you're about to report.

```bash
# Question: "Productivity and Business Processes Q4 FY21 operating income"
python /app/skills/analyzing-xlsx/scripts/xlsx_toolkit.py cell book.xlsx \
  --sheet "Segment History" --a1 A13         # → "Productivity and Business Processes"
python /app/skills/analyzing-xlsx/scripts/xlsx_toolkit.py cell book.xlsx \
  --sheet "Segment History" --a1 E1          # → "Q4 FY21"   (column header)
python /app/skills/analyzing-xlsx/scripts/xlsx_toolkit.py cell book.xlsx \
  --sheet "Segment History" --a1 E13         # → 6435
```

For pure row-based answers (no column ambiguity), just the row label + value
suffices. But whenever the workbook has multiple comparable columns
(quarters, years, regions, audited/pre-audit), the column-header verify is
mandatory.

If the row label is not a literal match for the question's wording — e.g.
question says "product revenue" but the cell holds "Total revenue", or
question says "Q1 2017" but the column header is "Q1-FY18" — do **not**
report. Re-run `search` with the literal phrase from the question and pick
the row whose label cell contains it. The most common loss is rubber-stamping
the verify on a row whose value happens to look reasonable but whose label
doesn't match the question.

For dict / table answers, run this two-cell verify for **every** entry, not
just the first one — one bad entry sinks the whole answer.

**For any sum, count, or percentage answer, your scratch output MUST list
the source rows you included** (row label + value, one line per row) before
reporting the aggregate. Even for 2-3 rows. If the count of source rows
looks wrong for the question's scope (too many, too few, or a mix of
categories you weren't asked for), your filter is wrong — re-derive before
totalling. For percentages, print the numerator-row-list and the
denominator-row-list as two separate blocks so the choice is visible.

This catches off-by-one header-row errors, total-vs-sub-line confusions,
wrong-period / wrong-segment picks, wrong-workbook picks, and
wrong-subset-summed errors.

For multi-sheet aggregations, **print the per-sheet contributions** (use
`multi-agg`, which does this automatically) and confirm the grand total
equals the sum of the listed parts. If a sheet you expected to contribute
shows zero, that's a signal to re-check — the question likely intends it
to be included.

Deliverable shape by question type:

- **Single-value answers** → the value itself (`6435`, `5`, `7,701.45`,
  `George`). A brief one-line explanation can follow if it adds clarity
  ("1 Australia deal in 2007 and 6 in 2009, so the difference is 5.").
- **List/dict answers** → valid JSON on the first line. Example:
  `{"Liberty": 157.85, "HomeCoreAdvantage": 134.7, "Infojini Inc": 245.7}`
  or `["7130200202","7130210809"]`. Use the entity names exactly as they
  appear in the workbook (or as the question phrases them — when in doubt
  prefer the question's spelling, e.g. `"Infojini Inc"` not
  `"InfoJini, Inc."`).
- **Tabular answers** → CSV with a header row, sorted deterministically by
  the grouping keys.
- **Plots** → PNG at ~160 dpi with title, axis labels, and units. Add
  mean/median guide lines and a compact stats footer when useful.
- **Mixed text + table** → both: a short textual answer plus the supporting
  CSV.

## Final response shape

Lead with the answer in bold. Examples:

> Total spent at **Swantown** is **$7,701.45**.
>
> **133** appearances (league only).
>
> Bill rates: **`{"Liberty": 157.85, "HomeCoreAdvantage": 134.7, "Infojini Inc": 245.7}`**.

Do not recap the steps you took, do not list validation work, do not offer
follow-ups. If the data didn't contain what was asked (e.g. wrong year, item
not present), say that explicitly — don't substitute the closest-looking
item and don't invent a number.
