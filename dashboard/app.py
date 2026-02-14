"""Streamlit dashboard — visualizes incident reports and agent decision traces."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pandas as pd
import streamlit as st

API_BASE = "http://localhost:8000"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEVERITY_COLORS = {
    "critical": "red",
    "high": "orange",
    "medium": "blue",
    "low": "green",
}

AGENT_ICONS = {
    "triage": "🔍",
    "research": "🔬",
    "remediation": "🛠️",
    "orchestrator": "🎯",
}


def _api_get(path: str, **kwargs) -> dict | list | None:
    try:
        r = httpx.get(f"{API_BASE}{path}", timeout=30, **kwargs)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError:
        return None


def _api_post(path: str, payload: dict, **kwargs) -> dict | None:
    try:
        r = httpx.post(f"{API_BASE}{path}", json=payload, timeout=120, **kwargs)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        st.error(f"API error: {e}")
        return None


def _severity_badge(severity: str) -> str:
    color = SEVERITY_COLORS.get(severity, "gray")
    return f":{color}[**{severity.upper()}**]"


def _confidence_color(score: float) -> str:
    if score >= 0.7:
        return "green"
    elif score >= 0.4:
        return "orange"
    return "red"


def _parse_prometheus_metrics(text: str) -> dict[str, list[tuple[dict, float]]]:
    """Parse Prometheus text exposition format into {metric_name: [(labels, value)]}."""
    metrics: dict[str, list[tuple[dict, float]]] = {}
    for line in text.strip().split("\n"):
        if line.startswith("#") or not line.strip():
            continue
        # e.g. sentinel_tool_calls_total{tool_name="get_metrics"} 4.0
        try:
            if "{" in line:
                name_part, rest = line.split("{", 1)
                labels_str, value_str = rest.rsplit("}", 1)
                labels = {}
                for pair in labels_str.split(","):
                    k, v = pair.split("=", 1)
                    labels[k.strip()] = v.strip().strip('"')
                value = float(value_str.strip())
            else:
                parts = line.split()
                name_part = parts[0]
                labels = {}
                value = float(parts[1])
            metrics.setdefault(name_part.strip(), []).append((labels, value))
        except (ValueError, IndexError):
            continue
    return metrics


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Sentinel — DevOps AI Agent",
    page_icon="🛡️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

if "selected_incident_id" not in st.session_state:
    st.session_state.selected_incident_id = None
if "analysis_running" not in st.session_state:
    st.session_state.analysis_running = False
if "last_report" not in st.session_state:
    st.session_state.last_report = None

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🛡️ DevOps AI Agent")
    st.caption("Automated incident analysis")

    st.divider()

    # --- New Analysis Form ---
    st.subheader("New Analysis")
    with st.form("new_analysis_form"):
        svc = st.text_input("Service name", placeholder="e.g. payment-api")
        desc = st.text_area("Description", placeholder="e.g. P99 latency spike to 2s", height=80)
        sev = st.selectbox("Severity", ["critical", "high", "medium", "low"])
        submitted = st.form_submit_button("Analyze", type="primary", use_container_width=True)

    if submitted and svc and desc:
        st.session_state.analysis_running = True
        st.session_state.last_report = None
        payload = {
            "service": svc,
            "description": desc,
            "severity": sev,
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": {},
        }
        with st.spinner("Running analysis pipeline..."):
            report = _api_post("/api/v1/analyze", payload)
        st.session_state.analysis_running = False
        if report:
            st.session_state.last_report = report
            st.session_state.selected_incident_id = report["incident_id"]
            st.rerun()
        else:
            st.error("Analysis failed. Is the API running?")

    st.divider()

    # --- Recent Incidents ---
    st.subheader("Recent Incidents")
    incidents = _api_get("/api/v1/incidents") or []

    if not incidents:
        st.caption("No incidents yet.")
    for inc in incidents:
        label = f"{inc['incident_id']}  \n{_severity_badge(inc['severity'])} **{inc['service']}**"
        if st.button(
            label,
            key=f"inc_{inc['incident_id']}",
            use_container_width=True,
        ):
            st.session_state.selected_incident_id = inc["incident_id"]
            st.session_state.last_report = None
            st.rerun()

# ---------------------------------------------------------------------------
# Main area — Tabs
# ---------------------------------------------------------------------------

tab_analysis, tab_trace, tab_analytics = st.tabs([
    "📋 Incident Analysis",
    "🔗 Decision Trace",
    "📊 Analytics",
])

# ---------------------------------------------------------------------------
# Resolve selected incident data
# ---------------------------------------------------------------------------

report: dict | None = None
trace: list | None = None

selected_id = st.session_state.selected_incident_id

if selected_id:
    last = st.session_state.last_report
    if last and last.get("incident_id") == selected_id:
        report = last
    else:
        report = _api_get(f"/api/v1/incidents/{selected_id}")
        if report:
            st.session_state.last_report = report

    trace = _api_get(f"/api/v1/incidents/{selected_id}/trace")


# =====================================================================
# TAB 1 — Incident Analysis
# =====================================================================

with tab_analysis:
    if st.session_state.analysis_running:
        st.info("Analysis pipeline is running...")
        with st.spinner("Triage → Research → Remediation"):
            pass

    elif report:
        alert = report.get("alert", {})

        # --- Summary card ---
        col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
        with col1:
            st.metric("Incident", report["incident_id"])
        with col2:
            st.metric("Service", alert.get("service", "—"))
        with col3:
            sev_val = alert.get("severity", "unknown")
            st.metric("Severity", sev_val.upper())
        with col4:
            ts = alert.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    st.metric("Time", dt.strftime("%H:%M:%S"))
                except ValueError:
                    st.metric("Time", ts[:19])
            else:
                st.metric("Time", "—")

        st.divider()

        # --- Summary ---
        st.subheader("Summary")
        st.write(report.get("summary", ""))

        # --- Root cause ---
        st.subheader("Root Cause Analysis")
        st.info(report.get("root_cause", "Unknown"))

        # --- Confidence bar ---
        confidence = report.get("confidence_score", 0)
        conf_color = _confidence_color(confidence)
        st.subheader("Confidence Score")
        st.progress(confidence, text=f"{confidence:.0%}")
        if conf_color == "red":
            st.warning("Low confidence — manual investigation recommended.")
        elif conf_color == "orange":
            st.caption("Moderate confidence — verify root cause before acting.")

        st.divider()

        # --- Remediation steps ---
        st.subheader("Remediation Steps")
        steps = report.get("remediation_steps", [])
        if steps:
            for i, step_text in enumerate(steps, 1):
                st.markdown(f"**{i}.** {step_text}")
        else:
            st.caption("No remediation steps generated.")

        # --- Human approval banner ---
        if report.get("requires_human_approval"):
            st.divider()
            st.warning(
                "**Human Approval Required**  \n"
                "This incident's remediation includes actions that require human review "
                "before execution. Do not auto-apply these changes to production.",
                icon="⚠️",
            )

        # --- Cost / duration footer ---
        st.divider()
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            st.metric("Duration", f"{report.get('duration_seconds', 0):.1f}s")
        with fc2:
            st.metric("Total Tokens", f"{report.get('total_tokens', 0):,}")
        with fc3:
            st.metric("Cost", f"${report.get('total_cost_usd', 0):.4f}")

    else:
        st.info("Select an incident from the sidebar or submit a new analysis.")


# =====================================================================
# TAB 2 — Decision Trace
# =====================================================================

with tab_trace:
    if not trace:
        st.info("Select an incident to view its decision trace.")
    else:
        st.subheader("Agent Decision Trace")

        if report:
            svc_name = report.get("alert", {}).get("service", "")
            st.caption(f"Incident **{report['incident_id']}** — {svc_name}")

        # --- Visual flow header ---
        flow_cols = st.columns([1, 0.3, 1, 0.3, 1])
        agent_order = ["triage", "research", "remediation"]
        for idx, name in enumerate(agent_order):
            col_idx = idx * 2
            with flow_cols[col_idx]:
                icon = AGENT_ICONS.get(name, "🤖")
                st.markdown(f"### {icon} {name.title()}")
            if idx < len(agent_order) - 1:
                with flow_cols[col_idx + 1]:
                    st.markdown(
                        "<div style='text-align:center; "
                        "padding-top:1.5rem; font-size:1.5rem'>"
                        "→</div>",
                        unsafe_allow_html=True,
                    )

        st.divider()

        # --- Step cards ---
        for i, step in enumerate(trace):
            agent = step.get("agent_name", "unknown")
            icon = AGENT_ICONS.get(agent, "🤖")

            with st.container(border=True):
                hcol1, hcol2 = st.columns([4, 1])
                with hcol1:
                    st.markdown(f"#### {icon} {agent.title()} — `{step.get('action', '')}`")
                with hcol2:
                    st.caption(step.get("timestamp", "")[:19])

                # Reasoning
                reasoning = step.get("reasoning", "")
                if reasoning:
                    st.markdown("**Reasoning**")
                    st.text(reasoning[:2000])

                # Tool calls
                tool_calls = step.get("tool_calls", [])
                if tool_calls:
                    st.markdown(f"**Tool Calls** ({len(tool_calls)})")
                    for tc in tool_calls:
                        tool_label = (
                            f"🔧 `{tc.get('tool_name', '?')}` "
                            f"— {tc.get('latency_ms', 0):.0f}ms"
                        )
                        with st.expander(tool_label):
                            st.markdown("**Input:**")
                            st.json(tc.get("arguments", {}))
                            if "result" in tc:
                                st.markdown("**Output:**")
                                st.json(tc["result"])

                # Metrics row
                mcol1, mcol2, mcol3 = st.columns(3)
                with mcol1:
                    st.caption(f"Tokens: **{step.get('tokens_used', 0):,}**")
                with mcol2:
                    st.caption(f"Cost: **${step.get('cost_usd', 0):.4f}**")
                with mcol3:
                    latency_sum = sum(tc.get("latency_ms", 0) for tc in tool_calls)
                    st.caption(f"Tool latency: **{latency_sum:.0f}ms**")

        # --- Totals ---
        st.divider()
        total_tokens = sum(s.get("tokens_used", 0) for s in trace)
        total_cost = sum(s.get("cost_usd", 0) for s in trace)
        total_tools = sum(len(s.get("tool_calls", [])) for s in trace)

        tc1, tc2, tc3 = st.columns(3)
        with tc1:
            st.metric("Total Tokens", f"{total_tokens:,}")
        with tc2:
            st.metric("Total Cost", f"${total_cost:.4f}")
        with tc3:
            st.metric("Total Tool Calls", total_tools)


# =====================================================================
# TAB 3 — Analytics
# =====================================================================

with tab_analytics:
    st.subheader("System Analytics")

    # Fetch all data
    all_incidents = _api_get("/api/v1/incidents?limit=100") or []
    prom_text = None
    try:
        r = httpx.get(f"{API_BASE}/metrics", timeout=10)
        if r.status_code == 200:
            prom_text = r.text
    except httpx.HTTPError:
        pass

    prom = _parse_prometheus_metrics(prom_text) if prom_text else {}

    if not all_incidents and not prom:
        st.info("No data yet. Run some analyses to populate the dashboard.")
    else:
        # --- Row 1: summary metrics ---
        m1, m2, m3, m4 = st.columns(4)

        with m1:
            st.metric("Total Analyses", len(all_incidents))

        with m2:
            if all_incidents:
                total = sum(i.get("total_cost_usd", 0) for i in all_incidents)
                avg_cost = total / len(all_incidents)
                st.metric("Avg Cost / Analysis", f"${avg_cost:.4f}")
            else:
                st.metric("Avg Cost / Analysis", "$0.00")

        with m3:
            total_cost_all = sum(i.get("total_cost_usd", 0) for i in all_incidents)
            st.metric("Total Cost", f"${total_cost_all:.4f}")

        with m4:
            approval_count = sum(1 for i in all_incidents if i.get("requires_human_approval"))
            rate = (approval_count / len(all_incidents) * 100) if all_incidents else 0
            st.metric("Approval Rate", f"{rate:.0f}%")

        st.divider()

        # --- Row 2: charts ---
        chart_left, chart_right = st.columns(2)

        # Cost over time (line chart)
        with chart_left:
            st.markdown("**Cost Per Analysis Over Time**")
            if all_incidents:
                cost_df = pd.DataFrame([
                    {
                        "timestamp": i.get("timestamp", ""),
                        "cost_usd": i.get("total_cost_usd", 0),
                    }
                    for i in reversed(all_incidents)
                ])
                if not cost_df.empty and "timestamp" in cost_df.columns:
                    cost_df["timestamp"] = pd.to_datetime(cost_df["timestamp"], errors="coerce")
                    cost_df = cost_df.dropna(subset=["timestamp"])
                    if not cost_df.empty:
                        cost_df = cost_df.set_index("timestamp")
                        st.line_chart(cost_df["cost_usd"])
                    else:
                        st.caption("No timestamp data available.")
                else:
                    st.caption("No cost data available.")
            else:
                st.caption("No data yet.")

        # Incident types (pie chart via bar chart — Streamlit native)
        with chart_right:
            st.markdown("**Incidents by Severity**")
            if all_incidents:
                sev_counts: dict[str, int] = {}
                for i in all_incidents:
                    s = i.get("severity", "unknown")
                    sev_counts[s] = sev_counts.get(s, 0) + 1
                sev_df = pd.DataFrame(
                    list(sev_counts.items()),
                    columns=["Severity", "Count"],
                ).set_index("Severity")
                st.bar_chart(sev_df)
            else:
                st.caption("No data yet.")

        st.divider()

        # --- Row 3: tool usage + RAG confidence ---
        chart_left2, chart_right2 = st.columns(2)

        with chart_left2:
            st.markdown("**Tool Usage Breakdown**")
            tool_data = prom.get("sentinel_tool_calls_total", [])
            if tool_data:
                tool_counts = {
                    lbl.get("tool_name", "?"): val
                    for lbl, val in tool_data
                    if val > 0
                }
                if tool_counts:
                    tool_df = pd.DataFrame(
                        list(tool_counts.items()),
                        columns=["Tool", "Calls"],
                    ).set_index("Tool")
                    st.bar_chart(tool_df)
                else:
                    st.caption("No tool call data yet.")
            else:
                st.caption("No tool call data yet.")

        with chart_right2:
            st.markdown("**RAG Retrieval Confidence Distribution**")
            bucket_data = prom.get("sentinel_rag_retrieval_score_bucket", [])
            if bucket_data:
                # Build histogram from cumulative buckets
                buckets_sorted = sorted(
                    [(lbl.get("le", ""), val) for lbl, val in bucket_data],
                    key=lambda x: float(x[0]) if x[0] != "+Inf" else 999,
                )
                prev = 0.0
                hist_rows = []
                for le_str, cum_val in buckets_sorted:
                    if le_str == "+Inf":
                        continue
                    count = cum_val - prev
                    prev = cum_val
                    hist_rows.append({"Score ≤": le_str, "Count": max(0, count)})
                if hist_rows:
                    hist_df = pd.DataFrame(hist_rows).set_index("Score ≤")
                    st.bar_chart(hist_df)
                else:
                    st.caption("No RAG score data yet.")
            else:
                st.caption("No RAG score data yet.")

        st.divider()

        # --- Row 4: token usage by agent + duration ---
        chart_left3, chart_right3 = st.columns(2)

        with chart_left3:
            st.markdown("**Token Usage by Agent**")
            token_data = prom.get("sentinel_llm_tokens_total", [])
            if token_data:
                agent_tokens: dict[str, dict[str, float]] = {}
                for lbl, val in token_data:
                    agent = lbl.get("agent_name", "?")
                    direction = lbl.get("direction", "?")
                    if agent not in agent_tokens:
                        agent_tokens[agent] = {}
                    agent_tokens[agent][direction] = val
                if agent_tokens:
                    token_df = pd.DataFrame(agent_tokens).T.fillna(0)
                    st.bar_chart(token_df)
                else:
                    st.caption("No token data yet.")
            else:
                st.caption("No token data yet.")

        with chart_right3:
            st.markdown("**Analysis Duration Distribution**")
            if all_incidents:
                durations = [i.get("duration_seconds", 0) for i in all_incidents]
                dur_df = pd.DataFrame(durations, columns=["Duration (s)"])
                st.bar_chart(dur_df.value_counts(bins=10).sort_index())
            else:
                st.caption("No data yet.")
