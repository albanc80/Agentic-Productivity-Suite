# Design tokens and page anatomy

Every value here is already in `assets/theme.py`. This file explains what each
one controls, so you can change it deliberately rather than by trial.

## Colour

### Ink and surface

| Token | Value | Used for |
|---|---|---|
| `INK` | `#2A2F30` | Body text, section rules, the dark stat tile, tooltips |
| `INK_2` | `#5C6466` | Captions, axis tick labels, secondary prose |
| `INK_3` | `#8E979D` | Muted labels, notes, sources; also the "did not move" series colour |
| `SURFACE` | `#FFFFFF` | The sheet, chart backgrounds, mark rings and gaps |
| `SURFACE_2` | `#EFF0EF` | Page background behind the sheet, code chips, spanning rows |
| `LINE` | `#E2E5E4` | Borders, table rules, divider lines |
| `LINE_SOFT` | `#D8DCDB` | Panel separators inside a faceted stack |
| `GRID` | `#E6E8E7` | Chart gridlines (hairline, solid, never dashed) |
| `AXIS` | `#C9CDCD` | Baselines and tick marks |
| `REST_BAND` | `#CDD2D1` | The neutral "everything else" band in a stack |
| `HAL_RED` | `#CC0000` | The accent: eyebrow, figure chips, section numbers, series slot 1 |

The whole system is white sheet + charcoal ink + one accent. Red is spent on
identity and on the series that carries the story — never on decoration.

### Categorical series slots

```
SLOT = ["#CC0000", "#00819E", "#E07A52", "#5A6FB0", "#C79A2E", "#A34A72"]
         red        teal       coral      indigo     gold       plum
```

Assigned in order, never cycled. A seventh series folds into "Other", becomes
small multiples, or gets faceted. See `charts.md` for the validation these
passed and the pairs to avoid putting in one panel.

### Status tones

`chip()` and `status_note()` take a tone, not a colour:

| Tone | Hue | Means |
|---|---|---|
| `good` | teal `SLOT[1]` | Implemented, verified, in scope |
| `warn` | gold `SLOT[4]` | Partial, at risk |
| `bad` | red `HAL_RED` | Gap, failed, explicit non-goal |
| `info` | indigo `SLOT[3]` | Claimed but unverified, added later |
| `neutral` | `INK_3` | Out of scope, not applicable |

A chip is a tint of its hue (88% toward `SURFACE`) with a border (55%) and text
mixed 50% toward `INK`. Every tone clears 5:1 contrast on its tint. White text on
the raw hue does not: gold and neutral fall under 3:1. `hollow=True` drops the
fill and dashes the border, so an absent status never looks like a measured one.
Map a document's statuses to tones once, in one dict, and use them the same way
in every table.

Tones borrow series hues. If a chart in the same view already uses teal for an
entity, don't use `good` chips beside that chart's legend.

## Type

One sans stack, system-native, no web fonts:

```
-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Helvetica, Arial, sans-serif
```

Mono for code and identifiers: `ui-monospace, SFMono-Regular, Menlo, Consolas`.

| Role | Size / weight | Notes |
|---|---|---|
| Hero title | 44px / 700, `-0.02em` | Max 20ch, so it breaks into 2–3 lines |
| Section heading | 13px / 700, `0.14em`, uppercase | With a 2px ink bottom rule; number in accent |
| Sub-heading | 18px / 650 | Top rule, used inside a long section (`h3.sub`) |
| Minor heading | 16px / 650 | No rule; a Markdown `####` under a sub-heading (bare `h4`) |
| Lede | 19px / 1.55 | First paragraph of a section only |
| Body | 16px / 1.6 | `max-width: 74ch` |
| Prose list | Body size, 22px indent, 8px between items | Bare `ul` / `ol` from Markdown; classed lists are components and style themselves |
| Figure title | 17px / 600 | Beside an 11px accent chip (`CHART 1`, `FIGURE 3`) |
| Caption | 14px, `INK_2` | `max-width: 88ch` |
| Note / source | 12px, `INK_3` | Data caveats and the source file |
| Stat value | 30px / 650 — lead tile 52px | Proportional figures, not tabular |
| Axis text | 11.5px, tabular numerals | |
| Eyebrow / labels | 11.5px, `0.1em`, uppercase, `INK_3` | |

Tabular numerals are for **columns** of numbers (tables, axis ticks). Large
standalone values use proportional figures — `tabular-nums` makes a hero number
look loose.

## Layout

- Page max width **1160px**, sheet padding **56px** (22px under 900px).
- The sheet is white on the `SURFACE_2` page, bordered, with no top border —
  it hangs from the sticky masthead.
- Masthead: wordmark (176px, black) · 1px rule · kicker · right-aligned stamp.
  An "active" stamp uses a pulsing-free accent dot plus uppercase label.
- Sections: `padding-top: 56px`. Figures: `margin: 36px 0 44px`, 26px padding,
  1px `LINE` border.
- Grids (stat rows, source tables, limit cards) are built as **1px gaps over a
  `LINE` background** — the rules are the gaps, not borders.
- Charts render at a 1000-unit viewBox width, `width: 100%`, `height: auto`.

## Print

`@media print` drops the page background, un-sticks the masthead, removes the
sheet border, hides data-table disclosures and table-of-contents blocks, and
sets `break-inside: avoid` on figures.

Prose tables (`data_table`) lose their scroll box on paper, so print shrinks them
instead: 12px body, 10px headers, tighter padding, `nw` and `mono` cells allowed
to wrap, the header repeated on each page, and no row split across pages. For a
table that still overflows because its columns are too many rather than too long,
add `table.data { table-layout:fixed; }` inside `@media print` in that document's
`extra_css`. Fixed layout gives every column equal width, so it is not the default.

## Anatomy of a page

```
masthead        wordmark · kicker · stamp                    (sticky)
└ sheet
  ├ hero        eyebrow · h1 · meta grid (label/value pairs)
  ├ section 1   h2 with number and rule
  │  ├ lede + prose (74ch)
  │  ├ stats row (one dark lead tile, the rest light)
  │  └ figure card: chip · title · legend · plot · caption · note · source · table
  ├ section 2   prose · rail · data table · caution
  └ …
footer          one line, 12px, muted
```
