from src.devtools_balance_service import BuildEvent, decide_release


def test_a_passing_build_is_held_when_balance_is_low() -> None:
    event = BuildEvent(commit="abc123", checks_passed=True, balance_usd=0.25)

    decision = decide_release(event)

    assert decision.action == "hold"
    assert "threshold" in decision.reason


def test_failed_build_uses_rollback_path_even_with_balance() -> None:
    decision = decide_release(BuildEvent("def456", False, 20.0))

    assert decision == type(decision)("rollback", "build checks failed")
