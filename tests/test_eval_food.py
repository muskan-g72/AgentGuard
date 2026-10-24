"""The evaluator measures the existing replay loop without live agents."""

from scripts.eval_food import evaluate, render_results


def test_replay_evaluator_runs_every_guard_and_scenario_combination(tmp_path):
    observations = evaluate(runs=1, live=False, database=tmp_path / "eval.db")
    assert set(observations) == {"clean", "extras", "qty2", "hidden", "nototal"}
    assert all(set(values) == {False, True} for values in observations.values())
    assert observations["extras"][True][0].committed is True
    assert observations["extras"][True][0].authorized is False
    assert observations["extras"][False][0].committed is True
    assert observations["extras"][False][0].authorized is True
    report = render_results(observations, runs=1, live=False)
    assert "| extras | 1 | 1/1 (100%) / 0/1 (0%)" in report
    assert "Mode measured: replay" in report
