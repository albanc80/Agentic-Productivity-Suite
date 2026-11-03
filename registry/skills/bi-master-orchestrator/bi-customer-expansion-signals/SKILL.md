---
name: bi-customer-expansion-signals
description: "Use when: finding customer expansion signals, operators with recent permitting momentum, near-term demand, account prioritization, sales targets, or early buying signals."
argument-hint: "Customer, operator, basin, or sales-priority question"
---

# BI Customer Expansion Signals

Answer: which operators show early expansion buying signals.

```sql
SELECT envoperator AS Operator,
       COUNT(*) AS `Permits (3mo)`,
       COUNT(DISTINCT envbasin) AS Basins,
       date_format(MAX(approveddate),'yyyy-MM-dd') AS `Latest Permit`
FROM enverus_env_foundations_permits_view
WHERE approveddate >= add_months(current_date(), -3)
  AND envoperator IS NOT NULL
  AND envoperator <> ''
GROUP BY envoperator
ORDER BY `Permits (3mo)` DESC
LIMIT 15
```

Return a prioritized operator shortlist, explain whether signals are broad across basins or concentrated, and suggest follow-up filters.
