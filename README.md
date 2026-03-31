# Calgary Blanket Rezoning Permit Analysis

This repository contains a reproducible Python script to analyze City of Calgary development permit applications and compare missing-middle permit activity across two descriptive time windows split at the blanket rezoning date.

## Time windows used (descriptive)

Dataset window: `2021-01-01` to present (based on `applieddate`).

To avoid overlap at the split date, the script uses:

- `before_blanket_rezoning`: `2021-01-01 <= applieddate < 2024-08-06`
- `after_blanket_rezoning`: `applieddate >= 2024-08-06`

## What the script does

- Pulls permit records from Calgary Open Data Socrata using `LIMIT` + `OFFSET` pagination.
- Tags records with:
  - `is_residential`: from `category` and residential-use keywords.
  - `is_missing_middle`: from keywords in `proposedusedescription` + `description`.
- Calculates timing metrics:
  - `days_to_decision = decisiondate - applieddate`
  - `days_to_release = releasedate - applieddate`
- Calculates approval metrics:
  - `approval_rate = approved_count / approval_denominator` where denominator is permits with a non-empty `decision`.
- Includes SDAB analysis:
  - `has_sdab_number` (whether `sdabnumber` exists)
  - most common `sdabdecision` in each summary group.
- Produces both:
  - general before/after and monthly summaries
  - grouped summaries by community and ward
- Adds a policy-monitoring scorecard (`policy_metrics_summary.csv`) with before/after values and changes for key metrics:
  - missing-middle shares
  - approval rate
  - SDAB share
  - processing times (decision/release)
- Adds a metrics-framework table (`policy_metrics_framework.csv`) so council can set desired directions and explicit targets before judging policy success/failure.

## Usage

```bash
python3 analyze_permits.py
```

Outputs are written to `outputs/`:

- `permits_2021-01-01_to_present.csv`
- `period_summary.csv`
- `monthly_summary.csv`
- `community_summary.csv`
- `ward_summary.csv`
- `top_missing_middle_types.csv`
- `policy_metrics_summary.csv`
- `policy_metrics_framework.csv`
- `analysis_summary.md`

## Notes

- This workflow is intentionally **descriptive** (counts, shares, averages by period/community/ward).
- It is not intended to estimate causal effects.
- If Socrata rate limits are encountered, run with an app token:

```bash
SOCRATA_APP_TOKEN=your_token_here python3 analyze_permits.py
```
