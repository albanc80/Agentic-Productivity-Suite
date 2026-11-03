---
name: bi-esg-regulatory-impact
description: "Use when: analyzing ESG, methane, flaring, regulatory exposure, gas flaring intensity, compliance-led service demand, or operators with environmental risk indicators."
argument-hint: "Operator, basin, or ESG/regulatory question"
---

# BI ESG Regulatory Impact

Answer: which operators face the greatest methane/flaring regulatory exposure.

```sql
SELECT producingoperator AS Operator,
       ROUND(SUM(flaredgasprod_mcf)/1e3,1) AS `Flared Gas (MMcf)`,
       ROUND(100*SUM(flaredgasprod_mcf)/NULLIF(SUM(gasprod_mcf),0),2) AS `Flaring %`,
       COUNT(DISTINCT wellid) AS Wells
FROM enverus_env_foundations_production_view
WHERE producingmonth >= add_months(current_date(), -6)
  AND producingoperator IS NOT NULL
  AND producingoperator <> ''
GROUP BY producingoperator
HAVING SUM(flaredgasprod_mcf) > 0
ORDER BY `Flared Gas (MMcf)` DESC
LIMIT 15
```

Rank operators by absolute flaring and flaring percentage. Note whether exposure is volume-driven or intensity-driven.
