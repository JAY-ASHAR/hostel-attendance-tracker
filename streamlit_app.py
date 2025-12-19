# ================================
# Hostel Attendance Tracker
# Cloud-safe (Google Sheets)
# ================================

import os
import json
from datetime import date
from typing import Dict, List
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

import gspread
from google.oauth2.service_account import Credentials



import streamlit as st
from google.oauth2.service_account import Credentials
import streamlit as st
from google.oauth2.service_account import Credentials
import gspread

st.write("Secrets keys:", st.secrets.keys())

try:
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    st.success("✅ Google Sheets authentication successful")
except Exception as e:
    st.error("❌ Authentication failed")
    st.exception(e)
# ---------- CONFIG ----------
APP_TITLE = "🏠 Hostel Attendance Tracker"

SESSIONS = ["Morning", "Night"]
STATUS_OPTIONS = ["P", "A", "L", "S", "SCH/CLG", "OI"]

DATA_DIR = "data"
STUDENTS_CSV = os.path.join(DATA_DIR, "students.csv")
LOCKS_JSON = os.path.join(DATA_DIR, "locks.json")

SHEET_ID = "1kvMmd9jXZOLrIVzXlmBloSzN1Zkj3t7KKjmBrTEtieA"
ATTENDANCE_SHEET = "Attendance"

USERS = {
    "warden1": {"password": "1234", "role": "admin", "name": "Warden 1"},
    "warden2": {"password": "1234", "role": "admin", "name": "Warden 2"},
    "morning": {"password": "1111", "role": "operator", "name": "Morning Operator"},
    "night": {"password": "2222", "role": "operator", "name": "Night Operator"},
}

# ---------- BASIC FILE SETUP ----------
def ensure_files():
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(STUDENTS_CSV):
        pd.DataFrame([
            {"student_id": 1, "name": "Student One", "active": True},
            {"student_id": 2, "name": "Student Two", "active": True},
        ]).to_csv(STUDENTS_CSV, index=False)

    if not os.path.exists(LOCKS_JSON):
        with open(LOCKS_JSON, "w") as f:
            json.dump({}, f)

# ---------- STUDENTS ----------
def load_students():
    df = pd.read_csv(STUDENTS_CSV)
    return df[df["active"] == True].copy()

def save_students(df):
    df.to_csv(STUDENTS_CSV, index=False)

# ---------- LOCKS ----------
def locks_read():
    with open(LOCKS_JSON) as f:
        return json.load(f)

def locks_write(data):
    with open(LOCKS_JSON, "w") as f:
        json.dump(data, f, indent=2)

def is_session_locked(day, session):
    return locks_read().get(day, {}).get(session, False)

def lock_session(day, session):
    locks = locks_read()
    locks.setdefault(day, {})[session] = True
    locks_write(locks)

def unlock_session(day, session):
    locks = locks_read()
    if day in locks and session in locks[day]:
        locks[day][session] = False
        locks_write(locks)

# ---------- GOOGLE SHEETS ----------
def get_gsheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet(ATTENDANCE_SHEET)

def append_attendance(df_long):
    if df_long.empty:
        return
    ws = get_gsheet()
    ws.append_rows(df_long.values.tolist(), value_input_option="USER_ENTERED")

# ---------- DATA TRANSFORM ----------
def daily_to_long(df, day):
    rows = []
    for _, r in df.iterrows():
        for sess in SESSIONS:
            rows.append([
                day,
                int(r["student_id"]),
                r["name"],
                sess,
                r[sess]
            ])
    return pd.DataFrame(rows, columns=["date","student_id","name","session","status"])

# ---------- LOAD ATTENDANCE ----------
@st.cache_data(ttl=60)
def load_all_attendance():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={ATTENDANCE_SHEET}"
    df = pd.read_csv(url)
    if df.empty:
        return df
    df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
    df["month"] = df["date_dt"].dt.strftime("%Y-%m")
    return df

# ---------- LOGIN ----------
def login_ui():
    st.title(APP_TITLE)
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        user = USERS.get(u)
        if user and user["password"] == p:
            st.session_state.user = {**user, "username": u}
            st.rerun()
        else:
            st.error("Invalid login")

# ---------- ATTENDANCE PAGE ----------
def take_attendance():
    st.header("📝 Take Attendance")
    day = st.date_input("Date", date.today()).strftime("%Y-%m-%d")

    students = load_students()
    df = students[["student_id","name"]].copy()
    for s in SESSIONS:
        df[s] = ""

    session = st.selectbox("Session", SESSIONS)
    if is_session_locked(day, session):
        st.warning("Session locked")
        return

    for i, r in df.iterrows():
        df.at[i, session] = st.radio(
            r["name"],
            STATUS_OPTIONS,
            horizontal=True,
            key=f"{day}_{session}_{i}"
        )

    if st.button("Submit & Lock"):
        long_df = daily_to_long(df, day)
        append_attendance(long_df)
        lock_session(day, session)
        st.cache_data.clear()
        st.success("Attendance saved & locked")
        st.rerun()

# ---------- ANALYTICS ----------
def analytics():
    st.header("📊 Analytics")
    df = load_all_attendance()
    if df.empty:
        st.info("No data")
        return

    month = st.selectbox("Month", ["All"] + sorted(df["month"].dropna().unique()))
    if month != "All":
        df = df[df["month"] == month]

    counts = df["status"].value_counts().reindex(STATUS_OPTIONS, fill_value=0)
    st.bar_chart(counts)

# ---------- MAIN ----------
def main():
    st.set_page_config(APP_TITLE, layout="wide")
    ensure_files()

    if "user" not in st.session_state:
        login_ui()
        return

    st.sidebar.title("Menu")
    choice = st.sidebar.radio("Go to", ["Take Attendance", "Analytics"])

    if choice == "Take Attendance":
        take_attendance()
    else:
        analytics()

if __name__ == "__main__":
    main()
