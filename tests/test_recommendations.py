import pandas as pd

from analyzer.config import GOOD_SR_EDGE
from analyzer.recommendations import CONSIDER, NEUTRAL, STRONG_BUY, labels, read_signals, reasons


def test_reasons_write_numbers_with_the_given_decimal_separator() -> None:
    ranking = pd.DataFrame(
        {
            "TeamStatus": ["IN_PLAY"],
            "TeamRotRisk": [1.0],
            "ValFinal": [75.0],
            "Close": [1.5],
            "Fair": [1.4],
            "pick12": ["X"],
            "is_home": [True],
            "steam_x": [0.06],
        }
    )

    reason = reasons(ranking, read_signals(ranking), allow_draws=True, decimal=",")[0]

    assert "SteamX 0,06" in reason
    assert "Close(1,5) > Fair(1,4)" in reason


def test_reasons_name_the_sr_edge_whenever_it_can_make_the_row_consider() -> None:
    ranking = pd.DataFrame(
        {
            "TeamStatus": ["IN_PLAY", "IN_PLAY"],
            "TeamRotRisk": [1.0, 1.0],
            "SR_edge": [GOOD_SR_EDGE + 0.005, GOOD_SR_EDGE],
        }
    )

    reason = reasons(ranking, read_signals(ranking), allow_draws=False, decimal=".")

    assert reason.tolist() == ["SR Edge", "-"]


def _strong_favourite(sr_dropping: float, **extra: object) -> pd.DataFrame:
    """A heavy favourite with a strong model signal, as SR-only sees it: low closing odds, no motivation data."""
    return pd.DataFrame(
        {
            "TeamStatus": ["IN_PLAY"],
            "TeamRotRisk": [1.0],
            "expertScore": [2.0],
            "pick12": ["1"],
            "Close": [1.10],
            "Fair": [1.15],
            "srDropping": [sr_dropping],
            **{k: [v] for k, v in extra.items()},
        }
    )


def _label_and_reason(ranking: pd.DataFrame, allow_draws: bool) -> tuple[str, str]:
    s = read_signals(ranking)
    return str(labels(ranking, s, allow_draws)[0]), reasons(ranking, s, allow_draws, ".")[0]


def test_sr_only_strong_signal_without_steam_stays_consider_and_says_why() -> None:
    label, reason = _label_and_reason(_strong_favourite(0.0), allow_draws=True)

    assert label == CONSIDER
    assert "(No Steam Confirmation)" in reason


def test_sr_only_strong_signal_with_falling_odds_is_a_sure_bet_without_the_marker() -> None:
    label, reason = _label_and_reason(_strong_favourite(0.05), allow_draws=True)

    assert label == STRONG_BUY
    assert "Sure Bet Pattern" in reason
    assert "No Steam Confirmation" not in reason


def test_sr_only_strong_signal_with_rising_odds_names_the_risk_not_the_missing_steam() -> None:
    _, reason = _label_and_reason(_strong_favourite(-0.05), allow_draws=True)

    assert "(Risk: Rising Odds)" in reason
    assert "No Steam Confirmation" not in reason


def test_standard_mode_keeps_strong_buy_for_a_motivated_strong_signal() -> None:
    label, reason = _label_and_reason(_strong_favourite(0.0, TeamMot=60, OppMot=40), allow_draws=False)

    assert label == STRONG_BUY
    assert "No Steam Confirmation" not in reason


def test_value_reason_compares_the_closing_and_fair_odds_as_they_are() -> None:
    ranking = pd.DataFrame(
        {
            "TeamStatus": ["IN_PLAY"] * 3,
            "TeamRotRisk": [1.0] * 3,
            "ValFinal": [75.0] * 3,
            "Close": [1.3, 1.404, None],
            "Fair": [1.4, 1.401, 1.4],
        }
    )

    reason = reasons(ranking, read_signals(ranking), allow_draws=False, decimal=".")

    assert reason.tolist() == ["High Value; Close(1.3) < Fair(1.4)", "High Value; Close(1.4) = Fair(1.4)", "High Value"]


def test_signal_reasons_go_only_to_the_team_the_score_favours() -> None:
    ranking = pd.DataFrame(
        {
            "TeamStatus": ["IN_PLAY"] * 4,
            "TeamRotRisk": [1.0] * 4,
            "expertScore": [2.0, -2.0, 0.8, -0.8],
            "srDropping": [-0.06, 0.0, 0.0, 0.0],
        }
    )

    reason = reasons(ranking, read_signals(ranking), allow_draws=False, decimal=".")

    assert reason.tolist() == ["Strong Expert Signal; (Risk: Rising Odds); Steam (-)", "-", "Positive Signal", "-"]


def _sure_bet(expert_score: float, team_mot: float, opp_mot: float) -> pd.DataFrame:
    """A row whose odds match the Sure Bet Pattern: short closing and fair odds that keep falling."""
    return _strong_favourite(0.05, Close=1.5, Fair=1.6, TeamMot=team_mot, OppMot=opp_mot).assign(
        expertScore=expert_score
    )


def test_standard_mode_sure_bet_is_strong_buy_for_a_motivated_favoured_team() -> None:
    label, reason = _label_and_reason(_sure_bet(0.3, team_mot=60, opp_mot=40), allow_draws=False)

    assert label == STRONG_BUY
    assert "Sure Bet Pattern" in reason


def test_standard_mode_sure_bet_needs_the_motivation_rule() -> None:
    label, reason = _label_and_reason(_sure_bet(0.8, team_mot=30, opp_mot=60), allow_draws=False)

    assert label == CONSIDER
    assert "Sure Bet Pattern" in reason


def test_standard_mode_sure_bet_needs_the_model_to_favour_the_team() -> None:
    label, _ = _label_and_reason(_sure_bet(-0.3, team_mot=60, opp_mot=40), allow_draws=False)

    assert label == NEUTRAL
