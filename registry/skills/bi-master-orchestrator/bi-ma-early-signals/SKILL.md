---
name: bi-ma-early-signals
description: "Use when: analyzing M&A early signals, upstream deals, portfolio moves, announced transactions, deal type summaries, or pre-campaign market movement in O&G."
argument-hint: "M&A signal or deal activity question"
---

# BI M&A Early Signals

Answer: which portfolio moves are likely to precede drilling campaigns.

```sql
SELECT date_format(dateannounced,'yyyy-MM-dd') AS Announced,
       buyers AS Buyer,
       sellers AS Seller,
       dealtype AS Type,
       dealstatus AS Status,
       ROUND(value_mm,0) AS `Value (MM$)`
FROM enverus_env_ma_transactions_view
WHERE dateannounced >= add_months(current_date(), -12)
  AND value_mm IS NOT NULL
ORDER BY value_mm DESC
LIMIT 15
```

```sql
SELECT COALESCE(NULLIF(dealtype,''),'Unspecified') AS `Deal Type`,
       COUNT(*) AS Deals,
       ROUND(SUM(value_mm),0) AS `Disclosed Value (MM$)`
FROM enverus_env_ma_transactions_view
WHERE dateannounced >= add_months(current_date(), -12)
GROUP BY dealtype
ORDER BY Deals DESC
LIMIT 15
```

Summarize large transactions, dominant deal types, and likely follow-up questions. Avoid saying a deal will produce drilling unless the data shows follow-on activity.
