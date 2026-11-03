---
name: bi-competitor-intelligence
argument-hint: "Competitor or year-range question"
---

# BI Competitor Intelligence

Answer: what competitors are doing that signals market share movement.

```sql
SELECT sc.`Service Company` AS Company,
       t.Year AS Year,
       ROUND(SUM(rv.Revenue),0) AS `Revenue (MUSD)`
FROM rystadenergy_servicesupplycube_revenuevalues_view rv
JOIN rystadenergy_servicesupplycube_originalcompany_view oc ON rv.FK_OriginalCompany = oc.Id
JOIN rystadenergy_servicesupplycube_company_view sc ON oc.FK_Company = sc.Id
JOIN rystadenergy_servicesupplycube_timeline_view t ON rv.FK_Timeline = t.Id
  AND t.Year BETWEEN 2021 AND 2024
GROUP BY sc.`Service Company`, t.Year
ORDER BY t.Year DESC, `Revenue (MUSD)` DESC
```

Return a year-by-company table, trend commentary, and any share movement visible from the result. Do not infer strategy beyond the revenue trend unless the user supplies more evidence.
