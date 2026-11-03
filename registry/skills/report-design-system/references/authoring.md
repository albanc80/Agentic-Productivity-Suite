# Authoring workflow

How a written report becomes one of these HTML documents, and the rules that
keep the result trustworthy.

## The pipeline

```
REPORT.md  +  evidence/*.csv   →   build_report.py   →   report.html
(the words)   (the numbers)        (theme + charts)      (self-contained)
```

One builder script per document. Builders share `theme.py` and `charts.py`, so a
change to the palette or the page shell lands in every report at once; anything
specific to one document — its extra CSS, its figure choices, its prose — stays
in that document's builder.

Keep paths resolvable from the repo root and allow overrides:

```python
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVIDENCE = os.environ.get("EVIDENCE_DIR", os.path.join(ROOT, "evidence"))
OUT_DIR  = os.environ.get("OUT_DIR", ROOT)
```

The prize is reproducibility: anyone can re-run the builder and get the same
bytes. Verify it — build to a temp dir and `cmp` against the committed file.

## Prose is verbatim

When you are rendering someone else's report, their words are the input, not a
draft. Copy headings, prose, tables, captions and code blocks exactly.

The builder may add only:

- **figure captions** describing what the chart shows,
- **source lines** naming the CSV behind each figure,
- **data notes** — partial periods, added columns, coverage gaps.

If a chart needs a departure from the written spec (an extra panel, an added
column), make it **and say so on the page**, in the note under that figure or
table. Record the departures in the builder's README so the next person knows
what the builder does beyond transcription.

## When the document specifies charts

Reports often carry a "visualization descriptions" section: goal, data, chart
type, axes, series, event lines, title, caption. Follow it literally, and use
its title and caption text verbatim. Where it says "three sub-charts to keep it
readable", that is a decision, not a default — override it only with a stated
reason.

## When the document specifies nothing

Build one figure per claim that has evidence behind it, and put the figure next
to the claim rather than in a gallery at the end. A step that cites a CSV gets a
figure from that CSV. Name the source under every one.

## Chronology beats grouping

If a finding spans several days, do not park it in one row at the end of the
timeline. Split it into per-period observations placed where they belong, and
mark them as a lane (a distinct dot colour and a tinted row). A reader following
the clock should meet each fact when it happened.

## Honesty rules

These are the difference between a report that survives review and one that
does not:

1. **Reconcile derived series against the authoritative total.** If a pivot's
   "everything else" column disagrees with the total file, derive it as
   `total − named parts` and say why in a comment.
2. **Never plot a partial period as if it were whole.** Drop it, or draw it
   dashed and annotate it.
3. **Absence of evidence is not zero.** Say which it is, in the mark.
4. **Quote the report's numbers even when your sum differs**, and record the
   discrepancy in the README so someone can reconcile the source. Charts plot
   the data; tables quote the document.
5. **State the scale.** Any non-linear colour or axis scale says so in its key.

## Review checklist

Before shipping a build:

- [ ] Opens with no network — check the page source for `http`
- [ ] No console errors; tooltips fire on every chart that has a hover layer
- [ ] Every figure: title, caption, source, data table
- [ ] Legend present for ≥ 2 series; single-series charts have none
- [ ] No two Y axes on one chart
- [ ] Partial periods, gaps and sparse coverage all marked
- [ ] Series colours match across every figure in the set
- [ ] Screenshot the rendered page and **look at it** — the validators check
      colour, not label collisions, overflow or crowding
- [ ] Rebuild to a temp dir and `cmp` against the committed output
