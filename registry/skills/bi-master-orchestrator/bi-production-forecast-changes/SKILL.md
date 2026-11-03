---
name: bi-production-forecast-changes
description: "Use when: analyzing production forecast changes, production acceleration, basin production momentum, oil or gas production trends, recent monthly changes, and service demand shifts."
argument-hint: "Optional basin filter"
---

# BI Production Forecast Changes

Answer: where production is accelerating and where service demand may shift.

If a basin is supplied, add `AND UPPER(envbasin) = UPPER(:basin)`.

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

```sql
SELECT date_format(producingmonth,'yyyy-MM') AS Month,
       ROUND(SUM(prod_oilbbl)/1e6,2) AS `Oil (MMbbl)`,
       ROUND(SUM(gasprod_mcf)/1e6,2) AS `Gas (Bcf)`,
       COUNT(DISTINCT wellid) AS Wells
FROM enverus_env_foundations_production_view
WHERE producingmonth >= add_months(current_date(), -4)
  AND envbasin IS NOT NULL AND envbasin <> ''
GROUP BY date_format(producingmonth,'yyyy-MM')
ORDER BY Month DESC
LIMIT 6
```

State the latest month, direction of recent trend, and whether the signal is oil-led, gas-led, or well-count-led.
