---
name: bi-operator-spending-analysis
description: "Use when: analyzing operator spending, capital deployment proxies, permits, active rigs, operator momentum, drilling-program scale, operator prioritization, or account targeting."
argument-hint: "Optional operator name, e.g. EXXON or OCCIDENTAL"
---

# BI Operator Spending Analysis

Answer: which operators are increasing spending and where. Use permitting and rig activity as capital-deployment proxies.

If an operator is supplied, add `AND UPPER(envoperator) = UPPER(:operator)`.

```sql
SELECT envoperator AS Operator,
       COUNT(*) AS Permits,
       COUNT(DISTINCT envbasin) AS Basins,
       date_format(MAX(approveddate),'yyyy-MM-dd') AS `Latest Permit`
FROM enverus_env_foundations_permits_view
WHERE approveddate >= add_months(current_date(), -12)
  AND envoperator IS NOT NULL
  AND envoperator <> ''
GROUP BY envoperator
ORDER BY Permits DESC
LIMIT 15
```

```sql
SELECT envoperator AS Operator,
       COUNT(DISTINCT rigname_number) AS `Active Rigs`,
       COUNT(DISTINCT envbasin) AS Basins,
       date_format(MAX(spuddate),'yyyy-MM-dd') AS `Latest Spud`
FROM enverus_env_foundations_rigs_view
WHERE spuddate >= add_months(current_date(), -12)
  AND envoperator IS NOT NULL
  AND envoperator <> ''
GROUP BY envoperator
ORDER BY `Active Rigs` DESC
LIMIT 15
```

Summarize operators by program scale, basin breadth, and recency. State that this is a proxy, not audited spend.
