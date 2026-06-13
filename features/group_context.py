from features.group_state import current_tables,third_rows
from features.live_table_engine import LIVE


def team_context(matches,team,strength=None):
    strength=strength or {}
    records,groups,tables=current_tables(matches,strength)
    record=next((row for row in records if team in {row["home_team"],row["away_team"]}),None)
    if not record:
        raise ValueError(f"{team} is not in the group-stage fixtures.")
    group=record["group"]; table=tables[group]
    row=next(item for item in table if item["team"]==team)
    thirds=third_rows(tables,strength); qualifiers={item["team"] for item in thirds[:8]}
    position=int(row["position"])
    if position<=2:
        label="Qualifies directly if matches ended now"
    elif position==3 and team in qualifiers:
        label="Qualifies as a best third-place team if matches ended now"
    else:
        label="Outside the qualification places if matches ended now"
    return {"team":team,"group":group,"table":table,"position":position,"points":int(row["points"]),"goal_difference":int(row["goal_difference"]),"status_if_ended_now":label,"simultaneous_matches":[item for item in records if item["group"]==group and item["status"] in LIVE],"ranked_thirds":thirds}
