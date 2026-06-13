from __future__ import annotations

from pathlib import Path


APP_PATH = Path("app.py")
MARKER = "GITHUB_WORKFLOW_RUNS_URL"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Expected one {label} anchor, found {count}."
        )
    return text.replace(old, new, 1)


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")

    if MARKER in text:
        print("Production-health UI already applied.")
        return

    text = replace_once(
        text,
        'API_URL = "https://api.football-data.org/v4/competitions/WC/matches"\n',
        'API_URL = "https://api.football-data.org/v4/competitions/WC/matches"\n'
        'GITHUB_WORKFLOW_RUNS_URL = (\n'
        '    "https://api.github.com/repos/hayalows/cupmarket-2026/"\n'
        '    "actions/workflows/update-cupmarket.yml/runs?per_page=30"\n'
        ')\n'
        'WORKFLOW_STALE_MINUTES = 45\n',
        "API constant",
    )

    helper_anchor = (
        '    return parse_api_matches(response.json()), metadata\n\n\n'
        'def get_match_data() -> tuple[pd.DataFrame, dict]:\n'
    )

    helper_code = '''    return parse_api_matches(response.json()), metadata


@st.cache_data(ttl=300, show_spinner=False)
def fetch_workflow_health() -> dict:
    try:
        response = requests.get(
            GITHUB_WORKFLOW_RUNS_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "CupMarket-Streamlit",
            },
            timeout=20,
        )
        response.raise_for_status()
        runs = response.json().get("workflow_runs", [])
    except Exception as exc:
        return {
            "available": False,
            "warning": str(exc),
            "latest_run": None,
            "last_success": None,
            "last_failure": None,
        }

    def summarize(run):
        if not run:
            return None
        return {
            "run_number": run.get("run_number"),
            "event": run.get("event"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "created_at": run.get("created_at"),
            "run_started_at": run.get("run_started_at"),
            "updated_at": run.get("updated_at"),
            "html_url": run.get("html_url"),
            "head_sha": run.get("head_sha"),
        }

    latest = runs[0] if runs else None
    last_success = next(
        (
            run
            for run in runs
            if run.get("status") == "completed"
            and run.get("conclusion") == "success"
        ),
        None,
    )
    failure_conclusions = {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "startup_failure",
        "stale",
    }
    last_failure = next(
        (
            run
            for run in runs
            if run.get("status") == "completed"
            and run.get("conclusion") in failure_conclusions
        ),
        None,
    )

    return {
        "available": True,
        "warning": None,
        "latest_run": summarize(latest),
        "last_success": summarize(last_success),
        "last_failure": summarize(last_failure),
    }


def utc_timestamp(value):
    if not value:
        return pd.NaT
    return pd.to_datetime(value, errors="coerce", utc=True)


def format_utc_timestamp(value) -> str:
    timestamp = utc_timestamp(value)
    if pd.isna(timestamp):
        return "Never"
    return timestamp.strftime("%Y-%m-%d %H:%M UTC")


def build_production_health(
    matches: pd.DataFrame,
    simulation_metadata: dict,
    workflow_health: dict,
) -> dict:
    now = pd.Timestamp.now(tz="UTC")
    latest_run = workflow_health.get("latest_run") or {}
    last_success = workflow_health.get("last_success") or {}
    last_failure = workflow_health.get("last_failure") or {}

    live_finished_group_matches = 0
    if not matches.empty and {"stage", "status"}.issubset(matches.columns):
        live_finished_group_matches = int(
            (
                (matches["stage"] == "GROUP_STAGE")
                & (matches["status"] == "FINISHED")
            ).sum()
        )

    model_finished_group_matches = int(
        simulation_metadata.get("finished_group_matches", 0) or 0
    )
    pending_finished_matches = max(
        0,
        live_finished_group_matches - model_finished_group_matches,
    )

    reasons = []
    latest_status = latest_run.get("status")
    latest_conclusion = latest_run.get("conclusion")

    if not workflow_health.get("available"):
        workflow_label = "Unknown"
        reasons.append("GitHub Actions status could not be loaded")
    elif latest_status in {"queued", "in_progress", "waiting", "requested"}:
        workflow_label = "Updating"
    elif latest_conclusion == "success":
        workflow_label = "Healthy"
    elif latest_run:
        workflow_label = "Failed"
        reasons.append(
            "the latest GitHub Actions run did not complete successfully"
        )
    else:
        workflow_label = "Unknown"
        reasons.append("no GitHub Actions run was found")

    workflow_updated_at = utc_timestamp(latest_run.get("updated_at"))
    workflow_age_minutes = None
    if not pd.isna(workflow_updated_at):
        workflow_age_minutes = max(
            0.0,
            (now - workflow_updated_at).total_seconds() / 60.0,
        )
        if workflow_age_minutes > WORKFLOW_STALE_MINUTES:
            reasons.append(
                f"the latest workflow check is {workflow_age_minutes:.0f} minutes old"
            )

    if pending_finished_matches:
        reasons.append(
            f"{pending_finished_matches} finished group match"
            + ("es are" if pending_finished_matches != 1 else " is")
            + " not yet included in the model"
        )

    model_generated_at = utc_timestamp(
        simulation_metadata.get("generated_at_utc")
    )
    model_age_hours = None
    if pd.isna(model_generated_at):
        reasons.append("no model-generation timestamp is available")
    else:
        model_age_hours = max(
            0.0,
            (now - model_generated_at).total_seconds() / 3600.0,
        )

    status = workflow_label
    if reasons and status == "Healthy":
        status = "Attention"

    return {
        "status": status,
        "stale": bool(reasons),
        "reasons": reasons,
        "latest_run": latest_run,
        "last_success": last_success,
        "last_failure": last_failure,
        "last_success_text": format_utc_timestamp(
            last_success.get("updated_at")
        ),
        "last_failure_text": format_utc_timestamp(
            last_failure.get("updated_at")
        ),
        "model_generated_text": format_utc_timestamp(
            simulation_metadata.get("generated_at_utc")
        ),
        "model_age_hours": model_age_hours,
        "workflow_age_minutes": workflow_age_minutes,
        "live_finished_group_matches": live_finished_group_matches,
        "model_finished_group_matches": model_finished_group_matches,
        "pending_finished_matches": pending_finished_matches,
        "new_matches_processed": int(
            simulation_metadata.get(
                "new_finished_matches_processed",
                0,
            )
            or 0
        ),
    }


def get_match_data() -> tuple[pd.DataFrame, dict]:
'''

    text = replace_once(
        text,
        helper_anchor,
        helper_code,
        "workflow-health helper",
    )

    load_anchor = (
        'matches, match_metadata = get_match_data()\n\n'
        'st.title("CupMarket 2026")\n'
    )
    load_code = '''matches, match_metadata = get_match_data()
workflow_health = fetch_workflow_health()
production_health = build_production_health(
    matches,
    phase5_meta,
    workflow_health,
)

st.title("CupMarket 2026")
'''
    text = replace_once(
        text,
        load_anchor,
        load_code,
        "health-state load",
    )

    sidebar_anchor = '''    st.caption(
        "Data provided by football-data.org"
    )
'''
    sidebar_code = '''    health_status = production_health.get("status", "Unknown")
    if health_status == "Healthy":
        st.success("Automation healthy")
    elif health_status == "Updating":
        st.info("Automation updating")
    elif health_status == "Failed":
        st.error("Automation failed")
    else:
        st.warning(f"Automation: {health_status}")

    st.caption(
        "Data provided by football-data.org"
    )
'''
    text = replace_once(
        text,
        sidebar_anchor,
        sidebar_code,
        "sidebar health status",
    )

    model_health_anchor = '''elif page == "Model Health":
    st.header("Model Health")

    if phase3_eval:
'''
    model_health_code = '''elif page == "Model Health":
    st.header("Model Health")

    st.subheader("Production pipeline")
    health_columns = st.columns(4)
    health_columns[0].metric(
        "Workflow status",
        production_health.get("status", "Unknown"),
    )
    health_columns[1].metric(
        "Last successful automatic update",
        production_health.get("last_success_text", "Never"),
    )
    health_columns[2].metric(
        "Last failed update",
        production_health.get("last_failure_text", "Never"),
    )
    health_columns[3].metric(
        "New matches processed",
        production_health.get("new_matches_processed", 0),
    )

    freshness_columns = st.columns(4)
    freshness_columns[0].metric(
        "Model last refreshed",
        production_health.get("model_generated_text", "Never"),
    )
    freshness_columns[1].metric(
        "Live finished group matches",
        production_health.get("live_finished_group_matches", 0),
    )
    freshness_columns[2].metric(
        "Matches inside model",
        production_health.get("model_finished_group_matches", 0),
    )
    freshness_columns[3].metric(
        "Pending model updates",
        production_health.get("pending_finished_matches", 0),
    )

    if production_health.get("stale"):
        st.error(
            "Data-staleness warning: "
            + "; ".join(production_health.get("reasons", []))
            + "."
        )
    else:
        st.success(
            "The automation is healthy and all currently finished "
            "group-stage matches are included in the model."
        )

    if workflow_health.get("warning"):
        st.warning(
            "GitHub workflow status could not be checked: "
            + workflow_health["warning"]
        )

    latest_run_url = (
        production_health.get("latest_run", {}).get("html_url")
    )
    if latest_run_url:
        st.link_button(
            "Open latest GitHub Actions run",
            latest_run_url,
        )

    st.caption(
        "The workflow-status check is cached for five minutes. "
        "A model refresh is considered behind when the live API shows "
        "more completed group matches than the saved simulation contains."
    )

    if phase3_eval:
'''
    text = replace_once(
        text,
        model_health_anchor,
        model_health_code,
        "Model Health section",
    )

    APP_PATH.write_text(text, encoding="utf-8")
    print("Production-health UI added to app.py.")


if __name__ == "__main__":
    main()
