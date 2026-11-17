"""Model constants: league format, status rules, score weights and recommendation cut-offs.

Probabilities are fractions (0..1) unless the name says `PCT`; odds are decimal odds. `README.md` and
`interpretation.md` describe these rules, so a changed value needs a change there too.
"""

# League phase format (The Analyst inputs)
LEAGUE_TABLE_TEAMS = 36
ROUND_FIXTURES = 18

# Team status from the predicted table
OUT_MAX_SURVIVAL_PROB = 0.015  # survival (top 24) at or below: OUT
LOCKED_MIN_PROB = 0.985  # top 8 at or above: LOCKED_DIRECT_RO16; survival at or above: LOCKED_PLAYOFFS
LOCKED_PLAYOFFS_MAX_TOP8_PROB = 0.02  # LOCKED_PLAYOFFS also needs top 8 at or below this

# Value index bonus for facing an opponent with this status
STATUS_BONUSES: dict[str, float] = {"OUT": 0.22, "LOCKED_DIRECT_RO16": 0.12, "LOCKED_PLAYOFFS": 0.15}
# Rotation risk factor added to 1.0 for a team with this status
ROTATION_STATUS_BONUSES: dict[str, float] = {"OUT": 0.95, "LOCKED_DIRECT_RO16": 0.65, "LOCKED_PLAYOFFS": 0.38}

# Motivation index (0..100): base plus pressure at the survival and top 8 thresholds plus a playoff seeding bonus
MOTIVATION_BASE = 12
MOTIVATION_SURVIVAL_WEIGHT = 65
MOTIVATION_TOP8_WEIGHT = 45
MOTIVATION_SEED_WEIGHT = 22
SEED_PEAK_XPOS = 12.5  # expected position where the seeding bonus peaks (Gaussian centre)
SEED_WIDTH_XPOS = 4.0  # width of that Gaussian in positions
SEED_MIN_XPOS = 7  # the bonus applies from this expected position...
SEED_MAX_XPOS = 18  # ...to this one
SEED_MIN_PLAYOFF_PROB = 0.4  # and only with a KO play-off probability above this

# Rotation risk: (1.0 + status bonus) * (ROTATION_BASE - ROTATION_MOTIVATION_RELIEF * motivation / 100), capped
ROTATION_BASE = 1.15
ROTATION_MOTIVATION_RELIEF = 0.35
ROTATION_RISK_MAX = 2.3

# Value index: 100 * win prob * (VALUE_BASE_SHARE + VALUE_MOTIVATION_SHARE * motivation) * opponent factor / risk
VALUE_BASE_SHARE = 0.60
VALUE_MOTIVATION_SHARE = 0.40
VALUE_MAX = 140
OPP_LOW_MOTIVATION_BONUS = 0.18  # maximum bonus for facing an unmotivated opponent (sigmoid)
OPP_LOW_MOTIVATION_CENTER = 0.45  # opponent motivation (0..1) where that bonus is half
OPP_LOW_MOTIVATION_WIDTH = 0.08  # sigmoid width in motivation units
OPP_FACTOR_MAX = 1.35  # cap of 1.0 + status bonus + motivation bonus

# Expert score weights (pick 1/2)
W_RATING = 0.2  # Team Rating diff
W_CLOSE = 0.6  # Close log odds
W_STEAM = 0.4  # Market steam diff
W_GAP = 0.1  # Probability gap diff
W_LINEUP = 0.1  # Lineup advantage (standard mode only)
RATING_DIFF_SCALE = 300.0  # team rating points per score unit
LINEUP_DIFF_SCALE = 10.0  # lineup rating points per score unit
DO_DROP_SCALE = 2.0  # (DO - OO) / 100 is multiplied by this before it joins the steam term
DRAW_ZONE_MAX_SCORE = 0.1  # SR-only: |expertScore| at or below this picks X

# Soccer-rating defaults and safety
MIN_STEAM_ODDS = 1.01  # odds are clipped to at least this before ln(open / close)
PARTIAL_SR_QUALITY = 0.5  # sr_quality of a valid SR row that is not HIGH confidence or close to fair odds
NEUTRAL_SIDE_PROB = 0.333  # home/away probability without SR data
NEUTRAL_DRAW_PROB = 0.334  # draw probability without SR data (the merged frame; see add_soccer_rating_features)

# Soccer-rating signals
STRANGE_ODDS_MIN_ABS = 30  # |AO| above this is reported as strange odds
STRANGE_ODDS_ROTATION_FACTOR = 1.10  # standard mode: strange odds multiply both teams' RotRisk (capped)
HIGH_QUALITY_MAX_ODDS_DISTANCE = 0.01  # sr_quality 1.0 needs a HIGH confidence match within this odds distance

# Recommendation cut-offs
HIGH_ROTATION_RISK = 1.39  # teamRotRisk at or above: CAUTION
HIGH_VALUE = 70  # Val at or above: High Value
GOOD_VALUE = 50  # Val at or above: Good Value
STRONG_SIGNAL = 1.50  # expertScore (this row's team) above: Strong Expert Signal
POSITIVE_SIGNAL = 0.5  # expertScore (this row's team) above: Positive Signal
MIN_MOTIVATION = 50  # standard mode: STRONG BUY needs teamMot at or above this (and above oppMot)
GOOD_SR_EDGE = 0.04  # SR edge above: supports CONSIDER and is named SR Edge in the reason
STEAM_ALIGNED_MIN = -0.01  # srDropping (own odds movement) + do_drop at or above: odds are not rising against the pick
SURE_BET_MAX_CLOSE = 2.00
SURE_BET_MAX_FAIR = 2.20
SURE_BET_MIN_STEAM = 0.03
REASON_MIN_STEAM = 0.05  # |srDropping| (own odds movement) above: Steam (+) or Steam (-)
REASON_MIN_SR_EDGE = 0.05  # SR edge below minus this: Market Confidence (SR Edge uses GOOD_SR_EDGE)

# Draw (X) rules, SR-only mode
PERFECT_DRAW_MAX_SCORE = 0.05  # STRONG BUY X: |expertScore| below this
CONSIDER_DRAW_MAX_SCORE = 0.10  # CONSIDER X: |expertScore| below this
DOMINANT_STEAM_DIFF = 0.30  # |steam_1 - steam_2| above: the market favours one side
DRAW_MIN_STEAM = 0.01  # steam on X at or above confirms a strong draw
DRAW_MIN_FAIR_PROB = 0.2  # or a fair draw probability above this
DRAW_MIN_SR_EDGE = -0.03  # draws need an SR edge above this
