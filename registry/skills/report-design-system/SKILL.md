---
name: report-design-system
description: A complete system for turning a written report into one **self-contained HTML
---

# Report design system

A complete system for turning a written report into one **self-contained HTML
file**: no CDN, no web fonts, no network requests at render time. Charts are
inline SVG generated at build time; the only script is a ~40-line tooltip layer.

Everything here is already built. Do not re-derive it — copy `assets/theme.py`
and `assets/charts.py` next to your builder and import them.

## Start here

1. **Run the worked example.** It proves the system end to end and shows most of
   the vocabulary in ~150 lines:

       python3 assets/example_report.py && open example-report.html

2. **Read `references/tokens.md`** for what the visual system is and which token
   controls what.
3. **Read `references/charts.md`** before writing any chart code — it has the
   form catalogue, the mark specs, and the colour rules.
4. **Read `references/authoring.md`** for the Markdown-report → HTML workflow,
   including the honesty rules that make these reports trustworthy.

## The shape of a build script

One script per document. It reads data, builds figures, and assembles the page:

```python
import sys, os
sys.path.insert(0, "assets")                    # or wherever theme/charts live

from charts import HAL_RED, SLOT, line_chart, stacked_panels
from theme import figure, hero, legend, page, section, stats

CH = {}                                          # chart id -> tooltip payload

SVG = line_chart(CH, "c1", labels, [
    {"name": "Requests", "color": HAL_RED, "values": values}],
    "Requests per day", "Date", area=True)

BODY = hero("Load Event Brief", "Title of the report",
            [("For", "Product Owner"), ("Date", "2026-08-16")]) \
     + section(1, "What happened", f"""
        <p class="lede">Opening sentence.</p>
        {figure(CH, 1, "Chart title", SVG, "Caption.", "", "c1", "Date",
                None, "evidence/source.csv", kind="Chart")}
        """)

open("report.html", "w").write(
    page(title="Title", kicker='Team · <b>System</b>', stamp="2026-08-16",
         body=BODY, charts=CH, footer="Built from evidence/."))
```

`page()` inlines `BASE_CSS`, `COMPONENTS_CSS`, `STATUS_CSS`, any `extra_css` you
pass, the chart payloads as JSON, and the tooltip script. Nothing else is emitted.

## Components available from `theme`

| Call | What it renders |
|---|---|
| `page(...)` | The whole document: masthead with wordmark, sheet, footer, inlined CSS/JS |
| `hero(eyebrow, title, meta, hot)` | Title block with the metadata grid |
| `section(num, title, body, sid)` | Numbered section with the rule heading |
| `stats(tiles)` | KPI row; exactly one `lead` tile per view |
| `figure(...)` / `diagram(...)` | Figure card: chip, title, legend, plot, caption, note, source, data table |
| `legend(names, colors, shape)` | `line` \| `band` \| `dot` swatches |
| `data_table(heads, rows, aligns)` | The prose-table style (2px ink header rule) |
| `caution(title, body)` | Accent-ruled callout for limits and warnings |
| `chip(text, tone, hollow)` | Inline status chip; tone `good` \| `warn` \| `bad` \| `info` \| `neutral`; `hollow` for absent / not yet |
| `status_note(label, body, tone)` | Block status annotation: tone rule, chip label, body |
| `kv(pairs)` | Definition rows for reference values |
| `rail(rows)` | Chronological observation rail with event markers |
| `event_key(items)` | The numbered-event key that sits under a figure title |
| `steps(items)` / `blk(label, html, learned)` | Numbered investigation steps |
| `fmt_value(v, unit)` | `requests` \| `percent` \| `gb` \| `ms` \| `seconds` \| `bytes` |

## Chart forms available from `charts`

`line_chart` · `stacked_columns` · `stacked_panels` (faceted stack, shared X) ·
`small_multiples` · `dumbbell` · `heat_strip` · `paired_bars` · `funnel_sankey`.
Every form registers its data in the `CH` dict so `figure()` can emit a tooltip
and a data table for it. See `references/charts.md`.

## Non-negotiables

These are what make the output trustworthy rather than merely pretty. Full
reasoning in `references/authoring.md`.

- **Self-contained.** No CDN, no web fonts, no runtime fetch. If it needs the
  network to render, it is wrong.
- **Prose is verbatim.** When rendering someone's report, do not rewrite their
  words. Add captions, source lines and data notes — not new phrasing.
- **Every figure names its source** and ships a `Data table` disclosure, so no
  value is reachable only by hovering or by colour.
- **One Y axis per chart.** Different units become panels on a shared X axis.
- **Gaps stay gaps.** A missing period breaks the line; it is never zero.
- **Partial periods are marked** — dashed tail, hollow end dot, and a note.
- **Colour follows the entity**, never rank: a series keeps its colour across
  every figure and every document in the set.
