# Chart system

Read this before writing chart code. The forms are in `assets/charts.py`; every
one of them registers its payload in the `CH` dict you pass, so `figure()` can
emit the tooltip and the data table without extra work.

## The form catalogue

| Form | Use it for |
|---|---|
| `line_chart` | One or a few series over time. Options: `area`, `dashed_tail`, `tail_dot`, `hrules`, `vrules`, `end_labels`, `day_seps` |
| `stacked_columns` | Composition over time — parts of a daily total |
| `stacked_panels` | **The workhorse.** Measures in different units on one shared X axis, panels flush, event rules drawn through all of them |
| `small_multiples` | The same measure for many entities, one shared Y scale |
| `dumbbell` | Before/after per entity — a baseline value against an event value |
| `heat_strip` | One cell per period, one lane per measure: the whole window at a glance, as an index above a long timeline |
| `paired_bars` | Two measures per item on one scale (request vs response bytes, budget vs actual) |
| `funnel_sankey` | A sequential part-to-whole funnel per entity (written → merged → surviving), every lane on one scale, drop-outs peeled off as named grey ribbons |

Helpers: `nice_ticks` / `tight_ticks` (round axis tops with minimal headroom),
`ramp(base, n)` (a sequential scale from any hue), `event_rows` (stagger
colliding event markers onto extra rows), `Canvas` (the SVG primitive).

## Mark specs

| Mark | Spec |
|---|---|
| Line | 2px, round join and cap |
| Area fill | Series hue at ~9% opacity — a wash, never a block |
| Marker / end dot | r ≥ 4 with a 2px `SURFACE` ring so it stays legible over a line |
| Hollow dot | `SURFACE` fill + coloured ring — a measured zero, or a partial final period |
| Bar / column | ≤ 24px thick, 4px rounded data-end, square at the baseline |
| Stack segments | 2px `SURFACE` gap between segments — white separates, never a stroke |
| Gridlines | 1px, solid, `GRID`; axis line `AXIS` |
| Event rule | 1px dashed ink at 50–55% with a numbered ink chip at the top |
| Direct label | 12px 600 with a 3.5px `SURFACE` stroke behind it (`paint-order: stroke`) |

## Colour rules

1. **Colour follows the entity.** A series keeps its slot across every figure and
   every document in a set. Filtering a chart must not repaint the survivors.
2. **Assign slots in order, never cycle.** Past six series: fold to "Other",
   facet into small multiples, or split the chart.
3. **Neutral means "did not move."** `INK_3` on a control series is a deliberate
   argument: the reader sees at a glance which measures are inert.
4. **Same metric, two aggregates** (hottest vs average) share one hue and differ
   by opacity — that is an ordinal relationship, not two identities.
5. **Sequential ramps are one hue, light → dark**, from `ramp()`. Never a rainbow.
   A non-linear scale (sqrt, log) must say so in its key.
6. **Text never wears the series colour.** Labels use ink tokens; identity comes
   from the coloured mark beside them.

### Validation

The six slots pass, in OKLab: the lightness band (0.43–0.77), the chroma floor
(≥ 0.10), adjacent-pair CVD separation under protanopia and deuteranopia, and
the normal-vision floor. Two known constraints:

- **coral + gold** collapse when compared directly (ΔE ~10 normal). They are
  never adjacent in slot order; keep them out of the same panel, or separate
  them in time.
- **red + plum** fail the normal-vision floor as a pair — do not put them in one
  panel. Red + teal, red + coral, red + gold and coral + teal are all clear.

Gold and coral fall below 3:1 contrast on white. That is legal here **because**
every chart carries direct labels and a data table; do not drop those.

## Interaction

Every chart gets a crosshair tooltip by default. `figure()` wires it up from the
`CH` payload: hit bands span the full plot (or the full stack, for
`stacked_panels`), focus dots skip null values, and each series formats by its
own `unit`. Forms that carry their values as direct labels — `dumbbell`,
`small_multiples`, `paired_bars`, `funnel_sankey` — register data for the table
view but draw no hover layer, which is the right call when every number is
already on the page.

## Funnels

`funnel_sankey(CH, cid, stages, rows, losses=, split=, noun=, end_word=)` draws
one lane per entity, and every lane shares one scale: a wider ribbon is more, in
any lane. It refuses input that would mislead:

- A stage may not exceed the one before it. A funnel only loses, and a gain means
  the stages are not one sequence.
- Every drop-out is drawn as an `INK_3` ribbon peeling off below the flow, named
  by `losses` and labelled with its count and its share of the first stage. It is
  never just a narrower next node.
- A final-node `split` must sum to the final value. It is drawn in one hue at two
  opacities, because the parts belong to one entity.
- A row's `note` sits against the source node. Use it to explain a number
  (a one-off bulk import, say) rather than silently deducting it.

Reconcile the stages against the source before plotting: each stage should equal
the next stage plus what dropped out between them.

## Honesty in the mark, not the caption

- A missing period **breaks the line**. Zero is a measurement; absent is not.
- A sparse series (logs that cover two hours a day) is drawn as **stems and
  dots at the observed periods**, with a **hollow dot for a measured zero**, so
  "we measured nothing" and "we did not measure" stay distinguishable.
- A partial final period gets a **dashed segment and a hollow end dot**, plus a
  note — otherwise a mid-period export reads as a collapse.
- A series with no data at all (a source that logs nothing) is drawn **at zero
  and labelled as such**, not omitted. Omitting it implies it was cleared.
