"""
Agentic analysis: Claude decides what to fetch, when to dig deeper,
and synthesizes a risk assessment autonomously via tool use.
"""
import os
import json
from typing import Callable, Optional
from datetime import datetime, timedelta, timezone
from anthropic import Anthropic

from utils.npm import get_package_info as _npm_get_package_info
from utils.github import (
    _get_repo, _get_contributors, _get_recent_commits,
    _get_issues_stats, _get_recent_releases,
    _top_contributor_share, _days_since_last_release, _parse_date,
)
from utils.scoring import compute_risk_score as _compute_risk_score


TOOLS = [
    {
        "name": "fetch_npm_metadata",
        "description": (
            "Fetch npm registry metadata for a package: description, latest version, "
            "license, maintainers list, and the resolved GitHub repository (owner/repo)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "package_name": {"type": "string", "description": "npm package name"}
            },
            "required": ["package_name"],
        },
    },
    {
        "name": "fetch_github_repo",
        "description": (
            "Fetch basic GitHub repository info: stars, forks, open issue count, "
            "archived status, license, creation date, last push date."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "owner_repo": {"type": "string", "description": "GitHub repo as 'owner/repo'"}
            },
            "required": ["owner_repo"],
        },
    },
    {
        "name": "fetch_contributors",
        "description": (
            "Fetch contributor list with commit counts. Use to assess how concentrated "
            "the contributor base is and who the top maintainers are."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "owner_repo": {"type": "string", "description": "GitHub repo as 'owner/repo'"}
            },
            "required": ["owner_repo"],
        },
    },
    {
        "name": "fetch_recent_commits",
        "description": (
            "Fetch commits from the last N days. Returns activity metrics: count, "
            "commits/month, active contributors in last 90 days, top contributor %, "
            "and days since last commit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "owner_repo": {"type": "string", "description": "GitHub repo as 'owner/repo'"},
                "days": {"type": "integer", "description": "Days to look back (default 180)"},
            },
            "required": ["owner_repo"],
        },
    },
    {
        "name": "fetch_issues",
        "description": (
            "Fetch issue statistics: open count, closed count, close ratio, "
            "and average first-response time in hours. Indicates maintainer responsiveness."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "owner_repo": {"type": "string", "description": "GitHub repo as 'owner/repo'"}
            },
            "required": ["owner_repo"],
        },
    },
    {
        "name": "fetch_releases",
        "description": (
            "Fetch recent releases from the last year and days since the last release. "
            "Use to assess whether the project ships regularly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "owner_repo": {"type": "string", "description": "GitHub repo as 'owner/repo'"}
            },
            "required": ["owner_repo"],
        },
    },
    {
        "name": "compute_risk_score",
        "description": (
            "Compute the composite Bus Factor risk score from collected signals. "
            "Call this once you have sufficient data. Returns overall score (0-100), "
            "risk level (CRITICAL/WARNING/MODERATE/HEALTHY), emoji, and component breakdowns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "signals": {
                    "type": "object",
                    "description": (
                        "Signals dict with any of: active_contributors_90d, total_contributors, "
                        "top_contributor_pct, days_since_last_commit, commits_per_month_6m, "
                        "open_issue_count, issue_close_ratio, avg_issue_response_hours, "
                        "releases_last_year, days_since_last_release, archived, stars."
                    ),
                }
            },
            "required": ["signals"],
        },
    },
]


SYSTEM_PROMPT = """You are a cybersecurity supply chain risk analyst specializing in open-source dependency risk.

Your goal: assess the Bus Factor risk of an npm package — how likely is it to collapse due to maintainer abandonment, burnout, or compromise?

**Adaptive strategy:**
1. Always start with `fetch_npm_metadata` to resolve the GitHub repo
2. Then `fetch_github_repo` for basic health signals (archived? stars?)
3. Then `fetch_contributors` + `fetch_recent_commits` — these are the most critical signals
4. **If fragile** (≤2 active contributors, declining commits, solo maintainer): also fetch issues and releases
5. **If healthy** (5+ active contributors, regular commits): skip deeper dives — you have enough
6. Call `compute_risk_score` once you have sufficient signals
7. Write a 3-4 sentence risk briefing: be direct, cite specific numbers, name the risk

Do not fetch everything for every package. Use early signals to decide how deep to go."""


# ── Tool implementations ────────────────────────────────────────────────────

def _tool_fetch_npm_metadata(args: dict) -> dict:
    info = _npm_get_package_info(args["package_name"])
    if not info:
        return {"error": f"Package '{args['package_name']}' not found on npm"}
    return {
        "name": info["name"],
        "description": info.get("description", ""),
        "latest_version": info.get("latest_version", ""),
        "license": info.get("license", "unknown"),
        "maintainers": info.get("maintainers", []),
        "repository": info.get("repository"),
    }


def _tool_fetch_github_repo(args: dict) -> dict:
    repo = _get_repo(args["owner_repo"])
    if not repo:
        return {"error": f"Could not fetch repo '{args['owner_repo']}'"}
    return {
        "stars": repo.get("stargazers_count", 0),
        "forks": repo.get("forks_count", 0),
        "open_issues": repo.get("open_issues_count", 0),
        "archived": repo.get("archived", False),
        "license": (repo.get("license") or {}).get("spdx_id", "unknown"),
        "created_at": repo.get("created_at", ""),
        "pushed_at": repo.get("pushed_at", ""),
    }


def _tool_fetch_contributors(args: dict) -> dict:
    contributors = _get_contributors(args["owner_repo"])
    if not contributors:
        return {"total": 0, "top_contributor_pct": 0, "top_10": []}
    total_commits = sum(c.get("contributions", 0) for c in contributors)
    top = contributors[0]
    top_pct = round(top.get("contributions", 0) / total_commits * 100, 1) if total_commits > 0 else 0
    return {
        "total": len(contributors),
        "top_contributor": top.get("login", ""),
        "top_contributor_commits": top.get("contributions", 0),
        "top_contributor_pct": top_pct,
        "top_10": [{"login": c.get("login"), "commits": c.get("contributions")} for c in contributors[:10]],
    }


def _tool_fetch_recent_commits(args: dict) -> dict:
    days = args.get("days", 180)
    commits = _get_recent_commits(args["owner_repo"], days=days)
    if not commits:
        return {"count": 0, "commits_per_month": 0, "active_contributors_90d": 0,
                "top_contributor_pct": 0, "days_since_last_commit": 999}
    now = datetime.now(timezone.utc)
    cutoff_90 = now - timedelta(days=90)
    active_90 = len(set(
        c["author"] for c in commits
        if c["author"] and _parse_date(c["date"]) and _parse_date(c["date"]) > cutoff_90
    ))
    last_date = _parse_date(commits[0]["date"])
    days_since = (now - last_date).days if last_date else 999
    return {
        "count": len(commits),
        "commits_per_month": round(len(commits) / (days / 30), 1),
        "active_contributors_90d": active_90,
        "top_contributor_pct": _top_contributor_share(commits),
        "days_since_last_commit": days_since,
        "most_recent_commit": commits[0]["date"] if commits else None,
        "sample_authors": list({c["author"] for c in commits[:20] if c["author"]})[:8],
    }


def _tool_fetch_issues(args: dict) -> dict:
    return _get_issues_stats(args["owner_repo"])


def _tool_fetch_releases(args: dict) -> dict:
    releases = _get_recent_releases(args["owner_repo"])
    return {
        "releases_last_year": len(releases),
        "days_since_last_release": _days_since_last_release(releases),
        "recent_tags": [r["name"] for r in releases[:5]],
    }


TOOL_HANDLERS = {
    "fetch_npm_metadata": _tool_fetch_npm_metadata,
    "fetch_github_repo": _tool_fetch_github_repo,
    "fetch_contributors": _tool_fetch_contributors,
    "fetch_recent_commits": _tool_fetch_recent_commits,
    "fetch_issues": _tool_fetch_issues,
    "fetch_releases": _tool_fetch_releases,
}


def _merge_signals(tool_name: str, result: dict, signals: dict):
    """Merge tool result into running signals dict for compute_risk_score."""
    if "error" in result:
        return
    if tool_name == "fetch_npm_metadata":
        signals["npm_maintainers"] = result.get("maintainers", [])
        signals.setdefault("owner_repo", result.get("repository", ""))
        signals["_npm_info"] = result
    elif tool_name == "fetch_github_repo":
        signals["stars"] = result.get("stars", 0)
        signals["open_issue_count"] = result.get("open_issues", 0)
        signals["archived"] = result.get("archived", False)
        signals["license"] = result.get("license", "unknown")
    elif tool_name == "fetch_contributors":
        signals["total_contributors"] = result.get("total", 0)
        signals["top_contributor_pct"] = result.get("top_contributor_pct", 0)
    elif tool_name == "fetch_recent_commits":
        signals["commits_per_month_6m"] = result.get("commits_per_month", 0)
        signals["active_contributors_90d"] = result.get("active_contributors_90d", 0)
        signals["days_since_last_commit"] = result.get("days_since_last_commit", 999)
        signals.setdefault("top_contributor_pct", result.get("top_contributor_pct", 0))
    elif tool_name == "fetch_issues":
        signals["open_issue_count"] = result.get("open", 0)
        signals["closed_issue_count"] = result.get("closed", 0)
        signals["issue_close_ratio"] = result.get("close_ratio", 0)
        signals["avg_issue_response_hours"] = result.get("avg_response_hours", 0)
    elif tool_name == "fetch_releases":
        signals["releases_last_year"] = result.get("releases_last_year", 0)
        signals["days_since_last_release"] = result.get("days_since_last_release", 999)


# ── Main agent loop ─────────────────────────────────────────────────────────

def run_agent(
    package_name: str,
    on_tool_call: Optional[Callable[[str, dict], None]] = None,
) -> dict:
    """
    Run the agentic analysis loop for a single npm package.

    Claude autonomously decides which tools to call and in what order.
    on_tool_call: optional callback(tool_name, tool_input) fired before each execution.

    Returns dict with: package, repo, steps, briefing, signals, risk, npm_info
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set — agentic mode requires the Claude API."}

    client = Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": f"Analyze supply chain risk for npm package: **{package_name}**"}]
    collected_signals: dict = {}
    steps: list = []
    final_text = ""

    for _ in range(15):  # safety cap on iterations
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            final_text = next((b.text for b in response.content if hasattr(b, "text")), "")
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if on_tool_call:
                    on_tool_call(block.name, block.input)

                if block.name == "compute_risk_score":
                    merged = {**collected_signals, **block.input.get("signals", {})}
                    result = _compute_risk_score(merged)
                    collected_signals["_risk_score"] = result
                else:
                    handler = TOOL_HANDLERS.get(block.name)
                    result = handler(block.input) if handler else {"error": f"Unknown tool: {block.name}"}
                    _merge_signals(block.name, result, collected_signals)

                steps.append({"tool": block.name, "input": block.input, "result": result})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })
            messages.append({"role": "user", "content": tool_results})

    return {
        "package": package_name,
        "repo": collected_signals.get("owner_repo", ""),
        "steps": steps,
        "briefing": final_text,
        "signals": collected_signals,
        "risk": collected_signals.get("_risk_score"),
        "npm_info": collected_signals.get("_npm_info", {}),
    }
