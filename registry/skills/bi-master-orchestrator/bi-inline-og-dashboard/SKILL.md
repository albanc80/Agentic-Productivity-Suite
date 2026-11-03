---
name: bi-inline-og-dashboard
description: "Use when: the user asks for the BI MCP export-dashboard or get-dashboard behavior as an inline O&G intelligence dashboard, KPI dashboard, divergence dashboard, or executive summary without saving report files."
argument-hint: "Region, optional truth YoY, optional pulse MoM"
---

# BI Inline O&G Dashboard

Use this to replace the BI MCP `export-dashboard` and `get-dashboard` file-oriented behavior. Return a formatted inline dashboard in chat. Do not save files, return `filepath`, return a local path, or claim a PDF/XLSX was generated.

## Inputs

- `region`: optional label such as `Global`, `Permian`, `US Onshore`, or `EMEA`.
- `truthYoy`: optional authoritative year-over-year growth decimal.
- `pulseMom`: optional real-time month-over-month trend decimal.

## Databricks Query Pattern

Use the Databricks MCP with approved gold views. Prefer the narrower dashboard skill for basin-level executive intelligence when the user asks for permitting, rigs, and production.

For a divergence banner, compute:

```text
divergence_pct = abs((pulseMom - truthYoy) / truthYoy) * 100 when truthYoy != 0
```

If the user did not supply `truthYoy` or `pulseMom`, derive them from available Databricks aggregate trend data. If they cannot be derived, omit the divergence KPI and say which input was unavailable.

## Inline HTML Contract

Return a single self-contained HTML fragment:

```html
<section class="bi-dashboard og-dashboard">
  <h1>O&amp;G Intelligence Dashboard</h1>
  <p><strong>Region:</strong> ... <strong>Source:</strong> Databricks gold</p>
  <div class="kpis">...</div>
  <h2>Intelligence Summary</h2>
  <p>...</p>
  <h2>Key Metrics</h2>
  <table>...</table>
  <p class="caveat">Operational signals are directional and should be validated against authoritative planning sources.</p>
</section>
```

Keep CSS inline or minimal. Escape all values. Do not include scripts, external CSS, iframes, forms, downloads, or local links.
