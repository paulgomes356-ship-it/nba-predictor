import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import json

# --- Page Configuration ---
st.set_page_config(page_title="PG's NBA Predictor", page_icon="🏀", layout="wide")
st.title("🏀 PG's Daily NBA Predictor")
st.write("Welcome to the community leaderboard. Check today's projections and make your picks!")

# --- Connect to Google Sheets ---
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

# Pull the JSON key from Streamlit's secure cloud vault instead of your Mac
cred_dict = json.loads(st.secrets["google_credentials"])
credentials = Credentials.from_service_account_info(cred_dict, scopes=scopes)
client = gspread.authorize(credentials)

sheet_id = '1mbmggxfDbYmZ_siQB5tym2gWTLUlOIhOjB3Vfcegkzo'
spreadsheet = client.open_by_key(sheet_id)

sheet_id = '1mbmggxfDbYmZ_siQB5tym2gWTLUlOIhOjB3Vfcegkzo'
spreadsheet = client.open_by_key(sheet_id)

# --- Fetch and Display Today's Slate ---
st.subheader("Tonight's Slate & PG Projections")
raw_data = spreadsheet.worksheet('Raw_Data').get_all_records()

if raw_data:
    df_today = pd.DataFrame(raw_data)
    # Filter the dataframe to just the cleanest columns for the users to see
    display_columns = ['Game', 'Projected Winner', 'home_win_pct', 'visitor_win_pct', 'home_pg_score',
                       'visitor_pg_score']

    # Display a modern, interactive table
    st.dataframe(df_today[display_columns], use_container_width=True, hide_index=True)
else:
    st.info("Today's games haven't been loaded yet. Check back later!")

# --- User Picks Section ---
st.markdown("---")
st.subheader("Make Your Picks!")

# Ask for a username
username = st.text_input("Enter your Username:", placeholder="e.g., PG_Hoops_Fan")

# Create a form so the page doesn't refresh until they hit submit
with st.form("daily_picks_form"):
    st.write("Select the winner for each matchup below:")

    user_selections = {}

    # Loop through today's games to create a radio button for each one
    if raw_data:
        for index, row in df_today.iterrows():
            game_name = row['Game']
            home_team = row['home_team_name']
            away_team = row['visitor_team_name']

            # Display options side-by-side
            choice = st.radio(
                f"**{game_name}**",
                options=[home_team, away_team],
                horizontal=True
            )
            user_selections[game_name] = choice

    # The submission button
    submitted = st.form_submit_button("Lock in my picks!")

    if submitted:
        if username.strip() == "":
            st.error("⚠️ Please enter a username before submitting!")
        else:
            # Prepare the data for Google Sheets
            user_picks_sheet = spreadsheet.worksheet('User_Picks')
            rows_to_append = []

            # Grab today's date from the first row of your raw data
            today_str = df_today.iloc[0]['date']

            # Format the data to match your User_Picks headers
            for game, pick in user_selections.items():
                # Order: Date, Username, Game, User Pick, Result, Points Earned
                rows_to_append.append([today_str, username, game, pick, "", 0])

            # Push all picks to the cloud in one batch
            user_picks_sheet.append_rows(rows_to_append)

            st.success(f"Picks locked in for {username}! Check the Leaderboard tomorrow.")
            st.balloons()

# --- Community Leaderboard Section ---
st.markdown("---")
st.subheader("🏆 Community Leaderboard")

# Fetch the Leaderboard tab from Google Sheets
leaderboard_data = spreadsheet.worksheet('Leaderboard').get_all_records()

if leaderboard_data:
    df_leaderboard = pd.DataFrame(leaderboard_data)

    # Optional: Highlight the top score by styling the dataframe
    st.dataframe(
        df_leaderboard,
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("The leaderboard is currently empty. Check back tomorrow after the first round of picks is graded!")