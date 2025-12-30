from __future__ import annotations

from jobfinder.alerts.state import AlertState


def test_alert_state_marks_seen_and_reports_existing(tmp_path):
    state = AlertState(tmp_path / "alerts.db")

    assert state.already_seen(["a", "b"]) == set()

    inserted = state.mark_seen(["a", "b", "a", "", None])
    assert inserted == 2

    seen = state.already_seen(["a", "b", "c"])
    assert seen == {"a", "b"}


def test_alert_state_handles_empty_inputs(tmp_path):
    state = AlertState(tmp_path / "alerts.db")

    assert state.mark_seen([]) == 0
    assert state.already_seen([]) == set()
