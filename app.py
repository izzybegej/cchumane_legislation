# app.py
# ------
# The only file you run: `streamlit run app.py`
#
# CHANGES IN THIS VERSION:
#   - clean() helper eliminates "nan" showing up anywhere in the UI
#   - "Add Bill" form in sidebar lets you track new bills without editing code
#   - "Manage Bills" section shows custom bills with a remove button
#   - District flag shows "— not in our service area" instead of blank/nan

import streamlit as st
import pandas as pd
from scraper import scrape_all_bills
from storage import save_bills, load_bills, data_exists, last_updated
from bills import (
    load_custom_bills, save_custom_bills, remove_custom_bill,
    SESSION_104, SESSION_103
)

# ---------------------------------------------------------------------------
# PAGE CONFIGURATION — must be the very first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CU Humane Bill Tracker",
    page_icon="🐾",
    layout="wide",
)

# ---------------------------------------------------------------------------
# HELPER: clean()
# ---------------------------------------------------------------------------
# WHY THIS EXISTS:
#   pandas represents missing/empty CSV cells as NaN (Not a Number — a float).
#   When displayed directly in Streamlit, they appear as the text "nan".
#   This function converts any NaN, None, or empty value to a clean fallback
#   string (default: "") so nothing broken ever shows in the UI.
#
# Rule: whenever reading from a DataFrame row, always wrap in clean().
#   Instead of:  row.get("field", "")
#   Always use:  clean(row.get("field"))

def clean(value, fallback=""):
    """Returns value as a clean string, or fallback if it's empty/NaN/None."""
    if value is None:
        return fallback
    if isinstance(value, float):   # NaN is stored as a float in Python/pandas
        return fallback
    s = str(value).strip()
    if s.lower() == "nan" or s == "":
        return fallback
    return s


# ---------------------------------------------------------------------------
# STYLING
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: 700; color: #1a3a5c; margin-bottom: 0; }
    .sub-header  { color: #666; margin-top: 0; margin-bottom: 1.5rem; }
    a { color: #1a3a5c; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------------
st.markdown('<p class="main-header">🐾 CU Humane Bill Tracker</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Illinois General Assembly — Animal Welfare Legislation</p>', unsafe_allow_html=True)

if data_exists():
    st.caption(f"Data last refreshed: {last_updated()}")
else:
    st.caption("No data loaded yet — click 'Refresh All Bills' in the sidebar.")


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
with st.sidebar:

    # ---- Refresh button ----
    st.header("⚙️ Controls")
    if st.button("🔄 Refresh All Bills", type="primary", use_container_width=True):
        with st.spinner("Fetching bill data from ILGA... this may take 30–60 seconds"):
            try:
                results = scrape_all_bills()
                save_bills(results)
                st.success(f"✅ Updated {len(results)} bills!")
                st.rerun()
            except Exception as e:
                st.error(f"Error during refresh: {e}")

    st.divider()

    # ---- Add New Bill form ----
    # Saves to custom_bills.json — no Python file editing required.
    #
    # HOW TO FIND A BILL NUMBER:
    #   Go to ilga.gov and search for the bill. The number is just the
    #   digits — e.g. for "HB5411" enter type "HB" and number "5411".

    st.header("➕ Add Bill to Track")

    with st.form("add_bill_form", clear_on_submit=True):
        friendly_name = st.text_input(
            "Your label for this bill",
            placeholder="e.g. Puppy Mill Reform"
        )
        col_type, col_num = st.columns(2)
        with col_type:
            bill_type = st.selectbox("Type", ["HB", "SB"])
        with col_num:
            bill_number = st.text_input("Number", placeholder="e.g. 1234")

        session_choice = st.selectbox(
            "Session",
            ["104th GA (current, 2025–2026)", "103rd GA (previous, 2023–2024)"]
        )

        submitted = st.form_submit_button("Add Bill", use_container_width=True)

        if submitted:
            if not friendly_name.strip():
                st.error("Please enter a label for this bill.")
            elif not bill_number.strip().isdigit():
                st.error("Bill number should be digits only (e.g. 1234).")
            else:
                session_data = SESSION_104 if "104" in session_choice else SESSION_103
                new_bill = {
                    "friendly_name": friendly_name.strip(),
                    "bill_type":     bill_type,
                    "bill_number":   bill_number.strip(),
                    **session_data,
                }
                existing = load_custom_bills()
                bill_id  = f"{bill_type}{bill_number.strip()}"
                already  = any(
                    f"{b['bill_type']}{b['bill_number']}" == bill_id
                    for b in existing
                )
                if already:
                    st.warning(f"{bill_id} is already being tracked.")
                else:
                    existing.append(new_bill)
                    save_custom_bills(existing)
                    st.success(
                        f"✅ Added {bill_id}! "
                        f"Click 'Refresh All Bills' to fetch its data."
                    )

    # ---- Manage custom bills ----
    # Shows only the bills you added through the form (not bills.py baseline).
    custom = load_custom_bills()
    if custom:
        st.divider()
        st.header("🗂️ Custom Bills")
        st.caption("Added via this form — click ✕ to remove")
        for b in custom:
            bid = f"{b['bill_type']}{b['bill_number']}"
            c1, c2 = st.columns([3, 1])
            with c1:
                st.caption(f"**{bid}** — {b['friendly_name']}")
            with c2:
                if st.button("✕", key=f"remove_{bid}", help=f"Remove {bid}"):
                    remove_custom_bill(bid)
                    st.rerun()

    st.divider()

    # ---- Filters ----
    st.header("🔍 Filters")

    # Safe defaults so the page renders even before data is loaded
    selected_session  = "All Sessions"
    selected_district = "All Districts"
    selected_chamber  = "Both Chambers"
    status_search     = ""

    df_for_filters = load_bills()
    if df_for_filters is not None and not df_for_filters.empty:
        sessions = ["All Sessions"] + sorted(df_for_filters["session"].unique().tolist())
        selected_session  = st.selectbox("Session", sessions)
        selected_district = st.selectbox(
            "District",
            ["All Districts", "⭐ Our District", "📍 Neighbor District", "Other"]
        )
        selected_chamber = st.selectbox("Chamber", ["Both Chambers", "House", "Senate"])
        status_search    = st.text_input(
            "Search status/committee",
            placeholder="e.g. Rules, Agriculture"
        )

    st.divider()
    st.markdown("**Legend**")
    st.markdown("⭐ = Our districts (52nd Senate, 103rd House)")
    st.markdown("📍 = Neighbor districts")
    st.markdown("— = Unrelated district")


# ---------------------------------------------------------------------------
# MAIN CONTENT
# ---------------------------------------------------------------------------
df = load_bills()

if df is None or df.empty:
    st.info("👆 Click **Refresh All Bills** in the sidebar to load bill data for the first time.")
    st.stop()

# --- Apply filters ---
filtered_df = df.copy()

if selected_session != "All Sessions":
    filtered_df = filtered_df[filtered_df["session"] == selected_session]

if selected_district == "⭐ Our District":
    filtered_df = filtered_df[filtered_df["district_flag"] == "⭐ Our District"]
elif selected_district == "📍 Neighbor District":
    filtered_df = filtered_df[filtered_df["district_flag"] == "📍 Neighbor District"]
elif selected_district == "Other":
    filtered_df = filtered_df[
        ~filtered_df["district_flag"].isin(["⭐ Our District", "📍 Neighbor District"])
    ]

if selected_chamber != "Both Chambers":
    filtered_df = filtered_df[filtered_df["chamber"] == selected_chamber]

if status_search:
    mask = (
        filtered_df["current_status"].str.contains(status_search, case=False, na=False) |
        filtered_df["committee"].str.contains(status_search, case=False, na=False)
    )
    filtered_df = filtered_df[mask]

st.markdown(f"**Showing {len(filtered_df)} of {len(df)} bills**")

# ---------------------------------------------------------------------------
# BILL CARDS
# ---------------------------------------------------------------------------
if filtered_df.empty:
    st.warning("No bills match the current filters.")
else:
    for _, row in filtered_df.iterrows():

        # clean() on every value — no "nan" can ever reach the UI
        flag          = clean(row.get("district_flag"))
        session_str   = clean(row.get("session"))
        bill_id       = clean(row.get("bill_id"))
        friendly_name = clean(row.get("friendly_name"))

        district_badge = f" {flag}" if flag else ""
        session_note   = " *(103rd GA — session ended)*" if "103" in session_str else ""
        expander_label = f"**{bill_id}** — {friendly_name}{district_badge}{session_note}"

        with st.expander(expander_label, expanded=False):

            # --- Status / Committee / Session ---
            col1, col2, col3 = st.columns([2, 2, 1])

            with col1:
                st.markdown("**Current Status**")
                st.markdown(f"`{clean(row.get('current_status'), 'Unknown')}`")
                st.caption(
                    f"As of {clean(row.get('status_date'), '?')} "
                    f"— {clean(row.get('chamber'))}"
                )

            with col2:
                st.markdown("**Committee**")
                committee     = clean(row.get("committee"))
                committee_url = clean(row.get("committee_url"))
                if committee:
                    if committee_url:
                        st.markdown(f"[{committee}]({committee_url})")
                    else:
                        st.markdown(committee)
                else:
                    st.caption("Not yet assigned to committee")

            with col3:
                st.markdown("**Session**")
                st.markdown(session_str)

            st.divider()

            # --- Sponsor / Cosponsors ---
            col4, col5 = st.columns(2)

            with col4:
                st.markdown("**Primary Sponsor**")
                st.markdown(clean(row.get("primary_sponsor"), "Unknown"))
                district = clean(row.get("sponsor_district"), "Unknown")

                # Always show a clear, human-readable district label — no blanks, no "nan"
                if flag == "⭐ Our District":
                    st.caption(f"District: {district} ⭐ Our District")
                elif flag == "📍 Neighbor District":
                    st.caption(f"District: {district} 📍 Neighbor District")
                else:
                    st.caption(f"District: {district} — not in our service area")

            with col5:
                cosponsors = clean(row.get("cosponsors"))
                if cosponsors:
                    st.markdown("**Co-Sponsors**")
                    for cs in cosponsors.split("|"):
                        if cs.strip():
                            st.caption(f"• {cs.strip()}")

            st.divider()

            # --- Committee Hearings ---
            schedule_url   = clean(row.get("schedule_url"))
            chamber_name   = clean(row.get("chamber"), "chamber")
            committee_name = clean(row.get("committee"), "this committee")
            is_old         = "103" in session_str

            if schedule_url:
                st.markdown("**📅 Committee Hearings**")
                st.info(
                    f"ILGA's hearing schedule is updated weekly. "
                    f"[View the {chamber_name} schedule →]({schedule_url})  \n"
                    f"Check when **{committee_name}** meets next and reach out before that date."
                )
            elif is_old:
                st.caption("📅 103rd GA session has ended — no future hearings")

            st.divider()

            # --- Synopsis ---
            synopsis = clean(row.get("synopsis"))
            if synopsis:
                st.markdown("**Synopsis**")
                st.markdown(synopsis)
                st.divider()

            # --- Action History ---
            history = clean(row.get("action_history"))
            if history:
                with st.expander("📋 Full Action History"):
                    for entry in history.split(" | "):
                        if entry.strip():
                            st.caption(entry.strip())

            # --- Links ---
            st.markdown("**Links**")
            lc1, lc2 = st.columns(2)
            with lc1:
                bill_url = clean(row.get("bill_page_url"))
                if bill_url:
                    st.markdown(f"[📄 Bill Status Page]({bill_url})")
            with lc2:
                fulltext_url = clean(row.get("fulltext_url"))
                if fulltext_url:
                    st.markdown(f"[📃 Full Bill Text]({fulltext_url})")


# ---------------------------------------------------------------------------
# RAW DATA TABLE
# ---------------------------------------------------------------------------
with st.expander("📊 View Raw Data Table"):
    display_cols = [
        "bill_id", "friendly_name", "primary_sponsor", "sponsor_district",
        "district_flag", "committee", "current_status", "status_date", "session"
    ]
    available_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[available_cols], use_container_width=True)
    st.download_button(
        label="⬇️ Download Full CSV",
        data=df.to_csv(index=False),
        file_name="illinois_bills.csv",
        mime="text/csv",
    )
