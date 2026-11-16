import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import json
import pytz
import datetime
import extra_streamlit_components as stx


@st.cache_data(ttl=86400)  # Caches the data for 24 hours to prevent rate-limit bans
def get_top_scorers():
    try:
        # The 2026-2027 season is labeled as 2027 in their URL system
        url = "https://www.basketball-reference.com/leagues/NBA_2027_per_game.html"

        # Read the first table on the webpage
        df = pd.read_html(url)[0]

        # Clean the data (remove repeated table headers)
        df = df[df['Player'] != 'Player']

        # Remove duplicate rows if a player gets traded (BBall-Ref lists them multiple times)
        df = df.drop_duplicates(subset='Player')

        # Convert the Points column to actual numbers, sort highest to lowest, take the top 5
        df['PTS'] = pd.to_numeric(df['PTS'])
        top_5 = df.sort_values(by='PTS', ascending=False).head(5)

        # Extract the names and combine them with commas
        return ", ".join(top_5['Player'].tolist())
    except Exception as e:
        # Safe backup list in case the site goes down or blocks the connection
        return "Giannis Antetokounmpo, Shai Gilgeous-Alexander, Luka Doncic, Nikola Jokic, Jayson Tatum"

# --- Page Configuration ---
st.set_page_config(page_title="PG's NBA Predictor", page_icon="🏀", layout="wide")
st.markdown("""
<style>
    /* 1. Import Fonts (Redaction 50 via Fontsource CDN + Inter via Google) */
    @import url('https://cdn.jsdelivr.net/npm/@fontsource/redaction-50/index.css');
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

    html, body, [class*="css"], .stApp {
        font-family: 'Inter', sans-serif !important;
        background-color: #0D0D12 !important; /* Deep charcoal background */
    }

    /* 2. Redaction 50 Headers (Bespoke Editorial style) */
    h1, h2, h3, .main-title {
        font-family: 'Redaction 50', serif !important;
        color: #F8F9FA !important;
        letter-spacing: 0.5px;
    }

    /* 3. The Main Title (With a subtle premium glow) */
    .main-title {
        text-align: center;
        border-bottom: 1px solid #2A2A35;
        padding-bottom: 15px;
        margin-bottom: 30px;
        text-shadow: 0px 4px 15px rgba(226, 183, 20, 0.15); /* Faint gold glow */
    }

    /* 4. Premium Dark Cards (Intricate, non-glass containers) */
    [data-testid="stVerticalBlock"] > div > div {
        background: linear-gradient(145deg, #15151A, #111115) !important;
        border: 1px solid #2A2A35 !important;
        border-top: 1px solid #3A3A45 !important; /* Slight top highlight for depth */
        border-radius: 6px !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4) !important;
        padding: 15px !important;
    }

    /* 5. Sharp Data Tables */
    [data-testid="stDataFrame"] {
        border-radius: 4px !important;
        border: 1px solid #2A2A35 !important;
    }

    /* 6. Clean Dividers */
    hr {
        border-top: 1px solid #2A2A35 !important;
        margin: 1.5em 0 !important;
    }
</style>

<h1 class="main-title">🏀 HoopPix</h1>
""", unsafe_allow_html=True)

# --- Initialize Cookie Manager ---
if "cookie_manager" not in st.session_state:
    st.session_state["cookie_manager"] = stx.CookieManager(key="cookies")
cookie_manager = st.session_state["cookie_manager"]


# --- Connect to Google Sheets (Cached) ---
@st.cache_resource
def init_connection():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    cred_dict = json.loads(st.secrets["google_credentials"])
    credentials = Credentials.from_service_account_info(cred_dict, scopes=scopes)
    client = gspread.authorize(credentials)
    return client.open_by_key('1mbmggxfDbYmZ_siQB5tym2gWTLUlOIhOjB3Vfcegkzo')


spreadsheet = init_connection()


# --- Fetch Data (Cached to prevent API rate limits) ---
@st.cache_data(ttl=60)  # Refreshes data every 60 seconds max
def fetch_sheet_data(sheet_name):
    return spreadsheet.worksheet(sheet_name).get_all_records()


raw_data = fetch_sheet_data('Raw_Data')
ledger_data = fetch_sheet_data('Model_Ledger')
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

        total_pg = df_today['home_pg_score'] + df_today['visitor_pg_score']
        winner_pg = df_today[['home_pg_score', 'visitor_pg_score']].max(axis=1)
        # Calculate realistic % Certainty using a margin-based smoothing formula
        margin = abs(df_today['home_pg_score'] - df_today['visitor_pg_score'])
        # Base 50% chance + up to 45% extra certainty based on the size of the margin
        df_dash['% Certainty'] = (50 + (margin / (margin + 100)) * 45).round(2).astype(str) + '%'

        st.dataframe(df_dash, use_container_width=True, hide_index=True)


        col1, col2 = st.columns(2)

        has_graded_games = False
        if not df_ledger.empty and 'Correct' in df_ledger.columns:
            graded_games = df_ledger[df_ledger['Correct'].isin(['TRUE', 'FALSE', True, False])]

            if not graded_games.empty:
                has_graded_games = True

                # 1. Tally the graded games from the cloud ledger
                ledger_wins = sum(graded_games['Correct'].astype(str).str.upper() == 'TRUE')
                ledger_losses = len(graded_games) - ledger_wins

                # 2. Add the manual Excel record (5 wins, 4 losses)
                all_time_wins = ledger_wins + 5
                all_time_losses = ledger_losses + 4

                # 3. Calculate new Win Percentage
                total_all_time_games = all_time_wins + all_time_losses
                all_time_pct = round((all_time_wins / total_all_time_games) * 100, 1) if total_all_time_games > 0 else 0

                last_date = graded_games['Date'].max()
                last_night_games = graded_games[graded_games['Date'] == last_date]
                ln_wins = sum(last_night_games['Correct'].astype(str).str.upper() == 'TRUE')
                ln_losses = len(last_night_games) - ln_wins

                with col1:
                    st.metric("Our Table's Record Last Night", f"{ln_wins}-{ln_losses}")
                with col2:
                    st.metric("Our Table's Record All Time", f"{all_time_wins}-{all_time_losses} ({all_time_pct}%)")

            if not has_graded_games:
                st.markdown("*Record will calculate after the first slate is graded tomorrow morning.*")

                # 1. Fetch the messages from Google Sheets
            editor_msg = "Welcome to the predictor! Check back tomorrow for updates."
            deadline_msg = "PICK SUBMISSIONS WILL BE DUE BEFORE THE GAME STARTS"

            try:
                # Row 1: Deadline info
                base_deadline = spreadsheet.worksheet('Editor_Note').acell('A1').value
                cutoff_time = spreadsheet.worksheet('Editor_Note').acell('B1').value
                deadline_msg = f"{base_deadline} ({cutoff_time} EST)"

                # Row 2: Editor's Note (No more overlapping text!)
                editor_msg = spreadsheet.worksheet('Editor_Note').acell('A2').value
            except:
                pass

            # 2. Minimalist Text Layout (No more st.info boxes)
            st.divider()  # Creates a clean 1px horizontal line
            st.markdown(f"**Editor's Note:** {editor_msg}")
            st.markdown(f"*{deadline_msg}*")
            st.divider()


# ==========================================
# TAB 2: THE DEEP ANALYTICS
# ==========================================
with tab2:
    st.subheader("Selected Stats & Advanced Metrics")
    if not df_today.empty:
        # Safety check: Prevent app crash if the backend script hasn't pushed the new columns yet
        if 'home_heat_emoji' not in df_today.columns:
            df_today['home_heat_emoji'] = "TBD"
            df_today['visitor_heat_emoji'] = "TBD"

        detailed_df = df_today[[
            'Game',
            'home_team_name', 'home_heat_emoji', 'home_win_ratio', 'home_rest_days',
            'home_injured_stars', 'home_injury_impact', 'home_pg_score',
            'visitor_team_name', 'visitor_heat_emoji', 'visitor_win_ratio', 'visitor_rest_days',
            'visitor_injured_stars', 'visitor_injury_impact', 'visitor_pg_score'
        ]].copy()

        detailed_df.rename(columns={
            'home_team_name': 'Home Team',
            'home_heat_emoji': 'Home Heat',
            'home_win_ratio': 'Home Win Ratio',
            'home_rest_days': 'Home Rest',
            'home_injured_stars': 'Home Injuries',
            'home_injury_impact': 'Home Injury Impact',
            'home_pg_score': 'Home PG-Score',
            'visitor_team_name': 'Visitor Team',
            'visitor_heat_emoji': 'Visitor Heat',
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

        # --- DYNAMIC CUTOFF TIME ---
        cutoff_str = "19:00"  # Default to 7:00 PM
        try:
            # Pull the dynamic time from cell B1
            val = spreadsheet.worksheet('Editor_Note').acell('B1').value
            if val:
                cutoff_str = val.strip()
        except Exception:
            pass  # Fails gracefully if B1 is empty

        # Parse the string (e.g., "15:30") into hours and minutes
        try:
            cutoff_hour, cutoff_min = map(int, cutoff_str.split(':'))
        except ValueError:
            cutoff_hour, cutoff_min = 19, 0  # Failsafe in case of a typo in the sheet

        eastern = pytz.timezone('US/Eastern')
        now_est = datetime.datetime.now(eastern)
        cutoff_time = now_est.replace(hour=cutoff_hour, minute=cutoff_min, second=0, microsecond=0)

        if now_est > cutoff_time:
            # Format to standard 12-hour time for the error message
            display_time = cutoff_time.strftime('%I:%M %p').lstrip('0')
            st.error(f"🔒 Picks are locked! Today's cutoff was {display_time} EST. Come back tomorrow.")
        elif cookie_manager.get(cookie="submitted_today"):
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

                # --- NEW PROP PICK CODE GOES HERE ---
                st.divider() # Adds a clean line to separate the games from the prop bet
                top_5_list = get_top_scorers()
                st.markdown("### 🎯 Daily Prop Pick")
                st.write(f"Who will score the most points tonight outside of: **{top_5_list}**?")
                top_scorer_guess = st.text_input("Enter player name:")
                # ------------------------------------

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
                                # Added top_scorer_guess to the very end of this list!
                                rows_to_append.append(
                                    [today_str, username.strip(), game, pick, "", 0, top_scorer_guess])

                            user_picks_sheet.append_rows(rows_to_append)

                            expire_date = datetime.datetime.now() + datetime.timedelta(days=1)
                            cookie_manager.set("submitted_today", "true", expires_at=expire_date)

                            st.success(
                                f"Picks locked in for {username.strip()}! (Refresh to see the tracker in action)")
                            st.balloons()

    with col_leaderboard:
        st.subheader("🏆 Community Leaderboard")
        leaderboard_data = fetch_sheet_data('Leaderboard')
        if leaderboard_data:
            df_leaderboard = pd.DataFrame(leaderboard_data)
            st.dataframe(df_leaderboard, use_container_width=True, hide_index=True)
        else:
            st.info("The leaderboard is currently empty.")