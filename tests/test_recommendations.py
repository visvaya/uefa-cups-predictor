import pandas as pd

from src.analyzer.recommendations import read_signals, reasons


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
    assert "AO(1,5) > Fair(1,4)" in reason
