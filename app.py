"""
Bus Factor — Predict open-source project collapse before it happens.
"""
import json
import time
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from dotenv import load_dotenv

from utils.npm import get_package_info, parse_package_json
from utils.github import get_repo_signals
from utils.scoring import compute_risk_score
from utils.briefing import generate_briefing, generate_overall_summary
from utils.agent import run_agent

load_dotenv()

st.set_page_config(
    page_title="Bus Factor",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Theme state ──────────────────────────────────────────────────────────────
if "theme" not in st.session_state:
    st.session_state["theme"] = "dark"

DARK = dict(
    bg="#0b0d14", surface="#12151f", surface2="#1a1e2e",
    text="#e2e8f0", text2="#94a3b8", text3="#64748b",
    border="#1e2235", border2="#252840",
    accent="#6366f1", accent_soft="rgba(99,102,241,0.12)",
    accent_border="rgba(99,102,241,0.28)",
    paper_bg="#0b0d14", plot_bg="#12151f", grid="#1e2235",
    shadow="0 4px 28px rgba(0,0,0,0.55)",
    hover_shadow="0 8px 36px rgba(99,102,241,0.18)",
    input_bg="#12151f",
)
LIGHT = dict(
    bg="#f0f4f9", surface="#ffffff", surface2="#f8fafc",
    text="#0f172a", text2="#475569", text3="#94a3b8",
    border="#e2e8f0", border2="#cbd5e1",
    accent="#6366f1", accent_soft="rgba(99,102,241,0.07)",
    accent_border="rgba(99,102,241,0.22)",
    paper_bg="#ffffff", plot_bg="#f8fafc", grid="#e2e8f0",
    shadow="0 4px 28px rgba(0,0,0,0.07)",
    hover_shadow="0 8px 36px rgba(99,102,241,0.14)",
    input_bg="#f8fafc",
)

T = DARK if st.session_state["theme"] == "dark" else LIGHT
is_dark = st.session_state["theme"] == "dark"


def inject_css():
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ── Base ───────────────────────────────────── */
.stApp {{ background: {T['bg']}; font-family: 'Inter', sans-serif; }}
#MainMenu, footer {{ visibility: hidden; }}
.block-container {{ padding: 2rem 3rem 5rem; max-width: 1440px; }}

/* ── Global text ────────────────────────────── */
.stApp, .stMarkdown p, .stText, label, span,
div[data-testid="stMarkdownContainer"] p {{ color: {T['text']}; }}
h1, h2, h3, h4 {{ color: {T['text']}; font-family: 'Inter', sans-serif; letter-spacing: -0.025em; }}

/* ── Divider ────────────────────────────────── */
hr {{ border-color: {T['border']}; opacity: 1; margin: 1.5rem 0; }}

/* ── Metrics ────────────────────────────────── */
div[data-testid="stMetric"] {{
    background: {T['surface']};
    border: 1px solid {T['border']};
    border-radius: 14px;
    padding: 18px 22px;
    box-shadow: {T['shadow']};
    transition: transform 0.18s ease, box-shadow 0.18s ease;
}}
div[data-testid="stMetric"]:hover {{
    transform: translateY(-2px);
    box-shadow: {T['hover_shadow']};
}}
div[data-testid="stMetric"] label {{
    color: {T['text2']} !important;
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.09em !important;
    text-transform: uppercase !important;
}}
div[data-testid="stMetricValue"] {{
    color: {T['text']} !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.55rem !important;
    font-weight: 600 !important;
}}
div[data-testid="stMetricDelta"] {{ font-size: 0.75rem !important; }}

/* ── Buttons ────────────────────────────────── */
.stButton > button {{
    background: linear-gradient(135deg, {T['accent']} 0%, #818cf8 100%);
    color: #fff !important;
    border: none;
    border-radius: 10px;
    padding: 11px 26px;
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    font-size: 0.88rem;
    letter-spacing: 0.025em;
    transition: all 0.18s ease;
    box-shadow: 0 4px 14px rgba(99,102,241,0.35);
}}
.stButton > button:hover {{
    transform: translateY(-1px);
    box-shadow: 0 6px 22px rgba(99,102,241,0.48) !important;
    opacity: 0.94;
    border: none !important;
}}
.stButton > button:active {{ transform: translateY(0); }}
.stButton > button[kind="secondary"] {{
    background: {T['surface']} !important;
    color: {T['text']} !important;
    border: 1px solid {T['border']} !important;
    box-shadow: none !important;
}}
.stButton > button[kind="secondary"]:hover {{
    border-color: {T['accent']} !important;
    box-shadow: none !important;
    opacity: 1;
}}

/* ── Inputs ─────────────────────────────────── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {{
    background: {T['input_bg']} !important;
    border: 1px solid {T['border']} !important;
    border-radius: 10px !important;
    color: {T['text']} !important;
    font-family: 'Inter', sans-serif;
    font-size: 0.9rem;
    padding: 10px 14px;
    transition: border-color 0.15s, box-shadow 0.15s;
}}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {{
    border-color: {T['accent']} !important;
    box-shadow: 0 0 0 3px {T['accent_soft']} !important;
}}
.stTextInput label, .stTextArea label {{
    color: {T['text2']} !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
}}

/* ── Selectbox ──────────────────────────────── */
.stSelectbox > div > div > div {{
    background: {T['input_bg']} !important;
    border: 1px solid {T['border']} !important;
    border-radius: 10px !important;
    color: {T['text']} !important;
}}
.stSelectbox label {{
    color: {T['text2']} !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
}}

/* ── Radio ──────────────────────────────────── */
.stRadio > div {{
    background: {T['surface']};
    border: 1px solid {T['border']};
    border-radius: 10px;
    padding: 10px 16px;
    gap: 8px;
}}
.stRadio label {{ color: {T['text']} !important; font-size: 0.9rem !important; }}

/* ── Dataframe ──────────────────────────────── */
.stDataFrame {{
    border-radius: 14px !important;
    overflow: hidden;
    border: 1px solid {T['border']} !important;
    box-shadow: {T['shadow']};
}}
.stDataFrame thead tr th {{
    background: {T['surface2']} !important;
    color: {T['text2']} !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    border-bottom: 1px solid {T['border']} !important;
}}
.stDataFrame tbody tr td {{
    background: {T['surface']} !important;
    color: {T['text']} !important;
    border-bottom: 1px solid {T['border']} !important;
    font-size: 0.875rem !important;
}}
.stDataFrame tbody tr:hover td {{ background: {T['surface2']} !important; }}

/* ── Progress bar ───────────────────────────── */
.stProgress > div > div > div > div {{
    background: linear-gradient(90deg, {T['accent']}, #818cf8) !important;
    border-radius: 4px;
}}
.stProgress > div > div > div {{
    background: {T['border']} !important;
    border-radius: 4px;
}}

/* ── Spinner ────────────────────────────────── */
.stSpinner > div > div {{ border-top-color: {T['accent']} !important; }}

/* ── Alerts ─────────────────────────────────── */
.stAlert {{ border-radius: 10px !important; }}
.stSuccess {{ background: rgba(16,185,129,0.08) !important; border-color: rgba(16,185,129,0.25) !important; }}
.stWarning {{ background: rgba(245,158,11,0.08) !important; border-color: rgba(245,158,11,0.25) !important; }}
.stError   {{ background: rgba(239,68,68,0.08)  !important; border-color: rgba(239,68,68,0.25)  !important; }}

/* ── Custom components ──────────────────────── */
.hero-badge {{
    display: inline-flex; align-items: center; gap: 6px;
    background: {T['accent_soft']};
    border: 1px solid {T['accent_border']};
    color: #818cf8;
    padding: 4px 14px; border-radius: 100px;
    font-size: 0.72rem; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase;
    margin-bottom: 14px;
}}

.page-title {{
    font-size: 2.8rem; font-weight: 700;
    color: {T['text']}; letter-spacing: -0.035em; line-height: 1.1; margin: 0;
}}
.page-subtitle {{
    font-size: 0.95rem; color: {T['text2']}; margin-top: 10px; font-weight: 400;
}}

.section-label {{
    font-size: 0.7rem; font-weight: 700;
    color: {T['text3']}; letter-spacing: 0.1em;
    text-transform: uppercase; margin-bottom: 12px;
}}

.briefing-card {{
    background: {T['accent_soft']};
    border: 1px solid {T['accent_border']};
    border-left: 3px solid {T['accent']};
    border-radius: 0 14px 14px 0;
    padding: 20px 24px;
    color: {T['text2']};
    font-size: 0.9rem; line-height: 1.75;
}}
.briefing-label {{
    font-size: 0.7rem; font-weight: 700;
    color: {T['accent']}; letter-spacing: 0.1em;
    text-transform: uppercase;
}}

.stat-table {{ width: 100%; border-collapse: collapse; }}
.stat-table tr td {{
    padding: 9px 0;
    border-bottom: 1px solid {T['border']};
    font-size: 0.875rem;
}}
.stat-table tr:last-child td {{ border-bottom: none; }}
.stat-table .stat-label {{ color: {T['text2']}; padding-right: 16px; }}
.stat-table .stat-value {{
    color: {T['text']};
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500; text-align: right;
}}

.risk-pill {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 12px; border-radius: 100px;
    font-size: 0.75rem; font-weight: 700; letter-spacing: 0.06em;
}}
.pill-critical {{ background: rgba(239,68,68,0.1);  color: #ef4444; border: 1px solid rgba(239,68,68,0.25); }}
.pill-warning  {{ background: rgba(245,158,11,0.1); color: #f59e0b; border: 1px solid rgba(245,158,11,0.25); }}
.pill-moderate {{ background: rgba(234,179,8,0.1);  color: #ca8a04; border: 1px solid rgba(234,179,8,0.25); }}
.pill-healthy  {{ background: rgba(16,185,129,0.1); color: #10b981; border: 1px solid rgba(16,185,129,0.25); }}

.signal-pill {{
    display: inline-flex; align-items: center;
    background: rgba(239,68,68,0.07);
    color: #ef4444;
    border: 1px solid rgba(239,68,68,0.18);
    padding: 3px 12px; border-radius: 100px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem; font-weight: 500; margin: 3px;
}}

.pkg-header {{
    background: {T['surface']};
    border: 1px solid {T['border']};
    border-radius: 16px; padding: 24px 28px;
    box-shadow: {T['shadow']};
    margin-bottom: 20px;
}}

.score-big {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 3.5rem; font-weight: 700; line-height: 1;
    background: linear-gradient(135deg, {T['accent']}, #818cf8);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
}}

.info-card {{
    background: {T['surface']};
    border: 1px solid {T['border']};
    border-radius: 14px; padding: 20px 22px;
    box-shadow: {T['shadow']};
}}
.info-card-title {{
    font-size: 0.72rem; font-weight: 700;
    color: {T['text3']}; letter-spacing: 0.1em;
    text-transform: uppercase; margin-bottom: 14px;
}}

.input-card {{
    background: {T['surface']};
    border: 1px solid {T['border']};
    border-radius: 16px; padding: 28px 32px;
    box-shadow: {T['shadow']};
    margin-top: 8px;
}}

/* Plotly chart container */
.js-plotly-plot .plotly {{ border-radius: 14px; overflow: hidden; }}
</style>
""", unsafe_allow_html=True)


def pill(level: str) -> str:
    cls = f"pill-{level.lower()}"
    icons = {"CRITICAL": "🔴", "WARNING": "🟠", "MODERATE": "🟡", "HEALTHY": "🟢"}
    return f'<span class="risk-pill {cls}">{icons.get(level,"")} {level}</span>'


def make_bar_chart(results):
    colors = [
        "#ef4444" if r["risk"]["level"] == "CRITICAL"
        else "#f59e0b" if r["risk"]["level"] == "WARNING"
        else "#eab308" if r["risk"]["level"] == "MODERATE"
        else "#10b981"
        for r in results
    ]
    fig = go.Figure(go.Bar(
        x=[r["name"] for r in results],
        y=[r["risk"]["overall_score"] for r in results],
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{r['risk']['overall_score']}" for r in results],
        textposition="outside",
        textfont=dict(family="JetBrains Mono", size=12, color=T["text2"]),
    ))
    fig.update_layout(
        paper_bgcolor=T["paper_bg"], plot_bgcolor=T["plot_bg"],
        font=dict(color=T["text2"], family="Inter"),
        xaxis=dict(gridcolor=T["grid"], showgrid=False, tickfont=dict(size=11, family="JetBrains Mono")),
        yaxis=dict(gridcolor=T["grid"], range=[0, 115], tickfont=dict(size=11)),
        margin=dict(t=20, b=10, l=10, r=10),
        height=320, bargap=0.35,
    )
    return fig


def make_radar_chart(pkg):
    components = pkg["risk"]["components"]
    categories = list(components.keys())
    values = list(components.values())
    categories_display = [c.replace("_", " ").title() for c in categories]
    categories_display.append(categories_display[0])
    values.append(values[0])

    fig = go.Figure(go.Scatterpolar(
        r=values,
        theta=categories_display,
        fill="toself",
        fillcolor="rgba(99,102,241,0.12)",
        line=dict(color="#6366f1", width=2),
        marker=dict(size=5, color="#6366f1"),
    ))
    fig.update_layout(
        polar=dict(
            bgcolor=T["plot_bg"],
            radialaxis=dict(visible=True, range=[0, 100], gridcolor=T["grid"],
                            color=T["text3"], tickfont=dict(size=9)),
            angularaxis=dict(gridcolor=T["grid"], color=T["text2"],
                             tickfont=dict(size=11, family="Inter")),
        ),
        paper_bgcolor=T["paper_bg"],
        font=dict(color=T["text2"], family="Inter"),
        margin=dict(t=30, b=30, l=40, r=40),
        height=320,
    )
    return fig


def _tool_label(name: str, inp: dict) -> str:
    """Return a clean label for an agent tool call."""
    if name == "fetch_npm_metadata":
        return f"npm registry · `{inp.get('package_name', '')}`"
    if name == "fetch_github_repo":
        return f"github · `{inp.get('owner_repo', '')}`"
    if name == "fetch_contributors":
        return f"contributors · `{inp.get('owner_repo', '')}`"
    if name == "fetch_recent_commits":
        days = inp.get("days", 180)
        return f"commits · last {days}d"
    if name == "fetch_issues":
        return "issue tracker"
    if name == "fetch_releases":
        return "release history"
    if name == "compute_risk_score":
        return "scoring"
    return name


def main():
    inject_css()

    # ── Header ──────────────────────────────────────────────────────────────
    col_title, col_toggle = st.columns([8, 1])
    with col_title:
        st.markdown('<div class="hero-badge">npm · supply chain</div>', unsafe_allow_html=True)
        st.markdown('<div class="page-title">Bus Factor</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="page-subtitle">Dependency risk scoring — identify fragile packages '
            'before they become an incident.</div>',
            unsafe_allow_html=True,
        )
    with col_toggle:
        st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)
        icon = "Light" if is_dark else "Dark"
        if st.button(icon, key="theme_btn", type="secondary"):
            st.session_state["theme"] = "light" if is_dark else "dark"
            st.rerun()

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown("---")

    # ── Input ────────────────────────────────────────────────────────────────
    st.markdown('<div class="input-card">', unsafe_allow_html=True)
    input_method = st.radio(
        "Input method",
        ["Paste package.json", "Enter package names"],
        horizontal=True,
        label_visibility="collapsed",
    )

    packages_to_analyze = []

    if input_method == "Paste package.json":
        pkg_json = st.text_area(
            "package.json contents",
            height=160,
            placeholder='{\n  "dependencies": {\n    "express": "^4.18.0",\n    "lodash": "^4.17.0"\n  }\n}',
            label_visibility="collapsed",
        )
        if pkg_json:
            try:
                parsed = json.loads(pkg_json)
                packages_to_analyze = parse_package_json(parsed)
                st.success(f"✓ Found **{len(packages_to_analyze)}** dependencies")
            except json.JSONDecodeError:
                st.error("Invalid JSON — please paste a valid package.json.")
    else:
        pkg_input = st.text_input(
            "Package names",
            placeholder="express, lodash, chalk, minimist, debug",
            label_visibility="collapsed",
        )
        if pkg_input:
            packages_to_analyze = [p.strip() for p in pkg_input.split(",") if p.strip()]

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    if packages_to_analyze:
        agentic_mode = st.toggle("Deep Analysis", value=False, help="Adaptive investigation — depth scales with what the data reveals")
        if st.button("Run Analysis", type="primary", use_container_width=True):
            results = []
            progress = st.progress(0, text="Initializing...")

            for i, pkg_name in enumerate(packages_to_analyze):
                progress.progress(
                    (i + 1) / len(packages_to_analyze),
                    text=f"Analyzing **{pkg_name}** ({i + 1}/{len(packages_to_analyze)})",
                )

                if agentic_mode:
                    with st.status(f"Analyzing {pkg_name}...", expanded=True) as status:
                        def on_tool_call(name, inp):
                            label = _tool_label(name, inp)
                            st.write(label)
                        result = run_agent(pkg_name, on_tool_call=on_tool_call)
                    if "error" in result:
                        st.error(result["error"])
                        continue
                    if not result.get("risk"):
                        st.warning(f"Agent could not score {pkg_name}, skipping.")
                        continue
                    status.update(label=f"✓ {pkg_name} analyzed", state="complete", expanded=False)
                    results.append({
                        "name": pkg_name,
                        "repo": result["repo"],
                        "npm_info": result.get("npm_info", {}),
                        "signals": result["signals"],
                        "risk": result["risk"],
                        "briefing": result.get("briefing", ""),
                        "agent_steps": result.get("steps", []),
                    })
                else:
                    npm_info = get_package_info(pkg_name)
                    if not npm_info:
                        st.warning(f"Could not find **{pkg_name}** on npm — skipping.")
                        continue
                    repo = npm_info.get("repository")
                    if not repo:
                        st.warning(f"No GitHub repo found for **{pkg_name}** — skipping.")
                        continue
                    signals = get_repo_signals(repo)
                    if not signals:
                        st.warning(f"Could not fetch GitHub data for **{pkg_name}** — skipping.")
                        continue
                    signals["npm_maintainers"] = npm_info.get("maintainers", [])
                    risk = compute_risk_score(signals)
                    results.append({"name": pkg_name, "repo": repo, "npm_info": npm_info, "signals": signals, "risk": risk})
                    time.sleep(0.5)

            progress.empty()

            if not results:
                st.error("No packages could be analyzed. Check your input and API tokens.")
                return
            st.session_state["results"] = results

    # ── Results ──────────────────────────────────────────────────────────────
    if "results" in st.session_state:
        _display_results(st.session_state["results"])


def _display_results(results: list[dict]):
    results.sort(key=lambda r: r["risk"]["overall_score"], reverse=True)

    critical = sum(1 for r in results if r["risk"]["level"] == "CRITICAL")
    warning  = sum(1 for r in results if r["risk"]["level"] == "WARNING")
    moderate = sum(1 for r in results if r["risk"]["level"] == "MODERATE")
    healthy  = sum(1 for r in results if r["risk"]["level"] == "HEALTHY")
    avg_score = round(sum(r["risk"]["overall_score"] for r in results) / len(results), 1)

    # ── Summary metrics ──────────────────────────────────────────────────────
    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">Overview</div>', unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Packages", len(results))
    c2.metric("Critical", critical)
    c3.metric("Warning", warning)
    c4.metric("Moderate", moderate)
    c5.metric("Healthy", healthy)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # ── AI Briefing ──────────────────────────────────────────────────────────
    with st.spinner("Generating summary..."):
        summary = generate_overall_summary(results)
    st.markdown(f'<div class="briefing-card"><span class="briefing-label">Executive Summary</span><br><br>{summary}</div>', unsafe_allow_html=True)
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

    # ── Charts ───────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Risk Breakdown</div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown('<div class="info-card"><div class="info-card-title">Risk Score by Package</div>', unsafe_allow_html=True)
        st.plotly_chart(make_bar_chart(results), use_container_width=True, config={"displayModeBar": False})
        st.markdown("</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown(f'<div class="info-card"><div class="info-card-title">Risk Profile — {results[0]["name"]}</div>', unsafe_allow_html=True)
        st.plotly_chart(make_radar_chart(results[0]), use_container_width=True, config={"displayModeBar": False})
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

    # ── Table ─────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Dependency Risk Table</div>', unsafe_allow_html=True)

    table_data = [{
        "Package": r["name"],
        "Score": r["risk"]["overall_score"],
        "Level": r["risk"]["level"],
        "Active Contribs (90d)": r["signals"].get("active_contributors_90d", "?"),
        "Top Contrib %": r["signals"].get("top_contributor_pct", "?"),
        "Days Since Commit": r["signals"].get("days_since_last_commit", "?"),
        "Commits/mo": r["signals"].get("commits_per_month_6m", "?"),
        "Stars": r["signals"].get("stars", 0),
    } for r in results]

    st.dataframe(
        pd.DataFrame(table_data),
        use_container_width=True, hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
        },
    )

    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

    # ── Deep Dive ────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Package Deep Dive</div>', unsafe_allow_html=True)

    selected = st.selectbox(
        "Select package",
        [r["name"] for r in results],
        format_func=lambda n: f"{n}  ·  {next(r['risk']['level'] for r in results if r['name'] == n)}",
        label_visibility="collapsed",
    )
    pkg = next(r for r in results if r["name"] == selected)
    _render_package_detail(pkg)


def _render_package_detail(pkg: dict):
    risk = pkg["risk"]
    signals = pkg["signals"]
    level = risk["level"]

    # Header card
    st.markdown(f"""
<div class="pkg-header">
  <div style="display:flex; align-items:flex-start; justify-content:space-between; flex-wrap:wrap; gap:16px;">
    <div>
      <div style="font-size:1.4rem; font-weight:700; color:{T['text']}; letter-spacing:-0.02em; margin-bottom:8px;">
        {pkg['name']}
      </div>
      <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
        {pill(level)}
        <span style="color:{T['text3']}; font-size:0.8rem; font-family:'JetBrains Mono',monospace;">
          github.com/{pkg['repo']}
        </span>
      </div>
    </div>
    <div style="text-align:right;">
      <div class="score-big">{risk['overall_score']}</div>
      <div style="font-size:0.72rem; color:{T['text3']}; letter-spacing:0.08em; text-transform:uppercase; margin-top:2px;">Risk Score</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # Component scores
    comps = risk["components"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Maintainer Fragility", f"{comps['maintainer_fragility']}/100")
    c2.metric("Activity Decay",       f"{comps['activity_decay']}/100")
    c3.metric("Responsiveness",       f"{comps['responsiveness']}/100")
    c4.metric("Release Health",       f"{comps['release_health']}/100")

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Key findings
    key_signals = risk.get("signals_used", [])
    if key_signals:
        pills_html = "".join(f'<span class="signal-pill">{s}</span>' for s in key_signals)
        st.markdown(f"""
<div style="margin-bottom:20px;">
  <div class="info-card-title" style="margin-bottom:10px;">Findings</div>
  {pills_html}
</div>
""", unsafe_allow_html=True)

    # Signal tables
    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown(f"""
<div class="info-card">
  <div class="info-card-title">Maintainers</div>
  <table class="stat-table">
    <tr><td class="stat-label">Active contributors (90d)</td><td class="stat-value">{signals.get('active_contributors_90d','?')}</td></tr>
    <tr><td class="stat-label">Total contributors</td><td class="stat-value">{signals.get('total_contributors','?')}</td></tr>
    <tr><td class="stat-label">Top contributor share</td><td class="stat-value">{signals.get('top_contributor_pct','?')}%</td></tr>
    <tr><td class="stat-label">npm maintainers</td><td class="stat-value">{len(signals.get('npm_maintainers',[]))}</td></tr>
  </table>
</div>""", unsafe_allow_html=True)

    with col_r:
        st.markdown(f"""
<div class="info-card">
  <div class="info-card-title">Activity</div>
  <table class="stat-table">
    <tr><td class="stat-label">Days since last commit</td><td class="stat-value">{signals.get('days_since_last_commit','?')}</td></tr>
    <tr><td class="stat-label">Commits / month (6m)</td><td class="stat-value">{signals.get('commits_per_month_6m','?')}</td></tr>
    <tr><td class="stat-label">Releases last year</td><td class="stat-value">{signals.get('releases_last_year','?')}</td></tr>
    <tr><td class="stat-label">Issue close ratio</td><td class="stat-value">{signals.get('issue_close_ratio','?')}</td></tr>
  </table>
</div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Briefing
    st.markdown(f'<div class="info-card-title">Assessment</div>', unsafe_allow_html=True)
    if pkg.get("briefing"):
        briefing = pkg["briefing"]
    else:
        with st.spinner("Generating briefing..."):
            briefing = generate_briefing(pkg["name"], signals, risk)
    st.markdown(f'<div class="briefing-card">{briefing}</div>', unsafe_allow_html=True)

    if pkg.get("agent_steps"):
        with st.expander(f"Trace  ·  {len(pkg['agent_steps'])} calls", expanded=False):
            for step in pkg["agent_steps"]:
                label = _tool_label(step["tool"], step["input"])
                st.markdown(f"**{label}**")
                result = step["result"]
                if "error" not in result:
                    clean = {k: v for k, v in result.items() if not k.startswith("_") and k not in ("top_10", "sample_authors", "recent_tags")}
                    st.json(clean)

    st.markdown(
        f"<div style='margin-top:16px; font-size:0.85rem;'><a href='https://github.com/{pkg['repo']}' "
        f"style='color:{T['accent']}; text-decoration:none;' target='_blank'>github.com/{pkg['repo']} →</a></div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
