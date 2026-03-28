"""
Fetch package metadata from the npm registry.
"""
import requests
from typing import Optional


NPM_REGISTRY = "https://registry.npmjs.org"


def get_package_info(package_name: str) -> Optional[dict]:
    """Fetch metadata for a single npm package."""
    try:
        resp = requests.get(f"{NPM_REGISTRY}/{package_name}", timeout=10)
        resp.raise_for_status()
        data = resp.json()

        latest_version = data.get("dist-tags", {}).get("latest", "unknown")
        latest_info = data.get("versions", {}).get(latest_version, {})

        return {
            "name": package_name,
            "description": data.get("description", ""),
            "latest_version": latest_version,
            "license": latest_info.get("license", "unknown"),
            "dependencies": list(latest_info.get("dependencies", {}).keys()),
            "dev_dependencies": list(latest_info.get("devDependencies", {}).keys()),
            "repository": _extract_repo(data),
            "maintainers": [m.get("name", "") for m in data.get("maintainers", [])],
        }
    except Exception as e:
        print(f"Error fetching {package_name}: {e}")
        return None


def parse_package_json(content: dict) -> list[str]:
    """Extract dependency names from a package.json dict."""
    deps = set()
    for field in ["dependencies", "devDependencies"]:
        deps.update(content.get(field, {}).keys())
    return sorted(deps)


def _extract_repo(data: dict) -> Optional[str]:
    """Extract GitHub repo string (owner/repo) from npm metadata."""
    repo = data.get("repository", {})
    if isinstance(repo, dict):
        url = repo.get("url", "")
    elif isinstance(repo, str):
        url = repo
    else:
        return None

    # Normalize GitHub URLs to owner/repo
    for prefix in [
        "https://github.com/",
        "http://github.com/",
        "git+https://github.com/",
        "git+ssh://git@github.com/",
        "git://github.com/",
        "ssh://git@github.com/",
    ]:
        if prefix in url:
            path = url.split(prefix)[-1]
            path = path.replace(".git", "").strip("/")
            parts = path.split("/")
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
    return None
