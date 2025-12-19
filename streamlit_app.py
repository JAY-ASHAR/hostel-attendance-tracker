import streamlit as st
import pandas as pd
from datetime import date
import matplotlib.pyplot as plt

import gspread
from google.oauth2.service_account import Credentials

# ================= CONFIG =================
APP_TITLE = "🏠 Hostel Attendance Tracker"

SESSIONS = ["Morning", "Night"]
STATUS_OPTIONS = ["P", "A", "L", "S", "SCH/CLG", "OI"]

SHEET_ID = "1kvMmd9jXZOLrIVzXlmBloSzN1Zkj3t7KKjmBrTEtieA"
SHEET_NAME = "Attendance"

USERS = {
    "warden1": {"password": "1234", "role": "admin"},
    "warden2": {"password": "1234", "role": "admin"},
    "morning": {"password": "1111", "role": "operator", "session": "Morning"},
    "night": {"password": "2222", "role": "operator", "session": "Night"},
}

# ================= GOOGLE SHEETS =================
def get_sheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

# ================= AUTH =================
def login():
    st.title(APP_TITLE)
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        user = USERS.get(u)
        if user and user["password"] == p:
            st.session_state.user = {**user, "username": u}
            st.rerun()
        else:
            st.error("Invalid credentials")

# ================= ATTENDANCE =================
def take_attendance():
    st.header("📝 Take Attendance")

    sheet = get_sheet()
    today = st.date_input("Date", date.today()).strftime("%Y-%m-%d")

    user = st.session_state.user
    if user["role"] == "admin":
        session = st.selectbox("Session", SESSIONS)
    else:
        session = user["session"]
        st.info(f"Session: {session}")

    students = sheet.get_all_records()
    df = pd.DataFrame(students)

    # get unique students
    students_df = df[["student_id", "name"]].drop_duplicates()

    marks = {}
    for _, r in students_df.iterrows():
        marks[r["student_id"]] = st.radio(
            r["name"], STATUS_OPTIONS, horizontal=True
        )

    if st.button("Submit"):
        rows = []
        for sid, status in marks.items():
            name = students_df.loc[students_df["student_id"] == sid, "name"].values[0]
            rows.append([today, sid, name, session, status])

        sheet.append_rows(rows)
        st.success("Attendance saved")

# ================= ANALYTICS =================
def analytics():
    st.header("📊 Analytics")

    df = pd.read_csv(
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"
    )

    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.strftime("%Y-%m")

    month = st.selectbox("Month", ["All"] + sorted(df["month"].unique()))
    session = st.selectbox("Session", SESSIONS)

    if month != "All":
        df = df[df["month"] == month]

    counts = (
        df[df["session"] == session]["status"]
        .value_counts()
        .reindex(STATUS_OPTIONS, fill_value=0)
    )

    fig, ax = plt.subplots()
    counts.plot(kind="bar", ax=ax)
    ax.set_ylabel("Count")
    st.pyplot(fig)

# ================= MAIN =================
def main():
    st.set_page_config(APP_TITLE, layout="wide")

    if "user" not in st.session_state:
        login()
        return

    st.sidebar.title("Menu")
    page = st.sidebar.radio("Go to", ["Take Attendance", "Analytics"])
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    if page == "Take Attendance":
        take_attendance()
    else:
        analytics()

if __name__ == "__main__":
    main()
