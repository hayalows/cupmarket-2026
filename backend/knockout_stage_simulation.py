"""Prediction and progressive simulation for the locked knockout bracket."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pandas as pd

try:
    from .knockout_stage_data import (
        BRACKET_MODE,
        FINAL_MATCH_NUMBER,
        MODEL_VERSION,
        KnockoutProcessingError,
        UPCOMING_STATUSES,
        _state_defaults,
        build_actual_results,
        is_knockout_stage,
    )
except ImportError:
    from knockout_stage_data import (
        BRACKET_MODE,
        FINAL_MATCH_NUMBER,
        MODEL_VERSION,
        KnockoutProcessingError,
        UPCOMING_STATUSES,
        _state_defaults,
        build_actual_results,
        is_knockout_stage,
    )


def _team_maps(team_map, live_elo, live_team_state, pipeline):
    name_lookup = dict(
        zip(team_map["live_team_name"], team_map["historical_team_name"])
    )
    rating_lookup = dict(zip(live_elo["team"], live_elo["elo_rating"]))
    state_lookup = live_team_state.set_index("team").to_dict(orient="index")

    def rating(live_team: str) -> float:
        historical = name_lookup.get(live_team, live_team)
        return float(rating_lookup.get(historical, pipeline.INITIAL_RATING))

    def state(live_team: str) -> dict:
        historical = name_lookup.get(live_team, live_team)
        return state_lookup.get(historical, _state_defaults(pipeline))

    return name_lookup, rating, state


def pair_xg_predictor(
    home_model,
    away_model,
    team_map,
    live_elo,
    live_state,
    pipeline,
):
    _, rating, state = _team_maps(team_map, live_elo, live_state, pipeline)
    cache: dict[tuple[str, str], tuple[float, float]] = {}

    def predict(home_team: str, away_team: str) -> tuple[float, float]:
        key = (home_team, away_team)
        if key in cache:
            return cache[key]
        home_rating = rating(home_team)
        away_rating = rating(away_team)
        if home_team in pipeline.WORLD_CUP_HOSTS:
            home_rating += pipeline.HOST_ELO_ADJUSTMENT
        if away_team in pipeline.WORLD_CUP_HOSTS:
            away_rating += pipeline.HOST_ELO_ADJUSTMENT
        home_state = state(home_team)
        away_state = state(away_team)
        elo_diff = home_rating - away_rating
        features = pd.DataFrame(
            [
                {
                    "home_elo": home_rating,
                    "away_elo": away_rating,
                    "elo_diff": elo_diff,
                    "abs_elo_diff": abs(elo_diff),
                    "neutral": 1,
                    "home_attack_form": float(home_state["ema_goals_for"]),
                    "home_defence_form": float(home_state["ema_goals_against"]),
                    "away_attack_form": float(away_state["ema_goals_for"]),
                    "away_defence_form": float(away_state["ema_goals_against"]),
                    "home_points_form": float(home_state["ema_points"]),
                    "away_points_form": float(away_state["ema_points"]),
                    "home_matches_before": int(home_state["matches"]),
                    "away_matches_before": int(away_state["matches"]),
                    "home_rest_days": 5.0,
                    "away_rest_days": 5.0,
                    "k_factor": pipeline.WORLD_CUP_K,
                }
            ]
        )[pipeline.FEATURE_COLUMNS]
        home_xg = pipeline.clip_xg(home_model.predict(features)[0])
        away_xg = pipeline.clip_xg(away_model.predict(features)[0])
        cache[key] = (home_xg, away_xg)
        return cache[key]

    return predict, rating, cache


def penalty_home_probability(home_team: str, away_team: str, rating) -> float:
    home_elo = rating(home_team)
    away_elo = rating(away_team)
    probability = 1.0 / (
        1.0 + 10.0 ** ((away_elo - home_elo) / 500.0)
    )
    return float(np.clip(probability, 0.35, 0.65))


def advancement_probabilities(
    home_xg: float,
    away_xg: float,
    penalty_home: float,
    pipeline,
) -> tuple[float, float]:
    regulation = pipeline.summarize_score_matrix(
        pipeline.score_probability_matrix(home_xg, away_xg)
    )
    extra_time = pipeline.summarize_score_matrix(
        pipeline.score_probability_matrix(
            home_xg * pipeline.EXTRA_TIME_GOAL_FACTOR,
            away_xg * pipeline.EXTRA_TIME_GOAL_FACTOR,
        )
    )
    home_advance = regulation["prob_home_win"] + regulation["prob_draw"] * (
        extra_time["prob_home_win"]
        + extra_time["prob_draw"] * penalty_home
    )
    away_advance = 1.0 - home_advance
    return float(home_advance), float(away_advance)


def generate_knockout_predictions(
    matches: pd.DataFrame,
    home_model,
    away_model,
    team_map: pd.DataFrame,
    live_elo: pd.DataFrame,
    live_state: pd.DataFrame,
    processed_ledger: pd.DataFrame,
    prediction_ledger: pd.DataFrame,
    pipeline,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    predict_xg, rating, _ = pair_xg_predictor(
        home_model,
        away_model,
        team_map,
        live_elo,
        live_state,
        pipeline,
    )
    upcoming = matches.loc[
        matches["stage"].map(is_knockout_stage)
        & matches["status"].isin(UPCOMING_STATUSES)
        & matches["home_team"].notna()
        & matches["away_team"].notna()
    ].sort_values("utc_date")
    generated_at = datetime.now(timezone.utc)
    rows = []
    for match in upcoming.itertuples(index=False):
        home_xg, away_xg = predict_xg(
            str(match.home_team),
            str(match.away_team),
        )
        score_summary = pipeline.summarize_score_matrix(
            pipeline.score_probability_matrix(home_xg, away_xg)
        )
        penalty_home = penalty_home_probability(
            str(match.home_team),
            str(match.away_team),
            rating,
        )
        home_advance, away_advance = advancement_probabilities(
            home_xg,
            away_xg,
            penalty_home,
            pipeline,
        )
        rows.append(
            {
                "prediction_id": str(uuid4()),
                "prediction_source": "phase6_knockout",
                "model_version": MODEL_VERSION,
                "generated_at_utc": generated_at.isoformat(),
                "state_matches_processed": int(len(processed_ledger)),
                "created_before_kickoff": (
                    generated_at < match.utc_date.to_pydatetime()
                ),
                "prediction_type": "knockout_pre_match",
                "match_id": int(match.match_id),
                "utc_date": match.utc_date,
                "status": str(match.status),
                "stage": str(match.stage),
                "group": None,
                "home_team": str(match.home_team),
                "away_team": str(match.away_team),
                "expected_home_goals": round(home_xg, 3),
                "expected_away_goals": round(away_xg, 3),
                "prob_home_win": round(score_summary["prob_home_win"], 6),
                "prob_draw": round(score_summary["prob_draw"], 6),
                "prob_away_win": round(score_summary["prob_away_win"], 6),
                "prob_home_advance": round(home_advance, 6),
                "prob_away_advance": round(away_advance, 6),
                "prob_btts_yes": round(score_summary["prob_btts_yes"], 6),
                "prob_over_2_5": round(score_summary["prob_over_2_5"], 6),
                "predicted_result": (
                    "HOME_ADVANCE"
                    if home_advance >= away_advance
                    else "AWAY_ADVANCE"
                ),
                "display_label": (
                    "HOME_ADVANCE"
                    if home_advance >= away_advance
                    else "AWAY_ADVANCE"
                ),
                "most_likely_score": score_summary["top_scorelines"][0][
                    "score"
                ],
                "most_likely_score_probability": round(
                    score_summary["top_scorelines"][0]["probability"], 6
                ),
                "second_likely_score": score_summary["top_scorelines"][1][
                    "score"
                ],
                "second_likely_score_probability": round(
                    score_summary["top_scorelines"][1]["probability"], 6
                ),
                "third_likely_score": score_summary["top_scorelines"][2][
                    "score"
                ],
                "third_likely_score_probability": round(
                    score_summary["top_scorelines"][2]["probability"], 6
                ),
            }
        )
    current = pd.DataFrame(rows)
    if not current.empty:
        prediction_ledger = pd.concat(
            [prediction_ledger, current],
            ignore_index=True,
            sort=False,
        ).drop_duplicates(subset=["prediction_id"], keep="first")
    return current, prediction_ledger


def simulate_knockout_match(
    home_team: str,
    away_team: str,
    rng: np.random.Generator,
    predict_xg,
    rating,
    pipeline,
) -> tuple[str, str]:
    home_xg, away_xg = predict_xg(home_team, away_team)
    home_goals = int(rng.poisson(home_xg))
    away_goals = int(rng.poisson(away_xg))
    if home_goals == away_goals:
        home_goals += int(
            rng.poisson(home_xg * pipeline.EXTRA_TIME_GOAL_FACTOR)
        )
        away_goals += int(
            rng.poisson(away_xg * pipeline.EXTRA_TIME_GOAL_FACTOR)
        )
    if home_goals == away_goals:
        if rng.random() < penalty_home_probability(
            home_team,
            away_team,
            rating,
        ):
            return home_team, away_team
        return away_team, home_team
    if home_goals > away_goals:
        return home_team, away_team
    return away_team, home_team


def _resolve_or_simulate(
    logical_number: int,
    home_team: str,
    away_team: str,
    actual_results: dict[int, dict],
    rng,
    predict_xg,
    rating,
    pipeline,
) -> tuple[str, str, bool]:
    actual = actual_results.get(logical_number)
    if actual is not None:
        expected = {str(home_team), str(away_team)}
        observed = {actual["home_team"], actual["away_team"]}
        if expected != observed:
            raise KnockoutProcessingError(
                f"Official match {logical_number} participants "
                f"{sorted(observed)} do not match bracket path "
                f"{sorted(expected)}"
            )
        return actual["winner"], actual["loser"], True
    winner, loser = simulate_knockout_match(
        home_team,
        away_team,
        rng,
        predict_xg,
        rating,
        pipeline,
    )
    return winner, loser, False


def run_progressive_simulation(
    matches: pd.DataFrame,
    locked_bracket: pd.DataFrame,
    current_tables: pd.DataFrame,
    home_model,
    away_model,
    team_map: pd.DataFrame,
    live_elo: pd.DataFrame,
    live_state: pd.DataFrame,
    previous_prices: pd.DataFrame | None,
    pipeline,
    number_of_simulations: int,
    random_seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    teams = sorted(current_tables["team"].astype(str).unique())
    if len(teams) != 48:
        raise KnockoutProcessingError(f"Expected 48 teams, found {len(teams)}")
    group_lookup = dict(
        zip(
            current_tables["team"].astype(str),
            current_tables["group"].astype(str),
        )
    )
    position_lookup = dict(
        zip(
            current_tables["team"].astype(str),
            current_tables["position"].astype(int),
        )
    )
    predict_xg, rating, xg_cache = pair_xg_predictor(
        home_model,
        away_model,
        team_map,
        live_elo,
        live_state,
        pipeline,
    )
    live_elo_lookup = {team: rating(team) for team in teams}
    actual_results = build_actual_results(matches, locked_bracket)
    r32_pairings = {
        int(row.bracket_match_number): (
            str(row.home_team),
            str(row.away_team),
        )
        for row in locked_bracket.itertuples(index=False)
    }
    if set(r32_pairings) != set(range(73, 89)):
        raise KnockoutProcessingError(
            "Locked Round-of-32 bracket is incomplete"
        )

    counter_columns = [
        "finish_1st_group",
        "finish_2nd_group",
        "finish_3rd_group",
        "best_third_qualifier",
        "reach_round_32",
        "reach_round_16",
        "reach_quarter_final",
        "reach_semi_final",
        "reach_final",
        "champion",
    ]
    counters = {
        team: {column: 0 for column in counter_columns}
        for team in teams
    }
    bracket_teams = {
        team for pair in r32_pairings.values() for team in pair
    }
    for team in teams:
        position = position_lookup[team]
        if position == 1:
            counters[team]["finish_1st_group"] = number_of_simulations
        elif position == 2:
            counters[team]["finish_2nd_group"] = number_of_simulations
        elif position == 3:
            counters[team]["finish_3rd_group"] = number_of_simulations
            if team in bracket_teams:
                counters[team]["best_third_qualifier"] = number_of_simulations
        if team in bracket_teams:
            counters[team]["reach_round_32"] = number_of_simulations

    rng = np.random.default_rng(random_seed)
    actual_resolutions = 0
    simulated_resolutions = 0
    for _ in range(number_of_simulations):
        winners: dict[int, str] = {}
        for logical in range(73, 89):
            home, away = r32_pairings[logical]
            winner, _, used_actual = _resolve_or_simulate(
                logical,
                home,
                away,
                actual_results,
                rng,
                predict_xg,
                rating,
                pipeline,
            )
            winners[logical] = winner
            counters[winner]["reach_round_16"] += 1
            actual_resolutions += int(used_actual)
            simulated_resolutions += int(not used_actual)
        for logical, (source_a, source_b) in pipeline.ROUND_OF_16.items():
            winner, _, used_actual = _resolve_or_simulate(
                logical,
                winners[source_a],
                winners[source_b],
                actual_results,
                rng,
                predict_xg,
                rating,
                pipeline,
            )
            winners[logical] = winner
            counters[winner]["reach_quarter_final"] += 1
            actual_resolutions += int(used_actual)
            simulated_resolutions += int(not used_actual)
        for logical, (source_a, source_b) in pipeline.QUARTER_FINALS.items():
            winner, _, used_actual = _resolve_or_simulate(
                logical,
                winners[source_a],
                winners[source_b],
                actual_results,
                rng,
                predict_xg,
                rating,
                pipeline,
            )
            winners[logical] = winner
            counters[winner]["reach_semi_final"] += 1
            actual_resolutions += int(used_actual)
            simulated_resolutions += int(not used_actual)
        for logical, (source_a, source_b) in pipeline.SEMI_FINALS.items():
            winner, _, used_actual = _resolve_or_simulate(
                logical,
                winners[source_a],
                winners[source_b],
                actual_results,
                rng,
                predict_xg,
                rating,
                pipeline,
            )
            winners[logical] = winner
            counters[winner]["reach_final"] += 1
            actual_resolutions += int(used_actual)
            simulated_resolutions += int(not used_actual)
        champion, _, used_actual = _resolve_or_simulate(
            FINAL_MATCH_NUMBER,
            winners[101],
            winners[102],
            actual_results,
            rng,
            predict_xg,
            rating,
            pipeline,
        )
        counters[champion]["champion"] += 1
        actual_resolutions += int(used_actual)
        simulated_resolutions += int(not used_actual)

    rows = []
    for team in teams:
        row = {
            "team": team,
            "group": group_lookup[team],
            "live_elo": live_elo_lookup[team],
        }
        for column in counter_columns:
            row[f"prob_{column}"] = (
                counters[team][column] / number_of_simulations
            )
        row["prob_group_exit"] = 1.0 - row["prob_reach_round_32"]
        row["prob_round_32_exit"] = (
            row["prob_reach_round_32"] - row["prob_reach_round_16"]
        )
        row["prob_round_16_exit"] = (
            row["prob_reach_round_16"]
            - row["prob_reach_quarter_final"]
        )
        row["prob_quarter_final_exit"] = (
            row["prob_reach_quarter_final"]
            - row["prob_reach_semi_final"]
        )
        row["prob_semi_final_exit"] = (
            row["prob_reach_semi_final"] - row["prob_reach_final"]
        )
        row["prob_runner_up"] = (
            row["prob_reach_final"] - row["prob_champion"]
        )
        rows.append(row)
    probabilities = pd.DataFrame(rows).sort_values(
        ["prob_champion", "prob_reach_final", "prob_reach_semi_final"],
        ascending=False,
    ).reset_index(drop=True)
    probabilities["champion_rank"] = np.arange(
        1, len(probabilities) + 1
    )
    prices = probabilities.copy()
    prices["cupmarket_price"] = (
        prices["prob_group_exit"]
        * pipeline.SETTLEMENT_VALUES["group_exit"]
        + prices["prob_round_32_exit"]
        * pipeline.SETTLEMENT_VALUES["round_32_exit"]
        + prices["prob_round_16_exit"]
        * pipeline.SETTLEMENT_VALUES["round_16_exit"]
        + prices["prob_quarter_final_exit"]
        * pipeline.SETTLEMENT_VALUES["quarter_final_exit"]
        + prices["prob_semi_final_exit"]
        * pipeline.SETTLEMENT_VALUES["semi_final_exit"]
        + prices["prob_runner_up"]
        * pipeline.SETTLEMENT_VALUES["runner_up"]
        + prices["prob_champion"]
        * pipeline.SETTLEMENT_VALUES["champion"]
    ).round(2)
    prices = prices.sort_values(
        "cupmarket_price", ascending=False
    ).reset_index(drop=True)
    prices["market_rank"] = np.arange(1, len(prices) + 1)
    if previous_prices is not None and not previous_prices.empty:
        previous = previous_prices[["team", "cupmarket_price"]].rename(
            columns={"cupmarket_price": "previous_price"}
        )
        prices = prices.merge(previous, on="team", how="left")
        prices["price_change"] = (
            prices["cupmarket_price"] - prices["previous_price"]
        )
        prices["price_change_percent"] = np.where(
            prices["previous_price"].abs() > 1e-12,
            100.0 * prices["price_change"] / prices["previous_price"],
            np.nan,
        )
    else:
        prices["previous_price"] = np.nan
        prices["price_change"] = np.nan
        prices["price_change_percent"] = np.nan

    totals = {
        "round_32_total": float(
            probabilities["prob_reach_round_32"].sum()
        ),
        "round_16_total": float(
            probabilities["prob_reach_round_16"].sum()
        ),
        "quarter_final_total": float(
            probabilities["prob_reach_quarter_final"].sum()
        ),
        "semi_final_total": float(
            probabilities["prob_reach_semi_final"].sum()
        ),
        "final_total": float(
            probabilities["prob_reach_final"].sum()
        ),
        "champion_total": float(
            probabilities["prob_champion"].sum()
        ),
    }
    expected = {
        "round_32_total": 32.0,
        "round_16_total": 16.0,
        "quarter_final_total": 8.0,
        "semi_final_total": 4.0,
        "final_total": 2.0,
        "champion_total": 1.0,
    }
    for key, expected_value in expected.items():
        if not np.isclose(totals[key], expected_value, atol=1e-6):
            raise KnockoutProcessingError(
                f"{key} failed: {totals[key]} != {expected_value}"
            )
    metadata = {
        "model_version": MODEL_VERSION,
        "bracket_mode": BRACKET_MODE,
        "number_of_simulations": int(number_of_simulations),
        "random_seed": int(random_seed),
        "actual_knockout_results_used": int(len(actual_results)),
        "actual_resolution_count_across_simulations": int(
            actual_resolutions
        ),
        "simulated_resolution_count_across_simulations": int(
            simulated_resolutions
        ),
        "pair_xg_cache_size": int(len(xg_cache)),
        "stage_probability_totals": totals,
        "settlement_values": pipeline.SETTLEMENT_VALUES,
        "limitations": [
            "Unfinished knockout matches use the existing Poisson goal models.",
            "Penalty shootouts use Elo-bounded probabilities between 35% and 65%.",
            (
                "Finished penalty shootouts count as draws for Elo, while the "
                "official winner advances."
            ),
        ],
    }
    return probabilities, prices, metadata
