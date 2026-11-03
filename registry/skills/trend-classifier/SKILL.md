---
name: trend-classifier
description: Classifies a stored sentiment score series as rising, falling, flat, or insufficient data. Call after scores are written, before reporting direction.
---

# Skill 05 — Trend Classifier

**Type:** AI Builder prompt
**Attached to:** Sentiment Radar
**Version:** 1.0

## Purpose

Turn a stored score series into a reproducible direction call, so the "3+
readings" rule is applied deterministically rather than judged inline.

## Inputs

| Name | Type | Source |
|---|---|---|
| `stakeholder` | Text | Stakeholder identifier |
| `score_series` | Text | JSON array from the tracking list: `[{score, date, rubric_version}]`, oldest first |

## Instruction

```
Classify the direction of this sentiment series.

STAKEHOLDER: {stakeholder}
SERIES (oldest first): {score_series}

RULES
- Ignore entries where score is null. They are non-substantive messages and
  carry no signal.
- Count remaining readings. If fewer than 3, return
  classification = "INSUFFICIENT_DATA" and stop. Do not describe a direction.
  Two points are not a trend no matter how far apart they sit.
- With 3 or more readings, compare the mean of the most recent 3 against the
  mean of the prior readings:
    difference <= -1.5  -> FALLING
    difference >= +1.5  -> RISING
    otherwise           -> FLAT
- If the series mixes rubric_version values, still classify, but set
  rubric_mismatch = true. A rubric change can produce an apparent shift that is
  a definitional artifact, not a real one.
- If the most recent reading is more than 14 days old, set stale = true and
  report the age. A trend from dormant data is not a current reading.
- Report the computed numbers. Do not editorialize about what the direction
  means, what caused it, or what to do about it.
```

## Output contract (JSON)

```json
{
  "stakeholder": "string",
  "classification": "RISING | FALLING | FLAT | INSUFFICIENT_DATA",
  "readings_used": 0,
  "recent_mean": 0.0,
  "prior_mean": 0.0,
  "difference": 0.0,
  "rubric_mismatch": false,
  "stale": false,
  "days_since_last_reading": 0
}
```

## Test cases

| # | Input | Pass condition |
|---|---|---|
| 1 | Two readings, 9 then 4 | `INSUFFICIENT_DATA`, no direction described |
| 2 | Five readings drifting 8→5 | `FALLING` with the arithmetic shown |
| 3 | Readings oscillating 6,8,6,8 | `FLAT` |
| 4 | Series with nulls interspersed | Nulls excluded from `readings_used` |
| 5 | Series spanning rubric 1.0 and 1.1 | `rubric_mismatch: true` |
| 6 | Last reading 30 days old | `stale: true`, age reported |
