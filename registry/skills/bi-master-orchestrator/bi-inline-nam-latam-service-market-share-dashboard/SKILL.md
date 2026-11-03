---
name: bi-inline-nam-latam-service-market-share-dashboard
argument-hint: "First year and last year"
---

# BI Inline NAM/LATAM Service Market Share Dashboard

Use this to replace `export-nam-latam-service-company-market-share-dashboard` file export behavior. Return inline formatted HTML in chat. Do not save files, return `filepath`, or claim a report was generated on disk.

## Inputs

- `firstYear`: default `2019`, clamp to `2010-2030`.
- `lastYear`: default `2026`, clamp to `firstYear-2035`.
- Treat `2024` as the latest actual year unless the user supplies a newer validated actual year.

## Required Databricks Queries

```sql
SELECT CASE
         WHEN g.Continent = 'North America' THEN 'NAM'
         WHEN g.Continent = 'South America' THEN 'LATAM'
       END AS region,
       t.Year AS year,
       SUM(COALESCE(rv.Revenue, 0)) AS total_market_revenue
FROM gold.rystadenergy_servicesupplycube_revenuevalues_view rv
JOIN gold.rystadenergy_servicesupplycube_timeline_view t ON rv.FK_Timeline = t.Id
JOIN gold.rystadenergy_servicesupplycube_geography_view g ON rv.FK_Geography = g.Id
WHERE g.Continent IN ('North America', 'South America')
  AND t.Year BETWEEN :firstYear AND :lastYear
GROUP BY 1, 2
ORDER BY 1, 2
```

```sql
SELECT CASE
         WHEN g.Continent = 'North America' THEN 'NAM'
         WHEN g.Continent = 'South America' THEN 'LATAM'
       END AS region,
       t.Year AS year,
       COALESCE(sc.`Service Company`, oc.`Original Company`) AS service_company,
       SUM(COALESCE(rv.Revenue, 0)) AS revenue
FROM gold.rystadenergy_servicesupplycube_revenuevalues_view rv
JOIN gold.rystadenergy_servicesupplycube_originalcompany_view oc ON rv.FK_OriginalCompany = oc.Id
LEFT JOIN gold.rystadenergy_servicesupplycube_company_view sc ON oc.FK_Company = sc.Id
JOIN gold.rystadenergy_servicesupplycube_timeline_view t ON rv.FK_Timeline = t.Id
JOIN gold.rystadenergy_servicesupplycube_geography_view g ON rv.FK_Geography = g.Id
WHERE g.Continent IN ('North America', 'South America')
  AND t.Year BETWEEN :firstYear AND :lastYear
GROUP BY 1, 2, 3
ORDER BY 1, 2, 4 DESC
```

```sql
SELECT CASE
         WHEN g.Continent = 'North America' THEN 'NAM'
         WHEN g.Continent = 'South America' THEN 'LATAM'
       END AS region,
       COALESCE(sc.`Service Company`, oc.`Original Company`) AS service_company,
       COALESCE(ss.`Service Segment Group`, 'Unclassified') AS service_segment,
       SUM(COALESCE(rv.Revenue, 0)) AS revenue
FROM gold.rystadenergy_servicesupplycube_revenuevalues_view rv
JOIN gold.rystadenergy_servicesupplycube_originalcompany_view oc ON rv.FK_OriginalCompany = oc.Id
LEFT JOIN gold.rystadenergy_servicesupplycube_company_view sc ON oc.FK_Company = sc.Id
JOIN gold.rystadenergy_servicesupplycube_timeline_view t ON rv.FK_Timeline = t.Id
JOIN gold.rystadenergy_servicesupplycube_geography_view g ON rv.FK_Geography = g.Id
LEFT JOIN gold.rystadenergy_servicesupplycube_servicesegment_view ss ON rv.FK_ServiceSegment = ss.Id
WHERE g.Continent IN ('North America', 'South America')
  AND t.Year = 2024
GROUP BY 1, 2, 3
HAVING revenue > 0
ORDER BY 1, 4 DESC
```

## Inline HTML Contract

Return a fragment with NAM and LATAM sections, market revenue, Big 4 revenue, Big 4 share of market, company ranking, segment concentration, trend table, and data-quality notes. State that LATAM maps to South America in this recipe.
