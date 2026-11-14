
import requests
import io
import os
from datetime import date, timedelta
import pandas as pd



def get_nba_daily_slate():
    print("Starting NBA Slate Updater...")

    API_KEY = "ca9280fb-7eb0-48e3-a33f-7b13192013df"
    url = "https://api.balldontlie.io/v1/games"
    headers = {"Authorization": API_KEY}
    today = date.today()

    # ---------------------------------------------------------
    # 1. FETCH PAST 7 DAYS OF GAMES (FOR REST CALCULATION)
    # ---------------------------------------------------------
    print("Calculating team rest days...")
    past_dates = [(today - timedelta(days=i)).isoformat() for i in range(1, 8)]

    try:
        past_response = requests.get(url, headers=headers, params={"dates[]": past_dates, "per_page": 100}, timeout=15)
        past_games = past_response.json().get('data', [])

        last_played = {}
        if past_games:
            past_df = pd.DataFrame(past_games)
            past_df['date'] = pd.to_datetime(past_df['date']).dt.date

            for _, row in past_df.iterrows():
                game_date = row['date']
                home = row['home_team']['name']
                visitor = row['visitor_team']['name']

                if home not in last_played or game_date > last_played[home]:
                    last_played[home] = game_date
                if visitor not in last_played or game_date > last_played[visitor]:
                    last_played[visitor] = game_date
    except Exception as e:
        print(f"Could not fetch past games: {e}")
        last_played = {}

    def get_rest_days(nickname):
        if nickname in last_played:
            return (today - last_played[nickname]).days
        return 7  # Default to 7+ days if they haven't played in the last week

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

    star_impact_map = {player: 100 - i for i, player in enumerate(espn_top_100)}

    try:
        injury_html = requests.get("https://www.basketball-reference.com/friv/injuries.fcgi").text
        injuries_df = pd.read_html(io.StringIO(injury_html))[0]

        team_injury_names = {}
        team_injury_impacts = {}

        for _, row in injuries_df.iterrows():
            player_text = str(row['Player'])
            team = str(row['Team'])

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

        # Apply Rest Days
        df['home_rest_days'] = df['home_team_nickname'].apply(get_rest_days) -1
        df['visitor_rest_days'] = df['visitor_team_nickname'].apply(get_rest_days) -1

        # Apply Notable Injured Players & Impact
        df['home_injured_stars'] = df['home_team_name'].apply(get_injured_stars)
        df['visitor_injured_stars'] = df['visitor_team_name'].apply(get_injured_stars)

        df['home_injury_impact'] = df['home_team_name'].apply(get_injury_impact)
        df['visitor_injury_impact'] = df['visitor_team_name'].apply(get_injury_impact)

        # Fetch the live standings
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
            return 0.01  # Default to prevent division by zero

        # Convert to numeric values
        df['home_win_pct'] = pd.to_numeric(df['home_team_nickname'].apply(get_win_pct), errors='coerce').fillna(0.01)
        df['visitor_win_pct'] = pd.to_numeric(df['visitor_team_nickname'].apply(get_win_pct), errors='coerce').fillna(
            0.01)
        df['home_win_pct'] = df['home_win_pct'].replace(0, 0.01)
        df['visitor_win_pct'] = df['visitor_win_pct'].replace(0, 0.01)

        # Calculate Win Rate Ratios
        df['home_win_ratio'] = df['home_win_pct'] / df['visitor_win_pct']
        df['visitor_win_ratio'] = df['visitor_win_pct'] / df['home_win_pct']

        # Calculate PG-Score
        df['home_pg_score'] = (df['home_win_ratio'] * 100) - df['home_injury_impact'] + (df['home_rest_days'] * 10)
        df['visitor_pg_score'] = (df['visitor_win_ratio'] * 100) - df['visitor_injury_impact'] + (
                    df['visitor_rest_days'] * 10)

        # Determine Projected Winner
        df['Game'] = df['home_team_name'] + " vs " + df['visitor_team_name']
        df['Projected Winner'] = df.apply(
            lambda row: row['home_team_name'] if row['home_pg_score'] > row['visitor_pg_score'] else row[
                'visitor_team_name'],
            axis=1
        )

        # ---------------------------------------------------------
        # 4. FINAL CLEANUP, LEDGER & EXPORT TO MASTER FILE
        # ---------------------------------------------------------
        df_raw = df[[
            'date', 'Game', 'Projected Winner',
            'home_team_name', 'visitor_team_name',
            'home_win_pct', 'visitor_win_pct',
            'home_win_ratio', 'visitor_win_ratio',
            'home_rest_days', 'visitor_rest_days',
            'home_injured_stars', 'visitor_injured_stars',
            'home_injury_impact', 'visitor_injury_impact',
            'home_pg_score', 'visitor_pg_score'
        ]]

        # Ensure this matches your OneDrive exact path
        file_name = "/Users/paulgomes/Library/CloudStorage/OneDrive-GeorgetownUniversity/NBA_Project/PG_Daily_Hoops.xlsx"

        # --- THE LEDGER SYSTEM ---
        try:
            # Load the existing Ledger
            df_ledger = pd.read_excel(file_name, sheet_name='Ledger')
        except ValueError:
            # If it's the first time running, create a blank Ledger
            df_ledger = pd.DataFrame(columns=['Date', 'Game', 'Projected Winner', 'Actual Winner', 'Correct'])

        # Grade any un-graded games using the past_games data you already fetched for rest days
        if not df_ledger.empty:
            for index, row in df_ledger.iterrows():
                if pd.isna(row['Actual Winner']) or row['Actual Winner'] == "":
                    # Search your past_games dictionary for a match
                    for game in past_games:
                        # BallDontLie dates usually come with timestamps, so we match the first 10 chars (YYYY-MM-DD)
                        if str(game['date'])[:10] == str(row['Date'])[:10]:
                            home_team = game['home_team']['full_name']
                            visitor_team = game['visitor_team']['full_name']

                            # Check if the teams match this row's game string
                            if home_team in row['Game'] and visitor_team in row['Game']:
                                # Determine actual winner by score
                                if game['home_team_score'] > game['visitor_team_score']:
                                    actual_winner = home_team
                                elif game['visitor_team_score'] > game['home_team_score']:
                                    actual_winner = visitor_team
                                else:
                                    actual_winner = "Tie/Unknown"

                                # Grade it
                                # Evaluate if the returned name (e.g., "Pacers") is inside the projected string (e.g., "Indiana Pacers")
                                if str(actual_winner) in str(row['Projected Winner']):
                                    df_ledger.at[index, 'Correct'] = "TRUE"
                                else:
                                    df_ledger.at[index, 'Correct'] = "FALSE"

        # Append today's predictions
        today_predictions = df_raw[['date', 'Game', 'Projected Winner']].copy()
        today_predictions.rename(columns={'date': 'Date'}, inplace=True)
        today_predictions['Actual Winner'] = ""
        today_predictions['Correct'] = ""

        # Add today to the bottom and drop duplicates in case you run the script twice in one day
        df_ledger = pd.concat([df_ledger, today_predictions], ignore_index=True)
        df_ledger = df_ledger.drop_duplicates(subset=['Date', 'Game'], keep='first')

        # --- EXPORT BOTH TABS TO EXCEL ---
        if not os.path.exists(file_name):
            with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
                df_raw.to_excel(writer, sheet_name='raw data', index=False)
                df_ledger.to_excel(writer, sheet_name='Ledger', index=False)
            print(f"Created new file: {file_name}")
        else:
            with pd.ExcelWriter(file_name, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                df_raw.to_excel(writer, sheet_name='raw data', index=False)
                df_ledger.to_excel(writer, sheet_name='Ledger', index=False)
            print(f"Success! Raw Data and Ledger safely updated in {file_name}")

        return df_raw

    except Exception as e:
        print(f"Failed to fetch data: {e}")
        return None


if __name__ == "__main__":
    pd.set_option('display.max_columns', None)
    slate = get_nba_daily_slate()
    if slate is not None:
        print(slate.head())