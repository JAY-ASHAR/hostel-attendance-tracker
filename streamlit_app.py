# =========================================================
# Hostel Attendance Tracker (Google Sheets Only)
# Single-file, Clean & Stable (FINAL – STUDENT WISE UI + MOBILE FRIENDLY)
# =========================================================

import streamlit as st
import pandas as pd
from datetime import date
from io import BytesIO
import gspread
from google.oauth2.service_account import Credentials

# ---------------- MOBILE FRIENDLY CSS ----------------
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 5rem;
    }

    div[role="radiogroup"] {
        flex-wrap: wrap !important;
    }

    label {
        font-size: 16px !important;
        font-weight: 500;
    }

    button {
        min-height: 44px;
        font-size: 16px;
    }

    @media (max-width: 768px) {
        section[data-testid="stSidebar"] {
            width: 100% !important;
        }
    }

    .sticky-submit {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: white;
        padding: 12px;
        border-top: 1px solid #ddd;
        z-index: 999;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
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
            st.error("Invalid credentials")

def logout():
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

def admin_only():
    if st.session_state.user["role"] != "admin":
        st.error("Admin only")
        st.stop()

# ---------------- DATA HELPERS ----------------
def normalize_active(col):
    return col.astype(str).str.upper().isin(["TRUE", "1", "YES"])

def load_students(active_only=True):
    df = pd.DataFrame(get_sheet("Students").get_all_records())
    if df.empty:
        return df

    df.columns = [c.strip().lower() for c in df.columns]
    df["active"] = normalize_active(df["active"])

    if active_only:
        df = df[df["active"]]

    return df

@st.cache_data(ttl=300)
def load_attendance():
    df = pd.DataFrame(get_sheet("Attendance").get_all_records())
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df

@st.cache_data(ttl=30)
def is_locked(day, session):
    rows = get_sheet("Locks").get_all_records()
    for r in rows:
        if str(r["date"]) == day and r["session"] == session:
            return bool(r["locked"])
    return False

def set_lock(day, session, locked=True):
    ws = get_sheet("Locks")
    rows = ws.get_all_records()
    for idx, r in enumerate(rows, start=2):
        if str(r["date"]) == day and r["session"] == session:
            ws.update(f"C{idx}", locked)
            return
    ws.append_row([day, session, locked])

# ---------------- ATTENDANCE ----------------
def take_attendance():
    user = st.session_state.user
    st.header("📝 Take Attendance")

    day = st.date_input("Date", date.today()).strftime("%Y-%m-%d")
    session = user.get("session") if user["role"] == "operator" else st.selectbox("Session", SESSIONS)

    if is_locked(day, session) and user["role"] != "admin":
        st.warning("🔒 Session locked")
        return

    students = load_students(active_only=True)
    if students.empty:
        st.warning("No active students")
        return

    attendance = {}

    for _, r in students.iterrows():
        sid = r["student_id"]
        attendance[sid] = st.radio(
            r["name"],
            STATUS_OPTIONS,
            horizontal=True,
            key=f"{day}_{session}_{sid}",
        )

    data = [
        [day, session, sid, students.loc[students["student_id"] == sid, "name"].values[0], status]
        for sid, status in attendance.items()
    ]

    df = pd.DataFrame(data, columns=["date","session","student_id","name","status"])

    st.subheader("📊 Live Totals")
    st.write(df["status"].value_counts().reindex(STATUS_OPTIONS, fill_value=0))

    st.markdown('<div class="sticky-submit">', unsafe_allow_html=True)
    if st.button(f"Submit & Lock {session} Attendance"):
        get_sheet("Attendance").append_rows(data)
        set_lock(day, session, True)
        st.cache_data.clear()
        st.success("✅ Attendance saved & locked")
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------- ANALYTICS ----------------
def analytics():
    admin_only()
    st.header("📊 Attendance Analytics")

    df = load_attendance()
    if df.empty:
        st.info("No attendance data available")
        return

    month_filter = st.selectbox(
        "📆 Select Month",
        ["All"] + sorted(df["date"].dt.to_period("M").astype(str).unique())
    )

    if month_filter != "All":
        df = df[df["date"].dt.to_period("M").astype(str) == month_filter]

    st.subheader("Overall Status Distribution")
    st.bar_chart(df["status"].value_counts().reindex(STATUS_OPTIONS, fill_value=0))

    total = df.groupby("student_id").size()
    present = df[df["status"] == "P"].groupby("student_id").size()
    percentage = ((present / total) * 100).fillna(0).round(2)

    students = load_students(active_only=False).set_index("student_id")
    report = pd.DataFrame({
        "Name": students["name"],
        "Attendance %": percentage,
        "Total Records": total
    }).fillna(0)

    st.subheader("🚦 Red Flag Students (<75%)")
    st.dataframe(report[report["Attendance %"] < 75])

    st.subheader("🏆 Best Attendance Leaderboard")
    st.dataframe(report.sort_values("Attendance %", ascending=False).head(10))

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
        menu += ["Analytics"]

    choice = st.sidebar.radio("Go to", menu)

    if choice == "Take Attendance":
        take_attendance()
    elif choice == "Analytics":
        analytics()

if __name__ == "__main__":
    main()
