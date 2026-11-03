---
name: bi-energy-transition-opportunities
description: "Use when: finding low-carbon, emissions reduction, gas flaring, produced water, water management, decarbonization, abandonment, or energy transition opportunities from O&G production data."
argument-hint: "Basin, operator, or region question"
---

# BI Energy Transition Opportunities

Answer: where adjacent low-carbon or decarbonization opportunities are forming.

```sql
SELECT envbasin AS Basin,
       ROUND(SUM(flaredgasprod_mcf)/1e3,1) AS `Flared Gas (MMcf)`,
       ROUND(100*SUM(flaredgasprod_mcf)/NULLIF(SUM(gasprod_mcf),0),2) AS `Flaring %`,
       COUNT(DISTINCT wellid) AS Wells
FROM enverus_env_foundations_production_view
WHERE producingmonth >= add_months(current_date(), -6)
  AND envbasin IS NOT NULL AND envbasin <> ''
GROUP BY envbasin
HAVING SUM(flaredgasprod_mcf) > 0
ORDER BY `Flared Gas (MMcf)` DESC
LIMIT 15
```

```sql
SELECT envbasin AS Basin,
       ROUND(SUM(waterprod_bbl)/1e6,2) AS `Water (MMbbl)`,
       COUNT(DISTINCT wellid) AS Wells
FROM enverus_env_foundations_production_view
WHERE producingmonth >= add_months(current_date(), -6)
  AND envbasin IS NOT NULL AND envbasin <> ''
GROUP BY envbasin
ORDER BY `Water (MMbbl)` DESC
LIMIT 15
```

Summarize flaring and produced-water intensity separately. Tie opportunities to emissions reduction, gas capture, water management, and well abandonment only as demand implications.
