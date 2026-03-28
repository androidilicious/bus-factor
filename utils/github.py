"""
Fetch repository and contributor signals from GitHub API.
"""
import os
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional

GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    h = {"Accept": "application/vnd.github.v3+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def get_repo_signals(owner_repo: str) -> Optional[dict]:
    """
    Collect all relevant signals for a GitHub repo.
    owner_repo: "owner/repo" string
    """
    try:
        repo = _get_repo(owner_repo)
        if not repo:
            return None

        contributors = _get_contributors(owner_repo)
        recent_commits = _get_recent_commits(owner_repo, days=180)
        issues_stats = _get_issues_stats(owner_repo)
        recent_releases = _get_recent_releases(owner_repo)

        # Calculate derived signals
        now = datetime.now(timezone.utc)
        last_commit_date = _parse_date(recent_commits[0]["date"]) if recent_commits else None
        days_since_last_commit = (now - last_commit_date).days if last_commit_date else 999

        # Commit frequency: commits per month over last 6 months
        commits_per_month = len(recent_commits) / 6.0 if recent_commits else 0

        # Contributor concentration: what % of recent commits come from top contributor
        top_contributor_pct = _top_contributor_share(recent_commits)

        # Active contributors: unique committers in last 90 days
        cutoff_90 = now - timedelta(days=90)
        active_contributors = len(set(
            c["author"] for c in recent_commits
            if c["author"] and _parse_date(c["date"]) > cutoff_90
        ))

        return {
            "owner_repo": owner_repo,
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "open_issues": repo.get("open_issues_count", 0),
            "archived": repo.get("archived", False),
            "last_push": repo.get("pushed_at", ""),
            "created_at": repo.get("created_at", ""),
            "license": (repo.get("license") or {}).get("spdx_id", "unknown"),

            # Contributor signals
            "total_contributors": len(contributors),
            "active_contributors_90d": active_contributors,
            "top_contributor_pct": top_contributor_pct,
            "npm_maintainers": [],  # filled by caller

            # Activity signals
            "days_since_last_commit": days_since_last_commit,
            "commits_per_month_6m": round(commits_per_month, 1),
            "recent_commits_count": len(recent_commits),

            # Issue signals
            "open_issue_count": issues_stats["open"],
            "closed_issue_count": issues_stats["closed"],
            "issue_close_ratio": issues_stats["close_ratio"],
            "avg_issue_response_hours": issues_stats["avg_response_hours"],

            # Release signals
            "releases_last_year": len(recent_releases),
            "days_since_last_release": _days_since_last_release(recent_releases),
        }

    except Exception as e:
        print(f"Error fetching signals for {owner_repo}: {e}")
        return None


def _get_repo(owner_repo: str) -> Optional[dict]:
    resp = requests.get(f"{GITHUB_API}/repos/{owner_repo}", headers=_headers(), timeout=10)
    if resp.status_code == 200:
        return resp.json()
    return None


def _get_contributors(owner_repo: str, max_pages: int = 2) -> list:
    contributors = []
    for page in range(1, max_pages + 1):
        resp = requests.get(
            f"{GITHUB_API}/repos/{owner_repo}/contributors",
            headers=_headers(),
            params={"per_page": 100, "page": page},
            timeout=10,
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        contributors.extend(data)
    return contributors


def _get_recent_commits(owner_repo: str, days: int = 180) -> list:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    commits = []
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner_repo}/commits",
        headers=_headers(),
        params={"since": since, "per_page": 100},
        timeout=10,
    )
    if resp.status_code == 200:
        for c in resp.json():
            commit_data = c.get("commit", {})
            author_info = commit_data.get("author", {})
            commits.append({
                "sha": c.get("sha", "")[:7],
                "author": (c.get("author") or {}).get("login", author_info.get("name", "unknown")),
                "date": author_info.get("date", ""),
                "message": commit_data.get("message", "")[:200],
            })
    return commits


def _get_issues_stats(owner_repo: str) -> dict:
    """Get open/closed issue counts and average response time."""
    stats = {"open": 0, "closed": 0, "close_ratio": 0.0, "avg_response_hours": 0}

    # Open issues
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner_repo}/issues",
        headers=_headers(),
        params={"state": "open", "per_page": 100},
        timeout=10,
    )
    if resp.status_code == 200:
        # Filter out pull requests
        issues = [i for i in resp.json() if "pull_request" not in i]
        stats["open"] = len(issues)

        # Estimate response time from first few issues
        response_times = []
        for issue in issues[:10]:
            created = _parse_date(issue.get("created_at", ""))
            comments = issue.get("comments", 0)
            if created and comments > 0:
                # Fetch first comment time
                comments_resp = requests.get(
                    issue.get("comments_url", ""),
                    headers=_headers(),
                    params={"per_page": 1},
                    timeout=10,
                )
                if comments_resp.status_code == 200:
                    comment_data = comments_resp.json()
                    if comment_data:
                        first_comment = _parse_date(comment_data[0].get("created_at", ""))
                        if first_comment:
                            delta = (first_comment - created).total_seconds() / 3600
                            response_times.append(delta)

        if response_times:
            stats["avg_response_hours"] = round(sum(response_times) / len(response_times), 1)

    # Closed issues (just count)
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner_repo}/issues",
        headers=_headers(),
        params={"state": "closed", "per_page": 1},
        timeout=10,
    )
    if resp.status_code == 200:
        # Use Link header to get total count
        link = resp.headers.get("Link", "")
        if 'rel="last"' in link:
            import re
            match = re.search(r'page=(\d+)>; rel="last"', link)
            if match:
                stats["closed"] = int(match.group(1))
        else:
            stats["closed"] = len(resp.json())

    total = stats["open"] + stats["closed"]
    stats["close_ratio"] = round(stats["closed"] / total, 2) if total > 0 else 0

    return stats


def _get_recent_releases(owner_repo: str) -> list:
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner_repo}/releases",
        headers=_headers(),
        params={"per_page": 20},
        timeout=10,
    )
    if resp.status_code == 200:
        now = datetime.now(timezone.utc)
        one_year_ago = now - timedelta(days=365)
        releases = []
        for r in resp.json():
            pub = _parse_date(r.get("published_at", ""))
            if pub and pub > one_year_ago:
                releases.append({"date": r["published_at"], "name": r.get("tag_name", "")})
        return releases
    return []


def _parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def _top_contributor_share(commits: list) -> float:
    if not commits:
        return 0.0
    from collections import Counter
    authors = Counter(c["author"] for c in commits if c["author"])
    if not authors:
        return 0.0
    top_count = authors.most_common(1)[0][1]
    return round(top_count / len(commits) * 100, 1)


def _days_since_last_release(releases: list) -> int:
    if not releases:
        return 999
    latest = _parse_date(releases[0]["date"])
    if latest:
        return (datetime.now(timezone.utc) - latest).days
    return 999
