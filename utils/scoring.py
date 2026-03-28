"""
Compute Bus Factor risk score from GitHub signals.

Score: 0 (safe) to 100 (critical risk)
"""

def compute_risk_score(signals: dict) -> dict:
    """
    Compute a composite risk score from raw signals.
    Returns dict with overall score and component breakdowns.
    """
    components = {
        "maintainer_fragility": _score_maintainer_fragility(signals),
        "activity_decay": _score_activity_decay(signals),
        "responsiveness": _score_responsiveness(signals),
        "release_health": _score_release_health(signals),
    }

    # Weighted composite
    weights = {
        "maintainer_fragility": 0.40,  # Most important
        "activity_decay": 0.25,
        "responsiveness": 0.20,
        "release_health": 0.15,
    }

    overall = sum(components[k] * weights[k] for k in components)

    # Determine risk level
    if overall >= 70:
        level = "CRITICAL"
        color = "red"
        emoji = "🔴"
    elif overall >= 45:
        level = "WARNING"
        color = "orange"
        emoji = "🟠"
    elif overall >= 25:
        level = "MODERATE"
        color = "yellow"
        emoji = "🟡"
    else:
        level = "HEALTHY"
        color = "green"
        emoji = "🟢"

    return {
        "overall_score": round(overall, 1),
        "level": level,
        "color": color,
        "emoji": emoji,
        "components": {k: round(v, 1) for k, v in components.items()},
        "signals_used": _extract_key_signals(signals),
    }


def _score_maintainer_fragility(s: dict) -> float:
    """
    How fragile is the maintainer base?
    High score = very fragile (bad)
    """
    score = 0.0

    # Active contributors in last 90 days
    active = s.get("active_contributors_90d", 0)
    if active == 0:
        score += 40
    elif active == 1:
        score += 30
    elif active == 2:
        score += 15
    elif active <= 4:
        score += 5

    # Top contributor concentration
    top_pct = s.get("top_contributor_pct", 0)
    if top_pct >= 90:
        score += 35
    elif top_pct >= 75:
        score += 25
    elif top_pct >= 60:
        score += 15
    elif top_pct >= 40:
        score += 5

    # Total contributor pool
    total = s.get("total_contributors", 0)
    if total <= 1:
        score += 25
    elif total <= 3:
        score += 15
    elif total <= 5:
        score += 8

    return min(score, 100)


def _score_activity_decay(s: dict) -> float:
    """
    Is the project losing momentum?
    High score = decaying (bad)
    """
    score = 0.0

    # Days since last commit
    days = s.get("days_since_last_commit", 0)
    if days >= 365:
        score += 50
    elif days >= 180:
        score += 35
    elif days >= 90:
        score += 20
    elif days >= 30:
        score += 10

    # Commits per month (last 6 months)
    cpm = s.get("commits_per_month_6m", 0)
    if cpm == 0:
        score += 30
    elif cpm < 1:
        score += 20
    elif cpm < 3:
        score += 10
    elif cpm < 5:
        score += 5

    # Archived repo
    if s.get("archived", False):
        score += 20

    return min(score, 100)


def _score_responsiveness(s: dict) -> float:
    """
    How well does the project respond to issues?
    High score = unresponsive (bad)
    """
    score = 0.0

    # Issue close ratio
    ratio = s.get("issue_close_ratio", 0)
    if ratio == 0:
        score += 20
    elif ratio < 0.3:
        score += 30
    elif ratio < 0.5:
        score += 20
    elif ratio < 0.7:
        score += 10

    # Average response time
    hours = s.get("avg_issue_response_hours", 0)
    if hours == 0:
        score += 10  # No data, slight penalty
    elif hours >= 720:  # 30 days
        score += 40
    elif hours >= 168:  # 7 days
        score += 25
    elif hours >= 48:
        score += 10

    # Open issue pile-up
    open_issues = s.get("open_issue_count", 0)
    if open_issues >= 500:
        score += 25
    elif open_issues >= 200:
        score += 15
    elif open_issues >= 50:
        score += 5

    return min(score, 100)


def _score_release_health(s: dict) -> float:
    """
    Are releases happening regularly?
    High score = stale releases (bad)
    """
    score = 0.0

    # Releases in last year
    releases = s.get("releases_last_year", 0)
    if releases == 0:
        score += 40
    elif releases == 1:
        score += 25
    elif releases <= 3:
        score += 10

    # Days since last release
    days = s.get("days_since_last_release", 0)
    if days >= 365:
        score += 40
    elif days >= 180:
        score += 25
    elif days >= 90:
        score += 10

    # No license
    if s.get("license", "unknown") == "unknown":
        score += 15

    return min(score, 100)


def _extract_key_signals(s: dict) -> list[str]:
    """Pull out the most notable signals for display."""
    signals = []

    active = s.get("active_contributors_90d", 0)
    if active <= 1:
        signals.append(f"Only {active} active contributor(s) in last 90 days")

    top_pct = s.get("top_contributor_pct", 0)
    if top_pct >= 75:
        signals.append(f"Top contributor responsible for {top_pct}% of recent commits")

    days = s.get("days_since_last_commit", 0)
    if days >= 30:
        signals.append(f"Last commit was {days} days ago")

    cpm = s.get("commits_per_month_6m", 0)
    if cpm < 2:
        signals.append(f"Only {cpm} commits/month over last 6 months")

    hours = s.get("avg_issue_response_hours", 0)
    if hours >= 168:
        signals.append(f"Average issue response time: {round(hours / 24)}+ days")

    if s.get("releases_last_year", 0) == 0:
        signals.append("No releases in the past year")

    if s.get("archived", False):
        signals.append("Repository is archived")

    return signals
