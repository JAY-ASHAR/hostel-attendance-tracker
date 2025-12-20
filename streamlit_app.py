# =========================================================
# Hostel Attendance Tracker (Google Sheets Only)
# Single-file, Clean & Stable
# =========================================================

import streamlit as st
import pandas as pd
from datetime import date
from io import BytesIO
import gspread
from google.oauth2.service_account import Credentials

# ---------------- CONFIG ----------------
APP_TITLE = "🏠 Hostel Attendance Tracker"
SHEET_ID = "1kvMmd9jXZOLrIVzXlmBloSzN1Zkj3t7KKjmBrTEtieA"

SESSIONS = ["Morning", "Night"]
STATUS_OPTIONS = ["P", "A", "L", "S", "SCH/CLG", "OI"]

USERS = {
    "warden1": {"password": "1234", "role": "admin"},
    "warden2": {"password": "1234", "role": "admin"},
    "morning": {"password": "1111", "role": "operator", "session": "Morning"},
    "night": {"password": "2222", "role": "operator", "session": "Night"},
}

# ---------------- GOOGLE SHEETS ----------------
@st.cache_resource
def get_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)

def get_sheet(name):
    return get_client().open_by_key(SHEET_ID).worksheet(name)

# ---------------- AUTH ----------------
def login():
    st.title(APP_TITLE)
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        user = USERS.get(u)
        if user and user["password"] == p:
            st.session_state.user = {"username": u, **user}
            st.rerun()
        else:
            st.error("Invalid login")

def logout():
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

def admin_only():
    if st.session_state.user["role"] != "admin":
        st.error("Admin only")
        st.stop()

# ---------------- DATA ----------------
def load_students(active_only=True):
    df = pd.DataFrame(get_sheet("Students").get_all_records())
    df.columns = [c.strip().lower() for c in df.columns]
    if active_only:
        df = df[df["active"] == True]
    return df

@st.cache_data(ttl=300)
def load_attendance():
    df = pd.DataFrame(get_sheet("Attendance").get_all_records())
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").astype(str)
    return df

@st.cache_data(ttl=30)
def is_locked(day, session):
    try:
        rows = get_sheet("Locks").get_all_records()
        for r in rows:
            if str(r.get("date")) == day and r.get("session") == session:
                return bool(r.get("locked"))
        return False
    except:
        return False

def set_lock(day, session, locked=True):
    ws = get_sheet("Locks")
    rows = ws.get_all_records()

    for idx, r in enumerate(rows, start=2):
        if str(r.get("date")) == day and r.get("session") == session:
            ws.update(f"C{idx}", locked)
            return

    ws.append_row([day, session, locked])

# ---------------- ATTENDANCE ----------------
def take_attendance():
    user = st.session_state.user
    st.header("📝 Take Attendance")

    day = st.date_input("Date", date.today()).strftime("%Y-%m-%d")
    session = user["session"] if user["role"] == "operator" else st.selectbox("Session", SESSIONS)

    if is_locked(day, session) and user["role"] != "admin":
        st.warning("🔒 This session is locked")
        return

    students = load_students()
    if students.empty:
        st.warning("No active students")
        return

    if "attendance_state" not in st.session_state:
        st.session_state.attendance_state = {
            r["student_id"]: {"name": r["name"], "status": None}
            for _, r in students.iterrows()
        }

    st.info("👉 Click a student name under the correct status")

    def mark_status(sid, status):
        st.session_state.attendance_state[sid]["status"] = status

    cols = st.columns(3)

    for idx, status in enumerate(STATUS_OPTIONS):
        with cols[idx % 3]:
            st.subheader(status)
            shown = False
            for sid, info in st.session_state.attendance_state.items():
                if info["status"] in (None, status):
                    shown = True
                    if st.button(info["name"], key=f"{day}_{session}_{status}_{sid}"):
                        mark_status(sid, status)
            if not shown:
                st.caption("—")

    data, missing = [], []

    for sid, info in st.session_state.attendance_state.items():
        if info["status"] is None:
            missing.append(info["name"])
        else:
            data.append([day, session, sid, info["name"], info["status"]])

    if missing:
        st.warning("Attendance not completed for:")
        for m in missing:
            st.write("•", m)
        return

    df = pd.DataFrame(data, columns=["date","session","student_id","name","status"])
    st.subheader("📊 Live Totals")
    st.write(df["status"].value_counts().reindex(STATUS_OPTIONS, fill_value=0))

    if st.button(f"Submit & Lock {session} Attendance"):
        get_sheet("Attendance").append_rows(data)
        set_lock(day, session, True)
        st.session_state.pop("attendance_state", None)
        st.cache_data.clear()
        st.success("✅ Attendance saved & locked")
        st.rerun()

# ---------------- STUDENTS ----------------
def manage_students():
    admin_only()
    st.header("👥 Manage Students")
    df = load_students(active_only=False)
    edited = st.data_editor(df, num_rows="dynamic")
    if st.button("Save"):
        ws = get_sheet("Students")
        ws.clear()
        ws.update([edited.columns.tolist()] + edited.values.tolist())
        st.success("Saved")
        st.rerun()

# ---------------- REPORTS ----------------
def generate_reports():
    admin_only()
    st.header("📈 Reports")
    df = load_attendance()
    if df.empty:
        st.info("No data")
        return

    day = st.date_input("Date").strftime("%Y-%m-%d")
    session = st.selectbox("Session", ["Morning", "Night", "Combined"])

    if session != "Combined":
        df = df[(df["date"].astype(str) == day) & (df["session"] == session)]
    else:
        df = df[df["date"].astype(str) == day]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False)
        df["status"].value_counts().to_excel(writer, sheet_name="Summary")

    st.download_button("Download Excel", output.getvalue(), "attendance.xlsx")

# ---------------- ANALYTICS ----------------
def analytics():
    admin_only()
    st.header("📊 Analytics")
    df = load_attendance()
    if df.empty:
        st.info("No data")
        return
    st.bar_chart(df["status"].value_counts())

# ---------------- MAIN ----------------
def main():
    st.set_page_config(APP_TITLE, layout="wide")

    if "user" not in st.session_state:
        login()
        return

    st.sidebar.title("Menu")
    logout()

    menu = ["Take Attendance"]
    if st.session_state.user["role"] == "admin":
        menu += ["Manage Students", "Generate Report", "Analytics"]

    choice = st.sidebar.radio("Go to", menu)

    if choice == "Take Attendance":
        take_attendance()
    elif choice == "Manage Students":
        manage_students()
    elif choice == "Generate Report":
        generate_reports()
    elif choice == "Analytics":
        analytics()

if __name__ == "__main__":
    main()
