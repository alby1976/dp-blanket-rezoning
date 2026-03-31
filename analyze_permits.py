import csv
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://data.calgary.ca/api/v3/views/6933-unw5/query.json"
PAGE_SIZE = 1000
DATA_START_DATE = "2021-01-01"
POLICY_DATE = "2024-08-06"

SELECT_COLS = [
    "permitnum",
    "category",
    "description",
    "proposedusecode",
    "proposedusedescription",
    "landusedistrict",
    "landusedistrictdescription",
    "statuscurrent",
    "applieddate",
    "decision",
    "decisiondate",
    "releasedate",
    "sdabnumber",
    "sdabdecision",
    "communityname",
    "ward",
    "quadrant",
]

MISSING_MIDDLE_KEYWORDS = [
    "duplex",
    "semi-detached",
    "semi detached",
    "rowhouse",
    "townhouse",
    "triplex",
    "fourplex",
    "4 plex",
    "3 plex",
    "multi-residential",
    "multi residential",
]
RESIDENTIAL_KEYWORDS = ["residential", "dwelling", "house", "suite", "apartment"]

POLICY_SPLIT = datetime.fromisoformat(f"{POLICY_DATE}T00:00:00+00:00")


def fetch_page(offset: int, app_token: str | None = None) -> list[dict]:
    sql = (
        "SELECT "
        + ", ".join(f"`{c}`" for c in SELECT_COLS)
        + f" WHERE `applieddate` >= '{DATA_START_DATE}T00:00:00'"
        + " ORDER BY `applieddate` ASC, `permitnum` ASC"
        + f" LIMIT {PAGE_SIZE} OFFSET {offset}"
    )
    req = Request(f"{BASE_URL}?{urlencode({'query': sql})}")
    if app_token:
        req.add_header("X-App-Token", app_token)
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8")).get("data", [])


def fetch_all(app_token: str | None = None) -> list[dict]:
    offset = 0
    all_rows: list[dict] = []
    while True:
        rows = fetch_page(offset, app_token=app_token)
        if not rows:
            break
        all_rows.extend(rows)
        print(f"Fetched {len(rows)} rows (total={len(all_rows)})")
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return all_rows


def parse_dt(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def contains_any(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


def is_missing_middle(row: dict) -> bool:
    text = f"{row.get('proposedusedescription', '')} {row.get('description', '')}".lower()
    return contains_any(text, MISSING_MIDDLE_KEYWORDS)


def is_residential(row: dict) -> bool:
    category = str(row.get("category") or "").lower()
    text = f"{row.get('proposedusedescription', '')} {row.get('description', '')}".lower()
    return "residential" in category or contains_any(text, RESIDENTIAL_KEYWORDS)




def is_approved(row: dict) -> bool:
    decision = str(row.get("decision") or "").strip().lower()
    return decision.startswith("approve") or decision == "approved"

def month_key(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def rezoning_period(dt: datetime) -> str:
    return "before_blanket_rezoning" if dt < POLICY_SPLIT else "after_blanket_rezoning"


def non_negative_days(start: datetime, end: datetime):
    if start is None or end is None:
        return None
    days = (end - start).total_seconds() / 86400
    return round(days, 2) if days >= 0 else None


def has_sdab_number(value: str) -> bool:
    return bool(str(value or "").strip())


def clean_text(value: str, fallback: str = "(blank)") -> str:
    txt = str(value or "").strip()
    return txt if txt else fallback


def write_csv(path: str, rows: list[dict], fieldnames: list[str]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def new_stats():
    return {
        "total": 0,
        "residential": 0,
        "missing": 0,
        "decision_days_sum": 0.0,
        "decision_days_count": 0,
        "release_days_sum": 0.0,
        "release_days_count": 0,
        "sdab_count": 0,
        "sdab_decisions": Counter(),
        "approved_count": 0,
        "approval_denominator": 0,
    }


def update_stats(stats: dict, row: dict):
    stats["total"] += 1
    if row["is_residential"]:
        stats["residential"] += 1
    if row["is_missing_middle"]:
        stats["missing"] += 1
    if row["days_to_decision"] is not None:
        stats["decision_days_sum"] += row["days_to_decision"]
        stats["decision_days_count"] += 1
    if row["days_to_release"] is not None:
        stats["release_days_sum"] += row["days_to_release"]
        stats["release_days_count"] += 1
    if row["decision_known"]:
        stats["approval_denominator"] += 1
        if row["is_approved"]:
            stats["approved_count"] += 1
    if row["has_sdab_number"]:
        stats["sdab_count"] += 1
        stats["sdab_decisions"][clean_text(row.get("sdabdecision"), "(no decision text)")] += 1


def summarize_stats(group_name: str, stats: dict) -> dict:
    total = stats["total"]
    residential = stats["residential"]
    missing = stats["missing"]
    decision_count = stats["decision_days_count"]
    release_count = stats["release_days_count"]
    sdab_count = stats["sdab_count"]
    approval_denominator = stats["approval_denominator"]
    approved_count = stats["approved_count"]
    top_sdab, top_sdab_count = ("", 0)
    if stats["sdab_decisions"]:
        top_sdab, top_sdab_count = stats["sdab_decisions"].most_common(1)[0]

    return {
        "group": group_name,
        "total_applications": total,
        "residential_applications": residential,
        "missing_middle_applications": missing,
        "missing_share_of_residential": round(missing / residential, 4) if residential else 0,
        "missing_share_of_all": round(missing / total, 4) if total else 0,
        "avg_days_to_decision": round(stats["decision_days_sum"] / decision_count, 2) if decision_count else "",
        "decision_records_used": decision_count,
        "avg_days_to_release": round(stats["release_days_sum"] / release_count, 2) if release_count else "",
        "release_records_used": release_count,
        "approved_count": approved_count,
        "approval_denominator": approval_denominator,
        "approval_rate": round(approved_count / approval_denominator, 4) if approval_denominator else "",
        "sdab_number_count": sdab_count,
        "sdab_share_of_all": round(sdab_count / total, 4) if total else 0,
        "top_sdab_decision": top_sdab,
        "top_sdab_decision_count": top_sdab_count,
    }


def summarize_period(stats_by_period: dict, period: str) -> dict:
    row = summarize_stats(period, stats_by_period[period])
    row["rezoning_period"] = row.pop("group")
    return row


def to_float(value):
    try:
        if value == "" or value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def diff_metric(after: dict, before: dict, key: str):
    a = to_float(after.get(key))
    b = to_float(before.get(key))
    if a is None or b is None:
        return ""
    return round(a - b, 4)


def pct_change_metric(after: dict, before: dict, key: str):
    a = to_float(after.get(key))
    b = to_float(before.get(key))
    if a is None or b in (None, 0):
        return ""
    return round((a - b) / b, 4)


def build_policy_metrics(period_rows: list[dict]) -> list[dict]:
    by_period = {r["rezoning_period"]: r for r in period_rows}
    before = by_period.get("before_blanket_rezoning")
    after = by_period.get("after_blanket_rezoning")
    if not before or not after:
        return []

    specs = [
        ("missing_middle_share_of_all", "missing_share_of_all"),
        ("missing_middle_share_of_residential", "missing_share_of_residential"),
        ("approval_rate", "approval_rate"),
        ("sdab_share_of_all", "sdab_share_of_all"),
        ("avg_days_to_decision", "avg_days_to_decision"),
        ("avg_days_to_release", "avg_days_to_release"),
    ]

    rows = []
    for label, key in specs:
        rows.append({
            "metric": label,
            "before_value": before.get(key, ""),
            "after_value": after.get(key, ""),
            "absolute_change_after_minus_before": diff_metric(after, before, key),
            "relative_change_after_vs_before": pct_change_metric(after, before, key),
            "desired_direction_template": "define_target",
        })
    return rows




def build_metrics_framework() -> list[dict]:
    return [
        {
            "metric": "missing_middle_share_of_residential",
            "why_it_matters": "Tracks whether missing-middle is becoming a larger portion of residential applications.",
            "desired_direction": "council_defined",
            "example_target_placeholder": "set_target",
            "notes": "Use together with approvals and processing times.",
        },
        {
            "metric": "approval_rate",
            "why_it_matters": "Shows proportion of decided applications that are approved.",
            "desired_direction": "higher_if_goal_is_more_supply",
            "example_target_placeholder": "set_target",
            "notes": "Monitor by ward/community and permit type.",
        },
        {
            "metric": "sdab_share_of_all",
            "why_it_matters": "Indicates dispute/friction levels in permitting outcomes.",
            "desired_direction": "lower_if_goal_is_less_friction",
            "example_target_placeholder": "set_target",
            "notes": "Interpret with SDAB decision mix.",
        },
        {
            "metric": "avg_days_to_decision",
            "why_it_matters": "Captures administrative timeliness to decision.",
            "desired_direction": "lower",
            "example_target_placeholder": "set_target",
            "notes": "Add median/p90 in future versions.",
        },
        {
            "metric": "avg_days_to_release",
            "why_it_matters": "Captures time from application to release.",
            "desired_direction": "lower",
            "example_target_placeholder": "set_target",
            "notes": "Use with approval-rate trends.",
        },
    ]


def main():
    app_token = os.getenv("SOCRATA_APP_TOKEN")
    os.makedirs("outputs", exist_ok=True)
    rows = fetch_all(app_token=app_token)

    cleaned_rows = []
    for row in rows:
        applied_dt = parse_dt(row.get("applieddate"))
        if applied_dt is None:
            continue
        decision_dt = parse_dt(row.get("decisiondate"))
        release_dt = parse_dt(row.get("releasedate"))

        row["applieddate"] = applied_dt.isoformat()
        row["decisiondate"] = decision_dt.isoformat() if decision_dt else ""
        row["releasedate"] = release_dt.isoformat() if release_dt else ""
        row["communityname"] = clean_text(row.get("communityname"), "(unknown community)")
        row["ward"] = clean_text(row.get("ward"), "(unknown ward)")
        row["sdabnumber"] = clean_text(row.get("sdabnumber"), "")
        row["sdabdecision"] = clean_text(row.get("sdabdecision"), "")

        row["is_missing_middle"] = is_missing_middle(row)
        row["is_residential"] = is_residential(row)
        row["month"] = month_key(applied_dt)
        row["rezoning_period"] = rezoning_period(applied_dt)
        row["days_to_decision"] = non_negative_days(applied_dt, decision_dt)
        row["days_to_release"] = non_negative_days(applied_dt, release_dt)
        row["has_sdab_number"] = has_sdab_number(row.get("sdabnumber"))
        row["decision_known"] = bool(str(row.get("decision") or "").strip())
        row["is_approved"] = is_approved(row)

        cleaned_rows.append(row)

    period_stats = defaultdict(new_stats)
    monthly_stats = defaultdict(new_stats)
    community_period_stats = defaultdict(new_stats)
    ward_period_stats = defaultdict(new_stats)
    top_types = Counter()

    for row in cleaned_rows:
        period = row["rezoning_period"]
        month_group = f"{period}:{row['month']}"
        community_group = f"{period}:{row['communityname']}"
        ward_group = f"{period}:{row['ward']}"

        update_stats(period_stats[period], row)
        update_stats(monthly_stats[month_group], row)
        update_stats(community_period_stats[community_group], row)
        update_stats(ward_period_stats[ward_group], row)

        if row["is_missing_middle"]:
            top_types[clean_text(row.get("proposedusedescription"))] += 1

    period_rows = [
        summarize_period(period_stats, "before_blanket_rezoning"),
        summarize_period(period_stats, "after_blanket_rezoning"),
    ]
    policy_metrics_rows = build_policy_metrics(period_rows)
    metrics_framework_rows = build_metrics_framework()

    monthly_rows = []
    for key in sorted(monthly_stats):
        period, month = key.split(":", 1)
        s = summarize_stats(month, monthly_stats[key])
        s["rezoning_period"] = period
        s["month"] = s.pop("group")
        monthly_rows.append(s)

    community_rows = []
    for key in sorted(community_period_stats):
        period, community = key.split(":", 1)
        s = summarize_stats(community, community_period_stats[key])
        s["rezoning_period"] = period
        s["communityname"] = s.pop("group")
        community_rows.append(s)

    ward_rows = []
    for key in sorted(ward_period_stats):
        period, ward = key.split(":", 1)
        s = summarize_stats(ward, ward_period_stats[key])
        s["rezoning_period"] = period
        s["ward"] = s.pop("group")
        ward_rows.append(s)

    top_rows = [{"proposedusedescription": key, "count": value} for key, value in top_types.most_common(20)]

    base_fields = [
        "total_applications",
        "residential_applications",
        "missing_middle_applications",
        "missing_share_of_residential",
        "missing_share_of_all",
        "avg_days_to_decision",
        "decision_records_used",
        "avg_days_to_release",
        "release_records_used",
        "approved_count",
        "approval_denominator",
        "approval_rate",
        "sdab_number_count",
        "sdab_share_of_all",
        "top_sdab_decision",
        "top_sdab_decision_count",
    ]

    write_csv(
        "outputs/permits_2021-01-01_to_present.csv",
        cleaned_rows,
        fieldnames=SELECT_COLS
        + [
            "is_residential",
            "is_missing_middle",
            "month",
            "rezoning_period",
            "days_to_decision",
            "days_to_release",
            "has_sdab_number",
            "decision_known",
            "is_approved",
        ],
    )
    write_csv("outputs/period_summary.csv", period_rows, ["rezoning_period"] + base_fields)
    write_csv("outputs/monthly_summary.csv", monthly_rows, ["rezoning_period", "month"] + base_fields)
    write_csv("outputs/community_summary.csv", community_rows, ["rezoning_period", "communityname"] + base_fields)
    write_csv("outputs/ward_summary.csv", ward_rows, ["rezoning_period", "ward"] + base_fields)
    write_csv("outputs/top_missing_middle_types.csv", top_rows, ["proposedusedescription", "count"])
    write_csv(
        "outputs/policy_metrics_summary.csv",
        policy_metrics_rows,
        [
            "metric",
            "before_value",
            "after_value",
            "absolute_change_after_minus_before",
            "relative_change_after_vs_before",
            "desired_direction_template",
        ],
    )
    write_csv(
        "outputs/policy_metrics_framework.csv",
        metrics_framework_rows,
        [
            "metric",
            "why_it_matters",
            "desired_direction",
            "example_target_placeholder",
            "notes",
        ],
    )

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with open("outputs/analysis_summary.md", "w", encoding="utf-8") as f:
        f.write("# Calgary Development Permit Descriptive Analysis (2021-01-01 to Present)\n\n")
        f.write(f"- Data retrieval date (UTC): {now}\n")
        f.write(f"- Period split date: {POLICY_DATE}\n")
        f.write("- Split rule (descriptive only): before is `< 2024-08-06`, after is `>= 2024-08-06`.\n\n")

        f.write("- Cursory takeaway: these results are descriptive and should be paired with council-defined targets to evaluate policy performance.\n\n")
        f.write("## General descriptive summary by time window\n\n")
        f.write(
            "| rezoning_period | total_applications | residential_applications | missing_middle_applications | approval_rate | avg_days_to_decision | avg_days_to_release | sdab_number_count | top_sdab_decision |\n"
        )
        f.write("|---|---:|---:|---:|---:|---:|---:|---:|---|\n")
        for r in period_rows:
            f.write(
                f"| {r['rezoning_period']} | {r['total_applications']} | {r['residential_applications']} | {r['missing_middle_applications']} | {r['approval_rate']} | {r['avg_days_to_decision']} | {r['avg_days_to_release']} | {r['sdab_number_count']} | {r['top_sdab_decision']} |\n"
            )

        f.write("\n## Community-level analysis (top 20 by total permits)\n\n")
        f.write("| rezoning_period | communityname | total_applications | missing_middle_applications | approval_rate | avg_days_to_decision | avg_days_to_release | sdab_number_count | top_sdab_decision |\n")
        f.write("|---|---|---:|---:|---:|---:|---:|---:|---|\n")
        for r in sorted(community_rows, key=lambda x: x['total_applications'], reverse=True)[:20]:
            f.write(
                f"| {r['rezoning_period']} | {r['communityname']} | {r['total_applications']} | {r['missing_middle_applications']} | {r['approval_rate']} | {r['avg_days_to_decision']} | {r['avg_days_to_release']} | {r['sdab_number_count']} | {r['top_sdab_decision']} |\n"
            )

        f.write("\n## Ward-level analysis\n\n")
        f.write("| rezoning_period | ward | total_applications | missing_middle_applications | approval_rate | avg_days_to_decision | avg_days_to_release | sdab_number_count | top_sdab_decision |\n")
        f.write("|---|---|---:|---:|---:|---:|---:|---:|---|\n")
        for r in sorted(ward_rows, key=lambda x: (x['rezoning_period'], x['ward'])):
            f.write(
                f"| {r['rezoning_period']} | {r['ward']} | {r['total_applications']} | {r['missing_middle_applications']} | {r['approval_rate']} | {r['avg_days_to_decision']} | {r['avg_days_to_release']} | {r['sdab_number_count']} | {r['top_sdab_decision']} |\n"
            )

        f.write("\n## Policy monitoring metrics (before vs after)\n\n")
        f.write("| metric | before_value | after_value | absolute_change_after_minus_before | relative_change_after_vs_before | desired_direction_template |\n")
        f.write("|---|---:|---:|---:|---:|---|\n")
        for r in policy_metrics_rows:
            f.write(
                f"| {r['metric']} | {r['before_value']} | {r['after_value']} | {r['absolute_change_after_minus_before']} | {r['relative_change_after_vs_before']} | {r['desired_direction_template']} |\n"
            )

        f.write("\n## Recommended policy-metric framework (targets to be defined by council)\n\n")
        f.write("| metric | why_it_matters | desired_direction | example_target_placeholder | notes |\n")
        f.write("|---|---|---|---|---|\n")
        for r in metrics_framework_rows:
            f.write(
                f"| {r['metric']} | {r['why_it_matters']} | {r['desired_direction']} | {r['example_target_placeholder']} | {r['notes']} |\n"
            )

        f.write("\n## Top missing-middle proposed use descriptions\n\n")
        f.write("| proposedusedescription | count |\n|---|---:|\n")
        for r in top_rows:
            f.write(f"| {r['proposedusedescription']} | {r['count']} |\n")


if __name__ == "__main__":
    main()
