---
name: bi-guarded-databricks-query
description: "Use when: the user needs a direct read-only Databricks SQL query for BI/O&G intelligence. Adds guardrails for Databricks MCP query use: allowed statements, row limits, table scope, parameter handling, and safe summarization."
argument-hint: "Business question, approved table/view, filters, desired columns"
---

# BI Guarded Databricks Query

Use the existing Databricks MCP as the execution layer. This skill is for direct SQL only when no narrower BI skill fits.

## Guardrails

- Run read-only SQL only: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, or `EXPLAIN`.
- Never run `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `COPY`, `OPTIMIZE`, `VACUUM`, `GRANT`, `REVOKE`, `REFRESH`, `MSCK`, `RESTORE`, or notebook/task/job commands.
- Prefer Databricks `gold` views used by the BI MCP server. Do not discover or query sensitive schemas unless the user explicitly names an approved object.
- Default to `LIMIT 50`; never exceed `LIMIT 200` unless the user explicitly asks for an aggregate count or export-safe result.
- For entity filters such as basin, operator, country, state, contractor, or commodity, use parameters when the MCP supports them. If parameters are unavailable, allow only letters, digits, spaces, ampersand, underscore, hyphen, and period before interpolating.
- Do not query credential tables, user/account tables, audit logs, raw PII, secrets, tokens, connection strings, or unrestricted free-text document bodies.
- Avoid `SELECT *`; select named columns needed for the business answer.
- For user-provided table names, allow only alphanumeric characters, underscore, and dot. Reject paths, semicolons, comments, or whitespace.
- If the user asks for mutation or data export, stop and ask for a separate approved workflow.

## Procedure

1. Translate the user request into one business question.
2. Choose the narrowest approved table/view and select only necessary columns.
3. Add date windows, filters, aggregations, and row limits.
4. Run the SQL with the Databricks MCP.
5. Summarize the answer with source view names, time window, row count, and caveats.

## Safe SQL Template

```sql
SELECT
  <dimension_column> AS Dimension,
  COUNT(*) AS Records
FROM <approved_catalog>.<approved_schema>.<approved_view>
WHERE <date_column> >= add_months(current_date(), -12)
  AND <dimension_column> IS NOT NULL
  AND <dimension_column> <> ''
GROUP BY <dimension_column>
ORDER BY Records DESC
LIMIT 50
```

## Response Contract

Return:

- short answer first;
- table of the most important rows;
- `Source: Databricks gold - <view name>`;
- time window and filters used;
- note when a result is a proxy indicator rather than a forecast or audited financial statement.
