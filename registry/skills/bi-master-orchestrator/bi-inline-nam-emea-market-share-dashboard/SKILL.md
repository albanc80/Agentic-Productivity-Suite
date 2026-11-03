---
name: bi-inline-nam-emea-market-share-dashboard
description: "Use when: creating an inline NAM/EMEA market share dashboard, global opportunity heat map, TAM/SAM/SOM view, operator capex dashboard, country capex dashboard, basin capex dashboard, NOC/IOC spend view, or KPI dashboard from Databricks gold data."
argument-hint: "Optional NAM countries, optional EMEA countries, top N, capability fit factor"
---

# BI Inline NAM/EMEA Market Share Dashboard

Use this to replace `export-nam-emea-market-share-dashboard` file export behavior. Return inline formatted HTML in chat. Do not save files, return `filepath`, or claim a report was generated on disk.

## Inputs

- `namCountries`: optional list of North America countries.
- `emeaCountries`: optional list of EMEA countries.
- `topN`: default `20`, clamp to `5-50`.
- `capabilityFitFactor`: default `1.0`, clamp to `0-1`.

## Region Scope

- NAM: `region = 'North America'`.
- EMEA: `region IN ('Western Europe','Eastern Europe','Middle East','North Africa','West Africa','East Africa','South Africa')`.

## Required Databricks Queries

Discover country scope first, then query operator and service-company revenue data.

```sql
SELECT DISTINCT country AS country
FROM gold.rystadenergy_ucubedatafeed_geography_view
WHERE region = 'North America'
  AND country IS NOT NULL AND TRIM(country) <> ''
ORDER BY country
```

```sql
SELECT DISTINCT country AS country
FROM gold.rystadenergy_ucubedatafeed_geography_view
WHERE region IN ('Western Europe','Eastern Europe','Middle East','North Africa','West Africa','East Africa','South Africa')
  AND country IS NOT NULL AND TRIM(country) <> ''
ORDER BY country
```

For each selected region/country set:

```sql
SELECT c.Company AS company,
       country AS country,
       SUM(COALESCE(fao.`Remaining Resources`, fao.`Original Resources`, 0) * (ABS(COALESCE(ao.Participation, 100)) / 100.0)) AS operator_value,
       COUNT(DISTINCT fao.FK_Asset) AS assets,
       AVG(COALESCE(fao.`Half Cycle Breakeven Oil Price`, 0)) AS avg_half_cycle_breakeven
FROM gold.rystadenergy_ucubedatafeed_factassetownership_view fao
JOIN gold.rystadenergy_ucubedatafeed_geography_view g ON fao.FK_Geography = g.PK_Geography
JOIN gold.rystadenergy_ucubedatafeed_company_view c ON fao.FK_Company = c.PK_Company
LEFT JOIN gold.rystadenergy_ucubedatafeed_assetownership_view ao ON fao.FK_Asset = ao.PK_AssetOwnership
WHERE c.Company IS NOT NULL
  AND country IN (:countries)
  AND <region_filter>
GROUP BY c.Company, country
HAVING operator_value > 0
ORDER BY operator_value DESC
LIMIT 1000
```

```sql
WITH latest_year AS (
  SELECT MAX(Year) AS max_year
  FROM gold.rystadenergy_servicesupplycube_timeline_view
)
SELECT COALESCE(sc.`Service Company`, oc.`Original Company`) AS service_company,
       oc.`Head Quarter Country` AS country,
       SUM(COALESCE(rv.Revenue, 0)) AS revenue,
       SUM(COALESCE(rv.`Reported Revenue`, 0)) AS reported_revenue
FROM gold.rystadenergy_servicesupplycube_revenuevalues_view rv
JOIN gold.rystadenergy_servicesupplycube_originalcompany_view oc ON rv.FK_OriginalCompany = oc.Id
LEFT JOIN gold.rystadenergy_servicesupplycube_company_view sc ON oc.FK_Company = sc.Id
JOIN gold.rystadenergy_servicesupplycube_timeline_view t ON rv.FK_Timeline = t.Id
CROSS JOIN latest_year y
WHERE t.Year = y.max_year
  AND oc.`Head Quarter Country` IN (:countries)
  AND COALESCE(sc.`Service Company`, oc.`Original Company`) IS NOT NULL
GROUP BY COALESCE(sc.`Service Company`, oc.`Original Company`), oc.`Head Quarter Country`
HAVING revenue > 0
ORDER BY revenue DESC
LIMIT 1000
```

## Inline HTML Contract

Return a fragment with KPI cards, NAM and EMEA sections, top operators, top service companies, TAM/SAM/SOM narrative, data quality notes, and source view names. Escape all values and avoid scripts/external assets.
