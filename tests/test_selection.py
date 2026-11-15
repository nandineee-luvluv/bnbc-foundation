"""Project-level foundation selection checks."""

from bnbc_foundation.core.models import sample_project
from bnbc_foundation.core.selector import design_project, run_design


def test_selection_covers_every_element():
    project = sample_project()
    run = design_project(project)
    selected = [r for r in run.results if r.details.get("selected", True)]
    assert selected
    covered = set()
    for result in selected:
        assert result.foundation_type
        assert result.size
        assert result.quantity >= 1
        assert result.status in ("OK", "CHECK", "FAIL")
        assert result.governing
        covered.update(result.covers or [result.element_id])
    element_ids = {e.id for e in project.elements}
    assert element_ids <= covered
    assert all(r.element_id for r in run.results)


def test_raft_trigger_always():
    project = sample_project()
    project.options.raft_trigger = "Always"
    run = design_project(project)
    assert len(run.results) == 1
    result = run.results[0]
    assert result.foundation_type == "Raft"
    assert result.details.get("selected") is True
    assert result.covers == [e.id for e in project.elements]


def test_run_stores_results_and_warnings():
    project = sample_project()
    run = run_design(project)
    assert project.results is run.results
    assert project.warnings == run.warnings
    assert project.results
    assert any(r.utilization > 0 for r in project.results)
    # Pile-group results must expose the supplementary check details too.
    by_id = {result.element_id: result for result in project.results}
    w1_checks = by_id["W1"].details.get("checks", {})
    assert {
        "uplift_utilization", "lateral_utilization", "pm_utilization",
        "downdrag", "uplift_ok", "lateral_ok", "pm_ok", "crack_width",
        "crack_ok",
    } <= set(w1_checks)


def test_adjacent_foundations_get_differential_settlement_warning():
    project = sample_project()
    run = design_project(project)
    assert any("Differential settlement" in warning for warning in run.warnings)
    by_id = {result.element_id: result for result in run.results}
    assert by_id["W1"].status == "CHECK"
    assert by_id["C2"].status == "CHECK"


def test_sample_liquefaction_trigger_is_reported():
    project = sample_project()
    run = design_project(project)
    assert project.options.pga_g > 0
    assert any("liquefaction FS" in warning for warning in run.warnings)


def test_missing_pga_produces_a_liquefaction_warning():
    project = sample_project()
    project.options.pga_g = 0.0
    run = design_project(project)
    assert any(
        "Liquefaction assessment not performed" in warning
        for warning in run.warnings
    )
