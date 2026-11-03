---
name: bi-completion-market-growth
argument-hint: "Optional basin filter"
---

# BI Completion Market Growth

Answer: which basins require more completions and where completion or frac service demand is growing.

If a basin is supplied, add `AND UPPER(envbasin) = UPPER(:basin)`.

```sql
SELECT envbasin AS Basin,
       COUNT(DISTINCT completionid) AS Completions,
       COUNT(DISTINCT envoperator) AS Operators,
       COUNT(DISTINCT rigname_number) AS Rigs,
       date_format(MAX(spuddate),'yyyy-MM-dd') AS `Latest Spud`
FROM enverus_env_foundations_rigs_view
WHERE spuddate >= add_months(current_date(), -12)
  AND completionid IS NOT NULL
GROUP BY envbasin
ORDER BY Completions DESC
LIMIT 15
```

Return the top basins, completion volume, operator breadth, and whether the demand signal is concentrated or broad-based.
