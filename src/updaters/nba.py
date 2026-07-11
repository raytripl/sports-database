from datetime import datetime
import pandas as pd
from nba_api.stats.endpoints import leaguegamelog
from nba_api.stats.static import players, teams
from src.db import save_frame

def _season_label() -> str:
    now = datetime.utcnow()
    start_year = now.year if now.month >= 10 else now.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"

def update() -> None:
    season = _season_label()

    game_log = leaguegamelog.LeagueGameLog(
        season=season,
        season_type_all_star="Regular Season",
        player_or_team_abbreviation="P",
    ).get_data_frames()[0]

    player_df = pd.DataFrame(players.get_players())
    team_df = pd.DataFrame(teams.get_teams())

    save_frame(game_log, "nba_player_game_logs")
    save_frame(player_df, "nba_players")
    save_frame(team_df, "nba_teams")
