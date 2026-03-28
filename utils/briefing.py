"""
Generate plain-English risk briefings using Claude API.
"""
import os
import json
from anthropic import Anthropic


def generate_briefing(package_name: str, signals: dict, risk_score: dict) -> str:
    """
    Generate a concise, plain-English risk briefing for a package.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _fallback_briefing(package_name, signals, risk_score)

    client = Anthropic(api_key=api_key)

    prompt = f"""You are a cybersecurity supply chain risk analyst. Generate a concise 3-4 sentence risk briefing for this open-source package.

Package: {package_name}
Risk Level: {risk_score['level']} (Score: {risk_score['overall_score']}/100)

Signals:
- Active contributors (last 90 days): {signals.get('active_contributors_90d', 'unknown')}
- Total contributors: {signals.get('total_contributors', 'unknown')}
- Top contributor share: {signals.get('top_contributor_pct', 'unknown')}%
- Days since last commit: {signals.get('days_since_last_commit', 'unknown')}
- Commits per month (6m avg): {signals.get('commits_per_month_6m', 'unknown')}
- Open issues: {signals.get('open_issue_count', 'unknown')}
- Issue close ratio: {signals.get('issue_close_ratio', 'unknown')}
- Avg issue response time: {signals.get('avg_issue_response_hours', 'unknown')} hours
- Releases in last year: {signals.get('releases_last_year', 'unknown')}
- Stars: {signals.get('stars', 'unknown')}
- Archived: {signals.get('archived', False)}

Key findings: {json.dumps(risk_score.get('signals_used', []))}

Score breakdown:
- Maintainer Fragility: {risk_score['components'].get('maintainer_fragility', 0)}/100
- Activity Decay: {risk_score['components'].get('activity_decay', 0)}/100
- Responsiveness: {risk_score['components'].get('responsiveness', 0)}/100
- Release Health: {risk_score['components'].get('release_health', 0)}/100

Write a brief, direct risk assessment. Be specific about the dangers. No headers or bullet points — just a short paragraph a CTO could read in 15 seconds."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        print(f"Claude API error: {e}")
        return _fallback_briefing(package_name, signals, risk_score)


def generate_overall_summary(results: list[dict]) -> str:
    """
    Generate an overall summary across all analyzed packages.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _fallback_overall(results)

    critical = [r for r in results if r["risk"]["level"] == "CRITICAL"]
    warning = [r for r in results if r["risk"]["level"] == "WARNING"]

    summary_data = {
        "total_packages": len(results),
        "critical": [{"name": r["name"], "score": r["risk"]["overall_score"]} for r in critical],
        "warning": [{"name": r["name"], "score": r["risk"]["overall_score"]} for r in warning],
    }

    client = Anthropic(api_key=api_key)

    prompt = f"""You are a cybersecurity supply chain risk analyst. Write a 3-4 sentence executive summary of this dependency audit.

{json.dumps(summary_data, indent=2)}

Be direct and specific. Mention the most critical packages by name. This should read like a briefing a CTO gets in their morning email."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        print(f"Claude API error: {e}")
        return _fallback_overall(results)


def _fallback_briefing(name: str, signals: dict, risk: dict) -> str:
    """Fallback if Claude API is unavailable."""
    active = signals.get("active_contributors_90d", 0)
    days = signals.get("days_since_last_commit", 0)
    score = risk["overall_score"]
    level = risk["level"]

    return (
        f"{name} has a {level} risk score of {score}/100. "
        f"The project has {active} active contributor(s) in the last 90 days "
        f"and the last commit was {days} days ago. "
        f"{'This package requires immediate attention.' if level == 'CRITICAL' else 'Monitor this package closely.'}"
    )


def _fallback_overall(results: list[dict]) -> str:
    """Fallback overall summary."""
    critical = sum(1 for r in results if r["risk"]["level"] == "CRITICAL")
    warning = sum(1 for r in results if r["risk"]["level"] == "WARNING")
    return (
        f"Analyzed {len(results)} dependencies. "
        f"Found {critical} critical and {warning} warning-level risks. "
        f"{'Immediate action recommended.' if critical > 0 else 'No critical risks found.'}"
    )
