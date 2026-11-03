---
name: bi-drilling-demand-forecast
description: "Use when: forecasting drilling demand, finding basins where drilling activity may increase, analyzing permits, rig activity, active rigs, permit-to-spud timing, or 6-24 month O&G demand signals from Databricks gold data."
argument-hint: "Optional basin, e.g. DELAWARE, MIDLAND, WILLISTON"
---

# BI Drilling Demand Forecast

Answer: where drilling activity is increasing and where demand may rise in the next 6-24 months.

Use the Databricks MCP to run both queries. If a basin is supplied, add this filter after the non-empty basin predicate: `AND UPPER(envbasin) = UPPER(:basin)`.

## Queries

```sql
SELECT envbasin AS Basin,
       COUNT(*) AS Permits,
       COUNT(DISTINCT envoperator) AS Operators,
       date_format(MAX(approveddate),'yyyy-MM-dd') AS `Latest Approved`
FROM enverus_env_foundations_permits_view
WHERE approveddate >= add_months(current_date(), -12)
  AND envbasin IS NOT NULL
  AND envbasin <> ''
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
  AND envbasin IS NOT NULL
  AND envbasin <> ''
GROUP BY envbasin
ORDER BY `Active Rigs` DESC
LIMIT 15
```

## Output

Summarize basins with both permitting and active-rig strength. Call out permit-heavy basins with lagging rig activity as possible near-term conversion signals.
