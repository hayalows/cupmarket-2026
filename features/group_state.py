from backend.group_scenarios import _rank_group
from features.live_table_engine import FINISHED,LIVE,group_records


def _result(match):
    return {"home_team":match["home_team"],"away_team":match["away_team"],"home_goals":match["home_score"],"away_goals":match["away_score"]}


def current_tables(matches,strength=None):
    strength=strength or {}
    rows,groups=group_records(matches)
    values={group:[] for group in groups}
    for match in rows:
        if match["status"] in FINISHED or match["status"] in LIVE:
            values[match["group"]].append(_result(match))
    tables={group:_rank_group(teams,values[group],strength) for group,teams in groups.items()}
    return rows,groups,tables


def third_rows(tables,strength=None):
    strength=strength or {}; rows=[]
    for group,table in tables.items():
        if len(table)>=3:
            row=dict(table[2]); row["group"]=group; rows.append(row)
    return sorted(rows,key=lambda r:(r["points"],r["goal_difference"],r["goals_for"],strength.get(r["team"],0),r["team"]),reverse=True)
