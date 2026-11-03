---
name: bi-inline-executive-dashboard
description: "Use when: creating an inline formatted HTML executive O&G intelligence dashboard from Databricks gold data, replacing BI MCP dashboard export file behavior with direct in-chat HTML output."
argument-hint: "Optional basin and executive audience"
---

# BI Inline Executive Dashboard

Use this instead of file-export dashboard behavior. The agent should return formatted inline HTML in the chat response after querying Databricks. Do not write a local file, return a local file path, or claim a PDF was generated.

## Data Queries

If a basin is supplied, add `AND UPPER(envbasin) = UPPER(:basin)` to each query.

```sql
SELECT envbasin AS Basin,
       COUNT(*) AS Permits,
       COUNT(DISTINCT envoperator) AS Operators,
       date_format(MAX(approveddate),'yyyy-MM-dd') AS `Latest Approved`
FROM enverus_env_foundations_permits_view
WHERE approveddate >= add_months(current_date(), -12)
  AND envbasin IS NOT NULL AND envbasin <> ''
GROUP BY envbasin
ORDER BY Permits DESC
LIMIT 15
```

```sql
SELECT envbasin AS Basin,
       COUNT(DISTINCT rigname_number) AS `Active Rigs`,
       COUNT(DISTINCT envoperator) AS Operators,
       ROUND(AVG(permittospud_days),1) AS `Avg Permit-to-Spud (days)`,
       date_format(MAX(spuddate),'yyyy-MM-dd') AS `Latest Spud`
FROM enverus_env_foundations_rigs_view
WHERE spuddate >= add_months(current_date(), -12)
  AND envbasin IS NOT NULL AND envbasin <> ''
GROUP BY envbasin
ORDER BY `Active Rigs` DESC
LIMIT 15
```

```sql
SELECT envbasin AS Basin,
       COUNT(DISTINCT wellid) AS Wells,
       ROUND(SUM(prod_oilbbl)/1e6,2) AS `Oil (MMbbl)`,
       ROUND(SUM(gasprod_mcf)/1e6,2) AS `Gas (Bcf)`,
       date_format(MAX(producingmonth),'yyyy-MM-dd') AS `Latest Month`
FROM enverus_env_foundations_production_view
WHERE producingmonth >= add_months(current_date(), -6)
  AND envbasin IS NOT NULL AND envbasin <> ''
GROUP BY envbasin
ORDER BY `Oil (MMbbl)` DESC
LIMIT 15
```

## Inline HTML Contract

Return a single self-contained HTML fragment, not a full document. Use this structure:

```html
<section class="bi-dashboard">
  <h1>Executive Strategic Intelligence Dashboard</h1>
  <p><strong>Source:</strong> Databricks gold</p>
  <div class="kpis">...</div>
  <h2>Permitting Activity</h2>
  <table>...</table>
  <h2>Rig Activity</h2>
  <table>...</table>
  <h2>Production</h2>
  <table>...</table>
  <p class="caveat">Signals are operational proxies, not audited financial guidance.</p>
</section>
```

Keep styling inline or minimal. Do not include scripts, external CSS, iframes, forms, or links to local files. Escape all cell values before inserting them into HTML.
