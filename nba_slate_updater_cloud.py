import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe, get_as_dataframe
import requests
import io
import os
from datetime import date, timedelta
import pandas as pd
import time


def get_nba_daily_slate():
    print("Starting NBA Slate Updater...")

    API_KEY = "ca9280fb-7eb0-48e3-a33f-7b13192013df"
    url = "https://api.balldontlie.io/v1/games"
    headers = {"Authorization": API_KEY}
    today = date.today()

    # ---------------------------------------------------------
    # 1. FETCH PAST 14 DAYS OF GAMES (FOR REST & HEAT CALCULATION)
    # ---------------------------------------------------------
    print("Calculating team rest days and heat metrics...")

    # FIX: range(0, 15) includes 'today' in UTC, catching late-night West Coast games!
    past_dates = [(today - timedelta(days=i)).isoformat() for i in range(0, 8)]

    try:
        past_response = requests.get(url, headers=headers, params={"dates[]": past_dates, "per_page": 100}, timeout=15)
        past_games = past_response.json().get('data', [])

        last_played = {}
        team_last_games = {}

        if past_games:
            past_df = pd.DataFrame(past_games)
            past_df['date'] = pd.to_datetime(past_df['date']).dt.date

            for _, row in past_df.iterrows():
                game_date = row['date']
                home = row['home_team']['name']
                visitor = row['visitor_team']['name']
                home_score = row['home_team_score']
                visitor_score = row['visitor_team_score']

                # FIX: Only process games that have actually finished (score > 0) so we don't ruin rest days
                if home_score > 0 or visitor_score > 0:
                    if home not in last_played or game_date > last_played[home]:
                        last_played[home] = game_date
                    if visitor not in last_played or game_date > last_played[visitor]:
                        last_played[visitor] = game_date

                    if home not in team_last_games: team_last_games[home] = []
                    if visitor not in team_last_games: team_last_games[visitor] = []

                    if home_score > visitor_score:
                        team_last_games[home].append({'date': game_date, 'won': True})
                        team_last_games[visitor].append({'date': game_date, 'won': False})
                    elif visitor_score > home_score:
                        team_last_games[home].append({'date': game_date, 'won': False})
                        team_last_games[visitor].append({'date': game_date, 'won': True})

    except Exception as e:
        print(f"Could not fetch past games: {e}")
        last_played = {}
        team_last_games = {}

    def get_rest_days(nickname):
        if nickname in last_played:
            return (today - last_played[nickname]).days
        return 7

    def get_heat_stats(nickname):
        if nickname not in team_last_games:
            return 0, "❄️"
        sorted_games = sorted(team_last_games[nickname], key=lambda x: x['date'], reverse=True)
        last_3 = sorted_games[:3]
        wins = sum(1 for g in last_3 if g['won'])

        if wins == 3:
            return 3, "🔥🔥🔥"
        elif wins == 2:
            return 2, "🔥🔥"
        elif wins == 1:
            return 1, ""
        else:
            return 0, "❄️"

    # ---------------------------------------------------------
    # 2. FETCH INJURIES & CALCULATE IMPACT SCORES
    # ---------------------------------------------------------
    print("Cross-referencing injuries with Top 100 players...")

    espn_top_100 = ["Nikola Jokić", "Victor Wembanyama", "Shai Gilgeous-Alexander", "Luka Dončić",
                    "Giannis Antetokounmpo", "Jalen Brunson", "Anthony Edwards", "Cade Cunningham", "Jayson Tatum",
                    "Donovan Mitchell", "Stephen Curry", "Kevin Durant", "Devin Booker", "Joel Embiid", "Jaylen Brown",
                    "Tyrese Haliburton", "De'Aaron Fox", "LeBron James", "Damian Lillard", "Kawhi Leonard",
                    "Jamal Murray", "Jimmy Butler", "Cooper Flagg", "Bam Adebayo", "Paul George", "Kyrie Irving",
                    "Deni Avdija", "Zion Williamson", "Domantas Sabonis", "Karl-Anthony Towns", "Tyrese Maxey",
                    "Evan Mobley", "Jalen Duren", "Scottie Barnes", "LaMelo Ball", "Paolo Banchero", "Austin Reaves",
                    "Stephon Castle", "Pascal Siakam", "Anthony Davis", "Jalen Williams", "Brandon Ingram",
                    "Rudy Gobert", "Trae Young", "DeMar DeRozan", "Brandon Miller", "Derrick White",
                    "Kristaps Porzingis", "Bradley Beal", "CJ McCollum", "Julius Randle", "Mikal Bridges",
                    "Desmond Bane", "Jaren Jackson Jr.", "Darius Garland", "Fred VanVleet", "Chet Holmgren",
                    "Alperen Şengün", "Zach LaVine", "Tyler Herro", "Aaron Gordon", "Myles Turner", "OG Anunoby",
                    "Khris Middleton", "Jerami Grant", "Marcus Smart", "Deandre Ayton", "Jarrett Allen", "Kyle Kuzma",
                    "Jordan Poole", "Draymond Green", "Andrew Wiggins", "Brook Lopez", "Jrue Holiday", "Cam Thomas",
                    "Nic Claxton", "Josh Giddey", "Franz Wagner", "Anfernee Simons", "Jalen Green", "Klay Thompson",
                    "D'Angelo Russell", "Michael Porter Jr.", "Collin Sexton", "Tobias Harris", "Bojan Bogdanovic",
                    "Buddy Hield", "Norman Powell", "Malik Monk", "Immanuel Quickley", "Jonas Valanciunas",
                    "Bobby Portis", "Malcolm Brogdon", "Spencer Dinwiddie", "Clint Capela", "Harrison Barnes",
                    "Caleb Wilson", "Jalen Suggs", "RJ Barrett", "Luguentz Dort"]

    star_impact_map = {player: 100 for i, player in enumerate(espn_top_100)}

    try:
        injury_html = requests.get("https://www.basketball-reference.com/friv/injuries.fcgi").text
        injuries_df = pd.read_html(io.StringIO(injury_html))[0]

        team_injury_names = {}
        team_injury_impacts = {}

        manually_active = ["Luka Dončić"]

        for _, row in injuries_df.iterrows():
            player_text = str(row['Player'])
            team = str(row['Team'])

            if any(active_player in player_text for active_player in manually_active):
                continue

            description = str(row.get('Description', '')).lower()
            if 'probable' in description or 'available' in description or 'active' in description:
                continue

            for star, impact in star_impact_map.items():
                if star in player_text:
                    if team not in team_injury_names:
                        team_injury_names[team] = []
                        team_injury_impacts[team] = 0
                    team_injury_names[team].append(star)
                    team_injury_impacts[team] += impact

        injured_stars_by_team = {team: ", ".join(stars) for team, stars in team_injury_names.items()}
        impact_by_team = team_injury_impacts

    except Exception as e:
        print(f"Could not fetch injuries: {e}")
        injured_stars_by_team = {}
        impact_by_team = {}

    def get_injured_stars(full_team_name):
        return injured_stars_by_team.get(full_team_name, "None")

    def get_injury_impact(full_team_name):
        return impact_by_team.get(full_team_name, 0)

    # ---------------------------------------------------------
    # 3. BUILD TODAY'S SLATE & CALCULATE PG-SCORE
    # ---------------------------------------------------------
    print("Fetching today's NBA schedule...")
    try:
        response = requests.get(url, headers=headers, params={"dates[]": today.isoformat()}, timeout=15)
        response.raise_for_status()

        games_data = response.json().get('data', [])
        if not games_data:
            print("No games scheduled for today.")
            return None

        df = pd.DataFrame(games_data)

        df['home_team_name'] = df['home_team'].apply(lambda x: x['full_name'])
        df['visitor_team_name'] = df['visitor_team'].apply(lambda x: x['full_name'])
        df['home_team_nickname'] = df['home_team'].apply(lambda x: x['name'])
        df['visitor_team_nickname'] = df['visitor_team'].apply(lambda x: x['name'])

        df['home_rest_days'] = df['home_team_nickname'].apply(get_rest_days) - 1
        df['visitor_rest_days'] = df['visitor_team_nickname'].apply(get_rest_days) - 1

        df['home_injured_stars'] = df['home_team_name'].apply(get_injured_stars)
        df['visitor_injured_stars'] = df['visitor_team_name'].apply(get_injured_stars)

        df['home_injury_impact'] = df['home_team_name'].apply(get_injury_impact)
        df['visitor_injury_impact'] = df['visitor_team_name'].apply(get_injury_impact)

        standings_html = requests.get("https://www.basketball-reference.com/leagues/NBA_2027_standings.html").text
        tables = pd.read_html(io.StringIO(standings_html))
        standings = pd.concat([
            tables[0][['Eastern Conference', 'W/L%']].rename(columns={'Eastern Conference': 'Team'}),
            tables[1][['Western Conference', 'W/L%']].rename(columns={'Western Conference': 'Team'})
        ])

        def get_win_pct(nickname):
            match = standings[standings['Team'].astype(str).str.contains(nickname, case=False, na=False)]
            if not match.empty:
                return match['W/L%'].values[0]
            return 0.01

        df['home_win_pct'] = pd.to_numeric(df['home_team_nickname'].apply(get_win_pct), errors='coerce').fillna(0.01)
        df['visitor_win_pct'] = pd.to_numeric(df['visitor_team_nickname'].apply(get_win_pct), errors='coerce').fillna(
            0.01)
        df['home_win_pct'] = df['home_win_pct'].replace(0, 0.01)
        df['visitor_win_pct'] = df['visitor_win_pct'].replace(0, 0.01)

        df['home_win_ratio'] = df['home_win_pct'] / df['visitor_win_pct']
        df['visitor_win_ratio'] = df['visitor_win_pct'] / df['home_win_pct']

        df[['home_L3_wins', 'home_heat_emoji']] = df.apply(
            lambda row: pd.Series(get_heat_stats(row['home_team_nickname'])), axis=1)
        df[['visitor_L3_wins', 'visitor_heat_emoji']] = df.apply(
            lambda row: pd.Series(get_heat_stats(row['visitor_team_nickname'])), axis=1)

        df['home_pg_score'] = (df['home_win_ratio'] * 100) - df['home_injury_impact'] + (
                    df['home_rest_days'] * 10) + 15 + (df['home_L3_wins'] * 10)
        df['visitor_pg_score'] = (df['visitor_win_ratio'] * 100) - df['visitor_injury_impact'] + (
                    df['visitor_rest_days'] * 10) + (df['visitor_L3_wins'] * 10)

        df['Game'] = df['home_team_name'] + " vs " + df['visitor_team_name']
        df['Projected Winner'] = df.apply(
            lambda row: row['home_team_name'] if row['home_pg_score'] > row['visitor_pg_score'] else row[
                'visitor_team_name'],
            axis=1
        )

        # ---------------------------------------------------------
        # 4. FINAL CLEANUP & EXPORT TO GOOGLE SHEETS CLOUD
        # ---------------------------------------------------------
        df_raw = df[[
            'date', 'Game', 'Projected Winner',
            'home_team_name', 'visitor_team_name',
            'home_win_pct', 'visitor_win_pct',
            'home_win_ratio', 'visitor_win_ratio',
            'home_rest_days', 'visitor_rest_days',
            'home_injured_stars', 'visitor_injured_stars',
            'home_injury_impact', 'visitor_injury_impact',
            'home_L3_wins', 'visitor_L3_wins',
            'home_heat_emoji', 'visitor_heat_emoji',
            'home_pg_score', 'visitor_pg_score'
        ]]

        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        credentials_path = '/Users/paulgomes/Downloads/nba-predictor-514717-c995f23c647e.json'
        credentials = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        client = gspread.authorize(credentials)

        sheet_id = '1mbmggxfDbYmZ_siQB5tym2gWTLUlOIhOjB3Vfcegkzo'
        spreadsheet = client.open_by_key(sheet_id)

        # --- 1. OVERWRITE RAW DATA ---
        raw_data_sheet = spreadsheet.worksheet('Raw_Data')
        raw_data_sheet.clear()
        set_with_dataframe(raw_data_sheet, df_raw)
        time.sleep(3)
        print("Raw Data successfully pushed to cloud.")

        # --- BUILD GLOBAL RESULTS DICTIONARY ---
        # We build this once and use it to flawlessly grade both the Ledger and the User Picks
        results_dict = {}
        for game in past_games:
            home_team = game['home_team']['full_name']
            visitor_team = game['visitor_team']['full_name']
            home_pts = int(game.get('home_team_score', 0))
            away_pts = int(game.get('visitor_team_score', 0))

            if home_pts > 0 or away_pts > 0:
                matchup = f"{home_team} vs {visitor_team}"
                winner = home_team if home_pts > away_pts else visitor_team
                results_dict[matchup] = winner

        # --- 2. GRADE PAST LEDGER GAMES ---
        print("Grading Model Ledger...")
        ledger_sheet = spreadsheet.worksheet('Model_Ledger')
        df_ledger = get_as_dataframe(ledger_sheet, evaluate_formulas=True).dropna(how='all')

        if not df_ledger.empty and 'Actual Winner' in df_ledger.columns:
            updates = []
            for index, row in df_ledger.iterrows():
                if pd.isna(row['Actual Winner']) or str(row['Actual Winner']).strip() == "":
                    game_matchup = str(row['Game']).strip()

                    # Match purely by team names, completely bypassing Google Sheets date bugs
                    actual_winner = results_dict.get(game_matchup)

                    if actual_winner:
                        if str(actual_winner) in str(row['PG Projected Winner']):
                            correct_status = "TRUE"
                        else:
                            correct_status = "FALSE"

                        sheet_row = index + 2
                        updates.append({
                            'range': f'D{sheet_row}:E{sheet_row}',
                            'values': [[actual_winner, correct_status]]
                        })

            if updates:
                ledger_sheet.batch_update(updates)
                time.sleep(3)

                # --- 2b. GRADE COMMUNITY PICKS & CONTRARIAN BONUS ---
                print("Grading community picks...")
                user_picks_sheet = spreadsheet.worksheet('User_Picks')
                df_users = get_as_dataframe(user_picks_sheet, evaluate_formulas=True).dropna(how='all')

                # NEW: Fetch the Answer Key for the daily prop (from Editor_Note cell C2)
                # NEW: Fetch the Answer Key for the daily prop (from Editor_Note cell C2)
                try:
                    c2_value = spreadsheet.worksheet('Editor_Note').acell('C2').value
                    if c2_value:  # Strictly check that the cell actually has text in it
                        prop_answer_key = str(c2_value).strip().upper()
                        valid_prop_answers = [ans.strip() for ans in prop_answer_key.split(',') if ans.strip()]
                    else:
                        valid_prop_answers = []
                except:
                    valid_prop_answers = []  # Defaults to empty if the cell is missing

                if 'Result' not in df_users.columns:
                    df_users['Result'] = ""
                if 'Points Earned' not in df_users.columns:
                    df_users['Points Earned'] = 0

                if not df_users.empty:
                    results_dict = {}
                    for game in past_games:
                        home_team = game['home_team']['full_name']
                        visitor_team = game['visitor_team']['full_name']
                        home_pts = int(game.get('home_team_score', 0))
                        away_pts = int(game.get('visitor_team_score', 0))

                        if home_pts > 0 or away_pts > 0:
                            matchup = f"{home_team} vs {visitor_team}"
                            winner = home_team if home_pts > away_pts else visitor_team
                            results_dict[matchup] = winner

                    ungraded_mask = df_users['Result'].astype(str).str.strip().isin(["", "PENDING", "nan", "None"])
                    ungraded_picks = df_users[ungraded_mask]

                    if not ungraded_picks.empty:
                        pick_counts = ungraded_picks.groupby(['Game', 'User Pick']).size()
                        total_game_picks = ungraded_picks.groupby('Game').size()

                        # Tracker to ensure we only award the +50 Prop Bonus ONCE per user, per day
                        graded_prop_users = set()

                        for idx, row in ungraded_picks.iterrows():
                            game_matchup = str(row['Game']).strip()
                            user_pick = str(row['User Pick']).strip()
                            username = str(row['Username']).strip()
                            pick_date = str(row['Date'])[:10]

                            # STRIP AND CAPITALIZE THE USER'S GUESS
                            prop_guess = str(row.get('Top Scorer Guess', '')).strip().upper()

                            actual_winner = results_dict.get(game_matchup)

                            if actual_winner is None:
                                result_str = "PENDING"
                                points = 0
                            else:
                                is_correct = (actual_winner in user_pick)
                                result_str = "WIN" if is_correct else "LOSS"
                                points = 100 if is_correct else 0

                                # 1. Contrarian Bonus (+50)
                                if is_correct:
                                    pct_picked = pick_counts.get((game_matchup, user_pick), 1) / total_game_picks.get(
                                        game_matchup, 1)
                                    if pct_picked < 0.30:
                                        points += 50

                                # 2. Prop Pick Bonus (+50)
                                # Only evaluate if an answer key exists, AND we haven't graded this user today yet
                                if valid_prop_answers and (pick_date, username) not in graded_prop_users:

                                    # Check if their cleaned guess matches any of our cleaned answers
                                    if prop_guess and any(
                                            ans in prop_guess or prop_guess in ans for ans in valid_prop_answers):
                                        points += 50

                                    # Add them to the tracker so they don't get another 50 points on the next row!
                                    graded_prop_users.add((pick_date, username))

                            df_users.at[idx, 'Result'] = result_str
                            df_users.at[idx, 'Points Earned'] = points

                # --- 2c. REBUILD THE GLOBAL LEADERBOARD ---
                print("Rebuilding Leaderboard...")
                if not df_users.empty:
                    user_picks_sheet.clear()
                    set_with_dataframe(user_picks_sheet, df_users.fillna(""))
                    time.sleep(3)

                    # Aggregate stats per user AND count their unique days played
                    leaderboard = df_users.groupby('Username').agg(
                        Total_Wins=('Result', lambda x: (x == 'WIN').sum()),
                        Total_Losses=('Result', lambda x: (x == 'LOSS').sum()),
                        Total_Points=('Points Earned', 'sum'),
                        Days_Played=('Date', 'nunique')  # This counts the exact number of days they submitted picks!
                    ).reset_index()

                    # Calculate Win Percentage
                    total_games = leaderboard['Total_Wins'] + leaderboard['Total_Losses']
                    leaderboard['Win Percentage'] = (leaderboard['Total_Wins'] / total_games * 100).fillna(0).round(
                        1).astype(str) + '%'

                    # THE LOYALTY BONUS: Apply 25 points for every 5 days played
                    leaderboard['Loyalty_Bonus'] = (leaderboard['Days_Played'] // 5) * 25
                    leaderboard['Total_Points'] = leaderboard['Total_Points'] + leaderboard['Loyalty_Bonus']

                    # Clean up the dataframe for the Google Sheet
                    leaderboard = leaderboard.sort_values(by='Total_Points', ascending=False)
                    leaderboard = leaderboard[
                        ['Username', 'Total_Wins', 'Total_Losses', 'Win Percentage', 'Total_Points']]
                    leaderboard.columns = ['Username', 'Total Wins', 'Total Losses', 'Win Percentage', 'Total Points']

                    lb_sheet = spreadsheet.worksheet('Leaderboard')
                    lb_sheet.clear()
                    set_with_dataframe(lb_sheet, leaderboard)
                    time.sleep(3)
                    print("Leaderboard successfully pushed to cloud.")
                else:
                    print("No user picks detected. Skipping overwrite to protect sheet data.")

        # --- 3. APPEND TODAY'S PREDICTIONS ---
        today_predictions = df_raw[['date', 'Game', 'Projected Winner']].copy()
        today_predictions.rename(columns={'date': 'Date', 'Projected Winner': 'PG Projected Winner'}, inplace=True)
        today_predictions['Actual Winner'] = ""
        today_predictions['Correct'] = ""

        today_str = str(date.today())
        ledger_dates = df_ledger['Date'].astype(str).str[:10].tolist() if not df_ledger.empty else []

        if today_str in ledger_dates:
            print(f"Slate for {today_str} is already in the ledger. Skipping append to prevent duplicates.")
        else:
            ledger_sheet.append_rows(today_predictions.fillna("").values.tolist())
            time.sleep(3)
            print("Ledger successfully updated in the cloud.")

    except Exception as e:
        print(f"Failed to fetch data: {e}")
        return None


if __name__ == "__main__":
    pd.set_option('display.max_columns', None)
    slate = get_nba_daily_slate()
    if slate is not None:
        print(slate.head())