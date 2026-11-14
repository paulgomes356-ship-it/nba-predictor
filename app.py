import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import json
import datetime
import extra_streamlit_components as stx

# --- Page Configuration ---
st.set_page_config(page_title="PG's NBA Predictor", page_icon="🏀", layout="wide")
st.title("🏀 PG's Daily NBA Predictor")

# --- Initialize Cookie Manager ---
if "cookie_manager" not in st.session_state:
    st.session_state["cookie_manager"] = stx.CookieManager(key="cookies")
cookie_manager = st.session_state["cookie_manager"]

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
        df_dash = df_today[['Game', 'Projected Winner']].copy()

        # Calculate % Certainty from the PG-Scores
        total_pg = df_today['home_pg_score'] + df_today['visitor_pg_score']
        winner_pg = df_today[['home_pg_score', 'visitor_pg_score']].max(axis=1)
        df_dash['% Certainty'] = ((winner_pg / total_pg) * 100).round(2).astype(str) + '%'

        st.dataframe(df_dash, use_container_width=True, hide_index=True)

        st.markdown("---")

        col1, col2 = st.columns(2)

        has_graded_games = False
        if not df_ledger.empty and 'Correct' in df_ledger.columns:
            graded_games = df_ledger[df_ledger['Correct'].isin(['TRUE', 'FALSE', True, False])]

            if not graded_games.empty:
                has_graded_games = True
                all_time_wins = sum(graded_games['Correct'].astype(str).str.upper() == 'TRUE')
                all_time_losses = len(graded_games) - all_time_wins
                all_time_pct = round((all_time_wins / len(graded_games)) * 100, 1)

                last_date = graded_games['Date'].max()
                last_night_games = graded_games[graded_games['Date'] == last_date]
                ln_wins = sum(last_night_games['Correct'].astype(str).str.upper() == 'TRUE')
                ln_losses = len(last_night_games) - ln_wins

                with col1:
                    st.metric("Our Table's Record Last Night", f"{ln_wins}-{ln_losses}")
                with col2:
                    st.metric("Our Table's Record All Time", f"{all_time_wins}-{all_time_losses} ({all_time_pct}%)")

        if not has_graded_games:
            st.info("Record will calculate after the first slate is graded tomorrow morning.")

        st.markdown("### About last night...(thoughts from the editor):")
        editor_msg = "Welcome to the predictor! Check back tomorrow for updates."
        try:
            msg_val = spreadsheet.worksheet('Editor_Note').acell('A1').value
            if msg_val:
                editor_msg = msg_val
        except Exception:
            pass

        st.info(editor_msg)
    else:
        st.info("Today's games haven't been loaded yet. Check back later!")

# ==========================================
# TAB 2: THE DEEP ANALYTICS
# ==========================================
with tab2:
    st.subheader("Selected Stats & Advanced Metrics")
    if not df_today.empty:
        detailed_df = df_today[[
            'Game',
            'home_team_name', 'home_win_ratio', 'home_rest_days', 'home_injured_stars', 'home_injury_impact',
            'home_pg_score',
            'visitor_team_name', 'visitor_win_ratio', 'visitor_rest_days', 'visitor_injured_stars',
            'visitor_injury_impact', 'visitor_pg_score'
        ]].copy()

        detailed_df.rename(columns={
            'home_team_name': 'Home Team',
            'home_win_ratio': 'Home Win Ratio',
            'home_rest_days': 'Home Rest',
            'home_injured_stars': 'Home Injuries',
            'home_injury_impact': 'Home Injury Impact',
            'home_pg_score': 'Home PG-Score',
            'visitor_team_name': 'Visitor Team',
            'visitor_win_ratio': 'Visitor Win Ratio',
            'visitor_rest_days': 'Visitor Rest',
            'visitor_injured_stars': 'Visitor Injuries',
            'visitor_injury_impact': 'Visitor Injury Impact',
            'visitor_pg_score': 'Visitor PG-Score'
        }, inplace=True)

        st.dataframe(detailed_df, use_container_width=True, hide_index=True)
    else:
        st.info("Awaiting today's data pipeline execution.")

# ==========================================
# TAB 3: COMMUNITY PICKS & LEADERBOARD
# ==========================================
with tab3:
    col_form, col_leaderboard = st.columns([1, 1])

    with col_form:
        st.subheader("Make Your Picks!")

        if cookie_manager.get(cookie="submitted_today"):
            st.success("🎉 You've already locked in your picks for today! Come back tomorrow to see the results.")
        else:
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
                        today_str = df_today.iloc[0]['date']

                        existing_picks = user_picks_sheet.get_all_records()
                        already_submitted = False

                        if existing_picks:
                            df_existing = pd.DataFrame(existing_picks)
                            today_submissions = df_existing[df_existing['Date'].astype(str) == str(today_str)]
                            existing_users = today_submissions['Username'].astype(str).str.strip().str.lower().tolist()
                            if username.strip().lower() in existing_users:
                                already_submitted = True

                        if already_submitted:
                            st.error(f"⚠️ Hold up! '{username}' has already submitted picks for today.")
                        else:
                            rows_to_append = []
                            for game, pick in user_selections.items():
                                rows_to_append.append([today_str, username.strip(), game, pick, "", 0])

                            user_picks_sheet.append_rows(rows_to_append)

                            expire_date = datetime.datetime.now() + datetime.timedelta(days=1)
                            cookie_manager.set("submitted_today", "true", expires_at=expire_date)

                            st.success(
                                f"Picks locked in for {username.strip()}! (Refresh to see the tracker in action)")
                            st.balloons()

    with col_leaderboard:
        st.subheader("🏆 Community Leaderboard")
        leaderboard_data = spreadsheet.worksheet('Leaderboard').get_all_records()
        if leaderboard_data:
            df_leaderboard = pd.DataFrame(leaderboard_data)
            st.dataframe(df_leaderboard, use_container_width=True, hide_index=True)
        else:
            st.info("The leaderboard is currently empty.")