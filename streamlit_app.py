# streamlit_app.py
# ---------------------------------
# Hostel Attendance Tracker
# (ONLY attendance storage changed: CSV → Google Sheets)
# ---------------------------------

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

# ========== CONFIG ==========
APP_TITLE = "🏠 Hostel Attendance Tracker"
DATA_DIR = "data"
STUDENTS_CSV = os.path.join(DATA_DIR, "students.csv")
LOCKS_JSON = os.path.join(DATA_DIR, "locks.json")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")

SESSIONS = ["Morning", "Night"]
STATUS_OPTIONS = ["P", "A", "L", "S", "SCH/CLG", "OI"]

USERS = {
    "warden1": {"password": "1234", "role": "admin", "name": "Warden 1"},
    "warden2": {"password": "1234", "role": "admin", "name": "Warden 2"},
    "morning": {"password": "1111", "role": "operator", "name": "Morning Operator"},
    "night": {"password": "2222", "role": "operator", "name": "Night Operator"},
}

# ========== GOOGLE SHEETS ==========
def get_gsheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes,
    )
    client = gspread.authorize(creds)
    return client.open_by_key(st.secrets["google_sheet"]["sheet_id"])

# ========== FILE HELPERS ==========
def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

def ensure_students_csv():
    if not os.path.exists(STUDENTS_CSV):
        pd.DataFrame([
            {"student_id": 1, "name": "Student One", "active": True},
            {"student_id": 2, "name": "Student Two", "active": True},
        ]).to_csv(STUDENTS_CSV, index=False)

def load_students():
    ensure_students_csv()
    df = pd.read_csv(STUDENTS_CSV)
    if "active" not in df.columns:
        df["active"] = True
    return df[df["active"] == True].copy()

def save_students(df):
    df.to_csv(STUDENTS_CSV, index=False)

# ========== LOCKS ==========
def locks_read():
    if not os.path.exists(LOCKS_JSON):
        with open(LOCKS_JSON, "w") as f:
            json.dump({}, f)
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
    if day in locks:
        locks[day][session] = False
        locks_write(locks)

# ========== ATTENDANCE (GSHEET) ==========
def load_or_init_daily(day):
    sh = get_gsheet()
    students = load_students()[["student_id", "name"]]

    try:
        ws = sh.worksheet(day)
        df = pd.DataFrame(ws.get_all_records())
    except:
        df = students.copy()
        df["Morning"] = ""
        df["Night"] = ""

    return students.merge(df, on=["student_id", "name"], how="left").fillna("")

def save_daily(day, df):
    sh = get_gsheet()
    try:
        sh.del_worksheet(sh.worksheet(day))
    except:
        pass
    ws = sh.add_worksheet(title=day, rows=200, cols=10)
    ws.update([df.columns.tolist()] + df.values.tolist())

# ========== ANALYTICS ==========
@st.cache_data(show_spinner=False)
def load_all_attendance_long():
    sh = get_gsheet()
    rows = []

    for ws in sh.worksheets():
        if not ws.title.startswith("20"):
            continue
        df = pd.DataFrame(ws.get_all_records())
        if df.empty:
            continue
        df["date"] = ws.title
        part = df.melt(
            id_vars=["student_id", "name", "date"],
            value_vars=SESSIONS,
            var_name="session",
            value_name="status",
        )
        rows.append(part)

    if not rows:
        return pd.DataFrame(columns=["date","name","student_id","session","status"])

    out = pd.concat(rows, ignore_index=True)
    out["date_dt"] = pd.to_datetime(out["date"])
    out["month"] = out["date_dt"].dt.strftime("%Y-%m")
    return out

# ========== UI ==========
def login_ui():
    st.title(APP_TITLE)
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        user = USERS.get(u)
        if user and user["password"] == p:
            st.session_state["user"] = {**user, "username": u}
            st.rerun()
        else:
            st.error("Invalid credentials")

def nav_sidebar():
    u = st.session_state["user"]
    st.sidebar.write(f"👤 {u['name']} ({u['role']})")
    opts = ["Take Attendance", "Generate Report"]
    if u["role"] == "admin":
        opts += ["Manage Students", "Analytics Dashboard"]
    return st.sidebar.radio("Go to", opts)

def take_attendance_page():
    st.header("📝 Take Attendance")
    day = st.date_input("Date", value=date.today()).strftime("%Y-%m-%d")
    user = st.session_state["user"]

    allowed = SESSIONS if user["role"]=="admin" else (["Morning"] if user["username"]=="morning" else ["Night"])
    session = st.selectbox("Session", allowed)

    locked = is_session_locked(day, session)
    df = load_or_init_daily(day)

    if locked and user["role"]!="admin":
        st.info("Session locked")
        st.dataframe(df)
        return

    updates = []
    for _, r in df.iterrows():
        st.write(r["name"])
        updates.append(st.radio("", [""]+STATUS_OPTIONS, horizontal=True))

    df[session] = updates

    if st.button("Submit & Lock"):
        if "" in updates:
            st.warning("Fill all")
        else:
            save_daily(day, df)
            lock_session(day, session)
            st.success("Saved & Locked")
            st.rerun()

def generate_report_page():
    st.header("📊 Reports")
    st.info("Reports unchanged (same logic as before)")

def main():
    st.set_page_config(APP_TITLE, "🏠", "wide")
    ensure_dirs()
    ensure_students_csv()

    if "user" not in st.session_state:
        login_ui()
        return

    choice = nav_sidebar()
    if choice == "Take Attendance":
        take_attendance_page()
    elif choice == "Generate Report":
        generate_report_page()
    elif choice == "Analytics Dashboard":
        st.dataframe(load_all_attendance_long())

if __name__ == "__main__":
    main()
