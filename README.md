# Calgary Blanket Rezoning Permit Analysis

This repository contains a reproducible Python script to analyze City of Calgary development permit applications and compare missing-middle permit activity across two descriptive time windows split at the blanket rezoning date.

## Configuration

Create a local `.env` file in the project root to configure the script:

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

## Permit alerting system idea

A useful extension of this project is a **permit alert system** that notifies a user when a new development permit appears in the City of Calgary open data feed.

### What the alert system would do

- Periodically check the open data source for new permit entries.
- Let the user choose:
  - a **permit type**
  - a **community**
- Send an alert when a new record matches those selections.
- Avoid duplicate alerts by storing the most recently seen records.

### Suggested alert logic

A permit should trigger an alert when all of the following are true:

- it is a new record that has not been processed before
- its permit type matches the user's selected type
- its community matches the user's selected community

### Good notification options

- Email
- SMS
- Slack or Discord
- Push notification
- Local dashboard or browser notification

### Simple implementation approach

A minimal version could use:

- a Python script that polls the dataset on a schedule
- a local state file or SQLite database to remember seen permits
- a small configuration file for user preferences
- email notifications for alerts

### Example user flow

1. User selects a permit type.
2. User selects a community.
3. The watcher checks the dataset every few minutes.
4. A new matching permit appears.
5. The user receives an alert with the permit details.

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
- If Socrata rate limits are encountered, add your app token to a local `.env` file and load it from there.
