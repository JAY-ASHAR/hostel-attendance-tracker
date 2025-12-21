def take_attendance():
    user = st.session_state.user
    st.header("📝 Take Attendance")

    day = st.date_input("Date", date.today()).strftime("%Y-%m-%d")
    session = (
        user.get("session")
        if user["role"] == "operator"
        else st.selectbox("Session", SESSIONS)
    )

    if is_locked(day, session) and user["role"] != "admin":
        st.warning("🔒 Session locked")
        return

    students = load_students(active_only=True)
    if students.empty:
        st.warning("No active students")
        return

    st.markdown("### Mark attendance")

    attendance = {}

    # ---------- ONE LINE PER STUDENT ----------
    for idx, (_, r) in enumerate(students.iterrows(), start=1):
        sid = r["student_id"]
        name = r["name"]

        col_no, col_name, col_radio = st.columns([0.6, 2.5, 7])

        with col_no:
            st.markdown(f"**{idx}.**")

        with col_name:
            st.markdown(f"**{name}**")

        with col_radio:
            attendance[sid] = st.radio(
                "",
                STATUS_OPTIONS,
                horizontal=True,
                key=f"{day}_{session}_{sid}",
            )

    # ---------- BUILD DATA ----------
    data = [
        [
            day,
            session,
            sid,
            students.loc[students["student_id"] == sid, "name"].values[0],
            status,
        ]
        for sid, status in attendance.items()
    ]

    df = pd.DataFrame(
        data, columns=["date", "session", "student_id", "name", "status"]
    )

    # ---------- LIVE TOTALS ----------
    st.subheader("📊 Live Totals")
    st.write(df["status"].value_counts().reindex(STATUS_OPTIONS, fill_value=0))

    # ---------- SUBMIT ----------
    if st.button(f"Submit & Lock {session} Attendance"):
        get_sheet("Attendance").append_rows(data)
        set_lock(day, session, True)
        st.cache_data.clear()
        st.success("✅ Attendance saved & locked")
        st.rerun()
