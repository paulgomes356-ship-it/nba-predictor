import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import json

# --- Page Configuration ---
st.set_page_config(page_title="PG's NBA Predictor", page_icon="🏀", layout="wide")
st.title("🏀 PG's Daily NBA Predictor")

# --- Connect to Google Sheets ---
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
cred_dict = json.loads(st.secrets["google_credentials"])
credentials = Credentials.from_service_account_info(cred_dict, scopes=scopes)
client = gspread.authorize(credentials)

sheet_id = '1mbmggxfDbYmZ_siQB5tym2gWTLUlOIhOjB3Vfcegkzo'
spreadsheet = client.open_by_key(sheet_id)

# --- Fetch Data ---
raw_data = spreadsheet.worksheet('Raw_Data').get_all_records()
ledger_data = spreadsheet.worksheet('Model_Ledger').get_all_records()
df_today = pd.DataFrame(raw_data) if raw_data else pd.DataFrame()
df_ledger = pd.DataFrame(ledger_data) if ledger_data else pd.DataFrame()

# --- Create Navigation Tabs ---
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📈 Selected Stats", "🏆 Picks & Leaderboard"])

# ==========================================
# TAB 1: THE EXCEL DASHBOARD CLONE
# ==========================================
with tab1:
    st.subheader("Tonight's Slate & PG Projections")

    if not df_today.empty:
        # 1. Recreate the Clean Dashboard View
        df_dash = df_today[['Game', 'Projected Winner']].copy()

        # Calculate % Certainty from the PG-Scores
        total_pg = df_today['home_pg_score'] + df_today['visitor_pg_score']
        winner_pg = df_today[['home_pg_score', 'visitor_pg_score']].max(axis=1)
        df_dash['% Certainty'] = ((winner_pg / total_pg) * 100).round(2).astype(str) + '%'

        st.dataframe(df_dash, use_container_width=True, hide_index=True)

        st.markdown("---")

        # 2. Recreate the Model's Record Section
        col1, col2 = st.columns(2)

        if not df_ledger.empty and 'Correct' in df_ledger.columns:
            # Filter to only games that have been graded (TRUE/FALSE)
            graded_games = df_ledger[df_ledger['Correct'].isin(['TRUE', 'FALSE', True, False])]

            if not graded_games.empty:
                # All-Time Record
                all_time_wins = sum(graded_games['Correct'].astype(str).str.upper() == 'TRUE')
                all_time_losses = len(graded_games) - all_time_wins
                all_time_pct = round((all_time_wins / len(graded_games)) * 100, 1)

                # Last Night's Record
                last_date = graded_games['Date'].max()
                last_night_games = graded_games[graded_games['Date'] == last_date]
                ln_wins = sum(last_night_games['Correct'].astype(str).str.upper() == 'TRUE')
                ln_losses = len(last_night_games) - ln_wins

                with col1:
                    st.metric("Our Table's Record Last Night", f"{ln_wins}-{ln_losses}")
                with col2:
                    st.metric("Our Table's Record All Time", f"{all_time_wins}-{all_time_losses} ({all_time_pct}%)")
        else:
            st.info("Record will calculate after the first slate is graded.")

        # 3. Editor's Thoughts
        st.markdown("### About last night...(thoughts from the editor):")
        st.info(
            "Last night was certainly an interesting one to start my predictor on, so many crazy upsets! I'll keep updating the formula so keep an eye out.")
    else:
        st.info("Today's games haven't been loaded yet. Check back later!")

# ==========================================
# TAB 2: THE DEEP ANALYTICS
# ==========================================
with tab2:
    st.subheader("Selected Stats & Advanced Metrics")
    if not df_today.empty:
        # Recreate the detailed view with the nitty-gritty stats
        detailed_cols = [
            'Game', 'home_win_ratio', 'visitor_win_ratio',
            'home_rest_days', 'visitor_rest_days',
            'home_injured_stars', 'visitor_injured_stars',
            'home_injury_impact', 'visitor_injury_impact',
            'home_pg_score', 'visitor_pg_score'
        ]
        st.dataframe(df_today[detailed_cols], use_container_width=True, hide_index=True)
    else:
        st.info("Awaiting today's data pipeline execution.")

# ==========================================
# TAB 3: COMMUNITY PICKS & LEADERBOARD
# ==========================================
with tab3:
    col_form, col_leaderboard = st.columns([1, 1])

    with col_form:
        st.subheader("Make Your Picks!")
        username = st.text_input("Enter your Username:", placeholder="e.g., PG_Hoops_Fan")

        with st.form("daily_picks_form"):
            user_selections = {}
            if not df_today.empty:
                for index, row in df_today.iterrows():
                    game_name = row['Game']
                    home_team = row['home_team_name']
                    away_team = row['visitor_team_name']

                    choice = st.radio(f"**{game_name}**", options=[home_team, away_team], horizontal=True)
                    user_selections[game_name] = choice

            submitted = st.form_submit_button("Lock in my picks!")

            if submitted:
                if username.strip() == "":
                    st.error("⚠️ Please enter a username before submitting!")
                else:
                    user_picks_sheet = spreadsheet.worksheet('User_Picks')
                    rows_to_append = []
                    today_str = df_today.iloc[0]['date']
                    for game, pick in user_selections.items():
                        rows_to_append.append([today_str, username, game, pick, "", 0])
                    user_picks_sheet.append_rows(rows_to_append)
                    st.success(f"Picks locked in for {username}!")
                    st.balloons()

    with col_leaderboard:
        st.subheader("🏆 Community Leaderboard")
        leaderboard_data = spreadsheet.worksheet('Leaderboard').get_all_records()
        if leaderboard_data:
            df_leaderboard = pd.DataFrame(leaderboard_data)
            st.dataframe(df_leaderboard, use_container_width=True, hide_index=True)
        else:
            st.info("The leaderboard is currently empty.")