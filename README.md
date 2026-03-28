# Bus Factor

Dependency risk scoring for npm. Identify fragile packages before they become an incident.

---

## Background

The bus factor of a project is the minimum number of contributors whose loss would stall or kill it. A bus factor of 1 means one person holds everything — if they quit, burn out, or get hit by a bus, the project is effectively over.

Most teams have no idea which of their dependencies are at bus factor 1 until something breaks. This tool makes that visible.

Real examples: left-pad (1 maintainer, rage-quit), event-stream (maintainer handed over to a stranger, backdoor inserted), XZ Utils (sole maintainer burned out, social-engineered), colors.js (author intentionally corrupted it).

---

## What It Does

Give it a `package.json` or a list of package names. For each dependency it:

1. Resolves the GitHub repository from npm metadata
2. Collects signals from the GitHub API — contributor concentration, commit trends, issue responsiveness, release cadence
3. Computes a **Risk Score** from 0–100
4. Generates a plain-English assessment

Results are ranked by risk with a per-package deep dive showing the raw signals behind each score.

---

## Risk Scoring

Four components, weighted by impact:

| Component | Weight | Signals |
|---|---|---|
| Maintainer Fragility | 40% | Active contributors (90d), top contributor %, total contributor pool |
| Activity Decay | 25% | Days since last commit, commits/month trend, archived status |
| Responsiveness | 20% | Issue close ratio, average first-response time, open backlog |
| Release Health | 15% | Releases in the last year, days since last release |

Score thresholds: **Critical** ≥ 70 · **Warning** ≥ 45 · **Moderate** ≥ 25 · **Healthy** < 25

---

## Analysis Modes

**Standard** — deterministic pipeline. npm registry → GitHub API → scoring → assessment. Fast and predictable, same depth for every package.

**Deep Analysis** — adaptive. An agent loop decides what to fetch and how deep to investigate based on what the data shows. A well-maintained package with 50 active contributors gets a quick pass. A solo-maintained package with a declining commit trend triggers a full investigation into issues, releases, and response patterns before scoring.

---

## Setup

**Requirements:** Python 3.9+, a GitHub token, an Anthropic API key (for assessments and Deep Analysis).

```bash
git clone https://github.com/androidilicious/bus-factor.git
cd bus-factor
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```
GITHUB_TOKEN=...        # github.com/settings/tokens → classic → public_repo scope
ANTHROPIC_API_KEY=...   # console.anthropic.com
```

```bash
python -m streamlit run app.py
```

---

## Project Structure

```
bus-factor/
├── app.py              # Streamlit UI
├── utils/
│   ├── npm.py          # npm registry client
│   ├── github.py       # GitHub API — signals collection
│   ├── scoring.py      # Risk scoring engine
│   ├── briefing.py     # Assessment generation
│   └── agent.py        # Deep Analysis agent loop
├── requirements.txt
└── .env.example
```

---

## Roadmap

- [ ] PyPI / pip support
- [ ] Transitive dependency analysis (score the full tree, not just direct deps)
- [ ] Maintainer communication patterns (tone, frequency, frustration signals)
- [ ] Social engineering detection (XZ Utils pattern recognition)
- [ ] Historical score tracking and drift alerts
- [ ] Slack / email alerts on threshold crossings
- [ ] Dependency graph visualization

---

## License

MIT
