from backend.group_scenarios import _rank_group
from features.live_table_engine import FINISHED,LIVE,group_records


def _result(match):
    return {"home_team":match["home_team"],"away_team":match["away_team"],"home_goals":match["home_score"],"away_goals":match["away_score"]}
