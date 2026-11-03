---
name: bi-basin-ranking
description: "Use when: ranking basins, identifying attractive or under-served O&G basins, comparing permitting, rig activity, production, operators, and production intensity from Databricks gold views."
argument-hint: "Region or ranking question"
---

# BI Basin Ranking

Answer: which basins are most attractive and which may be under-served.

Run all three queries and compare permitting, rig activity, and production.

```sql
SELECT envbasin AS Basin, COUNT(*) AS Permits, COUNT(DISTINCT envoperator) AS Operators
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
       ROUND(AVG(permittospud_days),1) AS `Avg Permit-to-Spud (days)`
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
       ROUND(SUM(gasprod_mcf)/1e6,2) AS `Gas (Bcf)`
FROM enverus_env_foundations_production_view
WHERE producingmonth >= add_months(current_date(), -6)
  AND envbasin IS NOT NULL AND envbasin <> ''
GROUP BY envbasin
ORDER BY `Oil (MMbbl)` DESC
LIMIT 15
```

Output a ranked list with rationale. Mark under-served candidates where production or permitting is high but rig/service indicators are not proportionally high.
