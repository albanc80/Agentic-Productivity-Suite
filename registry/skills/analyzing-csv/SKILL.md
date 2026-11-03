---
name: analyzing-csv
description: Analyzes CSV files and answers user questions about tabular data. Extracts metadata (columns, types, sample values) and performs data lookup, aggregation, and filtering using pandas. Use when the user asks questions about standalone CSV files or needs information extracted from .csv data. If an .xlsx workbook is supplied alongside the CSV, use analyzing-xlsx instead.
---

# CSV Analysis

## Preprocessing workflow

When you receive a CSV file to analyze, run the preprocessor first:

```bash
python /app/skills/analyzing-csv/scripts/preprocess.py <csv_path>
```

## Preprocessing output

The preprocessor writes artifacts to a versioned directory, which contains two files.

### manifest.json

Read this first. It describes what was extracted and whether any issues occurred.

| Field | Description |
|-------|-------------|
| `preprocessor_version` | Version of the extraction logic |
| `extractor_versions` | Library versions used (e.g. pandas) |
| `config` | Runtime settings (`max_csv_size_mb`, `categorical_scan_rows`, `date_scan_limit`) |
| `source_file` | Original file info: `name`, `sha256`, `size_bytes` |
| `artifacts` | List of produced files — each entry has `type`, `path`, `row_count`, `column_count` |
| `limits_applied` | Flags for skipped steps (e.g. `file_size_skip: true` if CSV > 100 MB) |
| `warnings` | Human-readable warnings (empty list on success) |
| `created_at` | ISO-8601 UTC timestamp |

Check `warnings` and `limits_applied` before relying on artifact files — if the CSV was too large or extraction failed, `metadata.json` may not exist.

### metadata.json

```json
{
    "file_name": "data.csv",
    "encoding": "utf-8",
    "columns": ["Name", "Date", "Amount", "Category"],
    "dtypes": {"Name": "string", "Date": "date (string format)", "Amount": "float", "Category": "string"},
    "row_count": 1247,
    "sample_rows": [
        {"Name": "Alice", "Date": "2024-01-15", "Amount": 150.00, "Category": "Sales"}
    ],
    "categorical_columns": {"Category": {"unique_count": 5, "values": ["Sales", "Marketing", ...]}},
    "null_counts": {"Name": 0, "Date": 0, "Amount": 3, "Category": 0}
}
```

- `columns` + `dtypes` — column names and their detected types
- `sample_rows` — first 5 rows for understanding data shape
- `categorical_columns` — low-cardinality string columns (<=20 unique values) with their values
- `null_counts` — missing value counts per column

## Answering questions from CSV data

### 1. Analyze the user's question
Before searching, parse the user's query to identify:
- **Intent**: What type of answer is expected (a lookup, an aggregation, a count, a comparison, a ranking, etc.)
- **Keywords**: Key terms that map to column names or data values
- **Entities**: Specific names, dates, categories, or identifiers to filter on

### 2. Map keywords to columns
Use the metadata to match the user's keywords to actual column names:
- Try literal match first — if the question says "Column 2 Rate", search for that exact string
- Then try substring match on column names (e.g., "revenue" → `Total_Revenue`)
- If no match, report available columns; do NOT guess

### 3. Search and filter the data
```python
import pandas as pd
df = pd.read_csv('file.csv')
```

**Critical matching rules:**
- **Column names**: fuzzy/substring matching is OK
- **Data values**: use **exact matching**, not `contains()`

```python
# BAD: df[df['warehouse'].str.contains('East')]  — may match 'Eastern', 'EU-East'
# GOOD: df[df['warehouse'].str.lower() == 'east']
```

If the requested time period, category, or entity does not exist in the data, stop and report it — do not hallucinate.

### 4. Verify before answering
Print filter criteria and matched rows before reporting:

```python
result = df[df['Sector'] == 'Energy']
print(f"Filter: Sector='Energy', Matched: {len(result)} rows")
print(result.head())
```

For aggregations, sanity-check: total should approximate mean x count.

For ranking queries (highest/lowest), show top 5 to confirm the #1 result.

### 5. Handle ambiguity
When "how many" or "total" could mean different things (count of distinct items vs. sum of a quantity vs. number of rows), state your interpretation and report both if genuinely ambiguous.

### 6. Always complete your answer
State what you found AND what you could not find:

> "The total revenue for Q3 is $X (from column 'Revenue', rows 45-67). The data does not contain Q4."

Never end with incomplete thoughts like "Let me check..." or "I will now search...".

## Multi-file analysis

When working with multiple CSV files, run `python /app/skills/analyzing-csv/scripts/preprocess.py` on each file first, then identify common columns for joining before loading data.
