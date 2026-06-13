from collections import defaultdict
import pandas as pd
from backend.group_scenarios import _rank_group

FINISHED={"FINISHED","AWARDED"}
LIVE={"IN_PLAY","PAUSED"}
UPCOMING={"TIMED","SCHEDULED"}


def group_records(matches):
    frame=matches[(matches["stage"]=="GROUP_STAGE")&matches["group"].notna()]
    groups=defaultdict(set); rows=[]
    for row in frame.itertuples(index=False):
        group=str(row.group).replace("GROUP_","")
        home,away=str(row.home_team),str(row.away_team)
        groups[group].update([home,away])
        hs=getattr(row,"home_score_full_time",None); aw=getattr(row,"away_score_full_time",None)
        rows.append({"match_id":int(row.match_id),"group":group,"status":str(row.status),"minute":getattr(row,"minute",None),"home_team":home,"away_team":away,"home_score":int(hs) if pd.notna(hs) else 0,"away_score":int(aw) if pd.notna(aw) else 0})
    return rows,{g:sorted(t) for g,t in groups.items()}
