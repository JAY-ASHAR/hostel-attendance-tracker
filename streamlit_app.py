# =========================================================
# Hostel Attendance Tracker (Google Sheets Only)
# Single-file, Clean & Stable (FINAL – STUDENT WISE UI)
# =========================================================

import streamlit as st
import pandas as pd
from datetime import date
from io import BytesIO
import gspread
from google.oauth2.service_account import Credentials
# ---------------- MOBILE FRIENDLY UI ----------------
st.markdown(
    """
    <style>
    /* Overall app width for mobile */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        padding-left: 1rem;
        padding-right: 1rem;
        max-width: 100%;
    }

    /* Make radio buttons touch-friendly */
    div[role="radiogroup"] > label {
        margin-right: 12px;
        font-size: 16px;
    }

    /* Student name spacing */
    label {
        font-size: 16px !important;
        font-weight: 500;
    }

    /* Bigger buttons for mobile */
    button[kind="primary"] {
        width: 100%;
        font-size: 18px;
        padding: 0.6rem;
    }

    /* Sidebar scroll on mobile */
    section[data-testid="stSidebar"] {
        overflow-y: auto;
    }

    /* Reduce horizontal overflow */
    .stHorizontalBlock {
        overflow-x: auto;
    }

    /* Hide Streamlit footer */
    footer {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True
)
/* Main app title */
h1 {
    font-size: 28px !important;
    font-weight: 700 !important;
    color: #1f2937;
    margin-bottom: 0.5rem;
}

/* Section headers */
h2 {
    font-size: 22px !important;
    font-weight: 600 !important;
    color: #111827;
    margin-top: 1.5rem;
    margin-bottom: 0.5rem;
}

/* Sub-section headers */
h3 {
    font-size: 18px !important;
    font-weight: 600 !important;
    color: #374151;
    margin-top: 1rem;
}

/* Improve normal text readability */
p, li, label {
    font-size: 16px !important;
    line-height: 1.6;
    color: #1f2937;
}

/* Sidebar headings */
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2 {
    font-size: 18px !important;
    font-weight: 600 !important;
}


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

def get_next_student_id():
    df = load_students(active_only=False)
    return int(df["student_id"].max()) + 1 if not df.empty else 1

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

# ---------------- COLOR EXCEL GENERATOR ----------------
def generate_color_excel(df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Attendance", index=False)

        workbook = writer.book
        worksheet = writer.sheets["Attendance"]

        green = workbook.add_format({"bg_color": "#C6EFCE"})
        red = workbook.add_format({"bg_color": "#FFC7CE"})

        status_col = df.columns.get_loc("status")

        for row in range(1, len(df) + 1):
            status = df.iloc[row - 1]["status"]
            if status == "A":
                worksheet.write(row, status_col, status, red)
            else:
                worksheet.write(row, status_col, status, green)

    output.seek(0)
    return output

# ---------------- ATTENDANCE ----------------
def take_attendance():
    user = st.session_state.user
    st.header("📝 Take Attendance")

    day = st.date_input("Date", date.today()).strftime("%Y-%m-%d")
    session = user.get("session") if user["role"] == "operator" else st.selectbox("Session", SESSIONS)

    if is_locked(day, session) and user["role"] != "admin":
        st.warning("🔒 Session locked")
        return

    students = load_students(True)
    if students.empty:
        st.warning("No active students")
        return

    attendance = {}
    for _, r in students.iterrows():
        attendance[r["student_id"]] = st.radio(
            r["name"], STATUS_OPTIONS, horizontal=True, key=f"{day}_{session}_{r['student_id']}"
        )

    data = [[day, session, sid, students.loc[students["student_id"] == sid, "name"].values[0], status]
            for sid, status in attendance.items()]

    df = pd.DataFrame(data, columns=["date","session","student_id","name","status"])

    st.subheader("📊 Live Totals")
    st.write(df["status"].value_counts().reindex(STATUS_OPTIONS, fill_value=0))

    if st.button(f"Submit & Lock {session} Attendance"):
        get_sheet("Attendance").append_rows(data)
        set_lock(day, session, True)
        st.cache_data.clear()

        excel_file = generate_color_excel(df)

        st.success("✅ Attendance saved, locked & report generated")

        st.download_button(
            "⬇️ Download Daily Report",
            excel_file,
            file_name=f"attendance_{day}_{session}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
# ---------------- ANALYTICS (NEW) ----------------

def analytics():
    admin_only()
    st.header("📊 Attendance Analytics")

    df = load_attendance()
    if df.empty:
        st.info("No attendance data available")
        return

    # ---------------- FILTERS ----------------
    col1, col2 = st.columns(2)

    with col1:
        month_filter = st.selectbox(
            "📆 Select Month",
            ["All"] + sorted(df["date"].dt.to_period("M").astype(str).unique())
        )

    with col2:
        session_filter = st.selectbox(
            "Session",
            ["All", "Morning", "Night"]
        )

    if month_filter != "All":
        df = df[df["date"].dt.to_period("M").astype(str) == month_filter]

    if session_filter != "All":
        df = df[df["session"] == session_filter]

    if df.empty:
        st.warning("No data for selected filters")
        return

    # ---------------- STATUS DISTRIBUTION ----------------
    st.subheader("📌 Overall Status Distribution")
    status_counts = df["status"].value_counts().reindex(STATUS_OPTIONS, fill_value=0)
    st.bar_chart(status_counts)

    # ---------------- MONTHLY ANALYTICS ----------------
    st.subheader("📆 Monthly Attendance Summary (Present Count)")
    monthly_present = (
        df[df["status"] == "P"]
        .groupby(df["date"].dt.to_period("M"))
        .size()
        .astype(int)
    )
    st.bar_chart(monthly_present)

    # ---------------- ATTENDANCE PERCENTAGE ----------------
    total = df.groupby("student_id").size()
    present = df[df["status"] == "P"].groupby("student_id").size()
    percentage = ((present / total) * 100).fillna(0).round(2)

    students = load_students(active_only=False).set_index("student_id")

    report = pd.DataFrame({
        "Name": students["name"],
        "Attendance %": percentage,
        "Total Records": total
    }).fillna(0)

    # ---------------- 🚦 RED FLAG STUDENTS ----------------
    st.subheader("🚦 Red Flag Students (Below 75%)")
    red_flags = report[report["Attendance %"] < 75]

    if red_flags.empty:
        st.success("✅ No red-flag students")
    else:
        st.dataframe(
            red_flags.sort_values("Attendance %"),
            use_container_width=True
        )

    # ---------------- 🏆 BEST ATTENDANCE ----------------
    st.subheader("🏆 Best Attendance Leaderboard")
    leaderboard = report.sort_values("Attendance %", ascending=False).head(10)

    st.dataframe(
        leaderboard,
        use_container_width=True
    )

# ---------------- MANAGE STUDENTS ----------------
def manage_students():
    admin_only()
    st.header("👥 Manage Students")

    ws = get_sheet("Students")
    df = load_students(active_only=False)

    if df.empty:
        df = pd.DataFrame(columns=["student_id", "name", "active", "inactive_reason"])

    search = st.text_input("🔍 Search student").strip().lower()
    if search:
        df = df[df["name"].str.lower().str.contains(search)]

    with st.form("add_student"):
        name = st.text_input("Student Name")
        if st.form_submit_button("Add Student"):
            if not name.strip():
                st.error("Name required")
            elif name.lower() in df["name"].str.lower().tolist():
                st.error("Duplicate name not allowed")
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
        num_rows="dynamic",
    )

    if st.button("Save Changes"):
        if edited["name"].str.lower().duplicated().any():
            st.error("Duplicate names found")
            return
        ws.clear()
        ws.update([edited.columns.tolist()] + edited.values.tolist())
        st.success("Changes saved")
        st.rerun()

# ---------------- STUDENT PROFILE ----------------
def student_profiles():
    admin_only()
    st.header("📊 Student Profile")

    students = load_students(active_only=False)
    if students.empty:
        st.info("No students")
        return

    sid = st.selectbox(
        "Select Student",
        students["student_id"],
        format_func=lambda x: students.loc[
            students["student_id"] == x, "name"
        ].values[0],
    )

    df = load_attendance()
    sdf = df[df["student_id"] == sid]

    if sdf.empty:
        st.info("No attendance records")
        return

    st.dataframe(sdf[["date", "session", "status"]])
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
    session = st.selectbox("Session", ["Morning", "Night", "Combined"])

    if session != "Combined":
        df = df[(df["date"].astype(str) == day) & (df["session"] == session)]
    else:
        df = df[df["date"].astype(str) == day]

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
        menu += ["Analytics", "Manage Students", "Student Profiles", "Generate Report"]

    choice = st.sidebar.radio("Go to", menu)

    if choice == "Take Attendance":
        take_attendance()
    elif choice == "Analytics":
        analytics()
    elif choice == "Manage Students":
        manage_students()
    elif choice == "Student Profiles":
        student_profiles()
    elif choice == "Generate Report":
        generate_reports()

if __name__ == "__main__":
    main()
