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
def load_students(active_only=True):
    df = pd.DataFrame(get_sheet("Students").get_all_records())
    if df.empty:
        return df
    df.columns = [c.lower() for c in df.columns]
    if active_only:
        df = df[df["active"] == True]
    return df

@st.cache_data(ttl=300)
def load_attendance():
    df = pd.DataFrame(get_sheet("Attendance").get_all_records())
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df

def get_next_student_id():
    df = load_students(active_only=False)
    if df.empty:
        return 1
    return int(df["student_id"].max()) + 1

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
    for i, r in enumerate(rows, start=2):
        if str(r["date"]) == day and r["session"] == session:
            ws.update(f"C{i}", locked)
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

    students = load_students()
    if students.empty:
        st.warning("No active students")
        return

    if "attendance_state" not in st.session_state:
        st.session_state.attendance_state = {
            r["student_id"]: {"name": r["name"], "status": None}
            for _, r in students.iterrows()
        }

    st.info("Click student name under correct status")

    cols = st.columns(3)

    for i, status in enumerate(STATUS_OPTIONS):
        with cols[i % 3]:
            st.subheader(status)
            for sid, info in st.session_state.attendance_state.items():
                if info["status"] in (None, status):
                    if st.button(info["name"], key=f"{day}_{session}_{status}_{sid}"):
                        st.session_state.attendance_state[sid]["status"] = status

    data, missing = [], []
    for sid, info in st.session_state.attendance_state.items():
        if not info["status"]:
            missing.append(info["name"])
        else:
            data.append([day, session, sid, info["name"], info["status"]])

    if missing:
        st.warning("Attendance pending for:")
        for m in missing:
            st.write("•", m)
        return

    df = pd.DataFrame(data, columns=["date","session","student_id","name","status"])
    st.subheader("Live Totals")
    st.write(df["status"].value_counts().reindex(STATUS_OPTIONS, fill_value=0))

    if st.button("Submit & Lock"):
        get_sheet("Attendance").append_rows(data)
        set_lock(day, session, True)
        st.session_state.pop("attendance_state")
        st.cache_data.clear()
        st.success("Attendance saved")
        st.rerun()

# ---------------- MANAGE STUDENTS ----------------
def manage_students():
    admin_only()
    st.header("👥 Manage Students")

    ws = get_sheet("Students")
    df = load_students(active_only=False)
    if df.empty:
        df = pd.DataFrame(columns=["student_id","name","active","inactive_reason"])

    search = st.text_input("🔍 Search").lower()
    if search:
        df = df[df["name"].str.lower().str.contains(search)]

    with st.form("add_student"):
        name = st.text_input("Student Name")
        if st.form_submit_button("Add Student"):
            if not name.strip():
                st.error("Name required")
            elif name.lower() in df["name"].str.lower().tolist():
                st.error("Duplicate name")
            else:
                ws.append_row([get_next_student_id(), name.strip(), True, ""])
                st.success("Student added")
                st.rerun()

    edited = st.data_editor(
        df,
        column_config={
            "student_id": st.column_config.NumberColumn(disabled=True),
            "active": st.column_config.CheckboxColumn(),
        },
        num_rows="dynamic"
    )

    if st.button("Save Changes"):
        if edited["name"].str.lower().duplicated().any():
            st.error("Duplicate names found")
            return
        ws.clear()
        ws.update([edited.columns.tolist()] + edited.values.tolist())
        st.success("Saved")
        st.rerun()

# ---------------- STUDENT PROFILE ----------------
def student_profiles():
    admin_only()
    st.header("📊 Student Profile")

    students = load_students(active_only=False)
    sid = st.selectbox(
        "Student",
        students["student_id"],
        format_func=lambda x: students.loc[students["student_id"] == x, "name"].values[0]
    )

    df = load_attendance()
    sdf = df[df["student_id"] == sid]

    if sdf.empty:
        st.info("No records")
        return

    st.dataframe(sdf[["date","session","status"]])
    st.subheader("Summary")
    st.write(sdf["status"].value_counts())

# ---------------- REPORTS ----------------
def generate_reports():
    admin_only()
    st.header("📈 Reports")
    df = load_attendance()
    if df.empty:
        st.info("No data")
        return

    day = st.date_input("Date").strftime("%Y-%m-%d")
    session = st.selectbox("Session", ["Morning","Night","Combined"])

    if session != "Combined":
        df = df[(df["date"].astype(str)==day) & (df["session"]==session)]
    else:
        df = df[df["date"].astype(str)==day]

    out = BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as w:
        df.to_excel(w, index=False)
        df["status"].value_counts().to_excel(w, sheet_name="Summary")

    st.download_button("Download Excel", out.getvalue(), "attendance.xlsx")

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
        menu += ["Manage Students","Student Profiles","Generate Report"]

    choice = st.sidebar.radio("Go to", menu)

    if choice == "Take Attendance":
        take_attendance()
    elif choice == "Manage Students":
        manage_students()
    elif choice == "Student Profiles":
        student_profiles()
    elif choice == "Generate Report":
        generate_reports()

if __name__ == "__main__":
    main()
