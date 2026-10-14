import streamlit as st
import pandas as pd
import subprocess
import os
import io
import datetime
import traceback

st.set_page_config(page_title="AVVNL Accounts & Reports", layout="wide")

UPLOAD_DIR = "uploaded_dbs"
os.makedirs(UPLOAD_DIR, exist_ok=True)

USER_CREDENTIALS = {
    "admin": "admin123",
    "ruchir": "avvnl@2026",
    "user": "user123"
}

# --- Helper Functions ---
def get_tables(mdb_path):
    try:
        cmd = ["mdb-tables", "-1", mdb_path]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return [t.strip() for t in res.stdout.strip().split("\n") if t.strip()]
    except Exception as e:
        st.error(f"Error reading tables: {e}")
        return []

def read_table(mdb_path, table_name):
    cmd = ["mdb-export", mdb_path, table_name]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    df = pd.read_csv(io.StringIO(res.stdout), low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    return df

def find_col(df, candidates):
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols:
            return cols[cand.lower()]
    for c_lower, orig in cols.items():
        for cand in candidates:
            if cand.lower() in c_lower:
                return orig
    return df.columns[0] if len(df.columns) > 0 else None

# --- Session State ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""

# --- Login Screen ---
if not st.session_state["logged_in"]:
    st.markdown("<h2 style='text-align: center;'>🔐 AVVNL Accounts Portal - User Login</h2>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        with st.form("login_form"):
            uname = st.text_input("Username").strip().lower()
            upass = st.text_input("Password", type="password")
            submit_btn = st.form_submit_button("Login", use_container_width=True)
            if submit_btn:
                if uname in USER_CREDENTIALS and USER_CREDENTIALS[uname] == upass:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = uname
                    st.success(f"Welcome, {uname}!")
                    st.rerun()
                else:
                    st.error("Invalid Username ya Password!")
    st.stop()

username = st.session_state["username"]
user_mdb_path = os.path.join(UPLOAD_DIR, f"{username}_database.mdb")

st.sidebar.markdown(f"👤 **Logged in as:** `{username}`")
if st.sidebar.button("Logout"):
    st.session_state["logged_in"] = False
    st.session_state["username"] = ""
    st.rerun()

st.sidebar.markdown("---")

# Persistent Upload with Live Progress Bar
if not os.path.exists(user_mdb_path):
    st.info("👋 Pehli baar setup karne ke liye apna `.mdb` database file upload karein.")
    up_file = st.file_uploader("Upload .mdb Database File", type=["mdb"])
    if up_file is not None:
        prog_bar = st.progress(0)
        status_text = st.empty()
        file_size = up_file.size
        chunk_size = 1024 * 512
        bytes_written = 0
        with open(user_mdb_path, "wb") as f:
            while True:
                chunk = up_file.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                bytes_written += len(chunk)
                percent = min(100, int((bytes_written / file_size) * 100))
                prog_bar.progress(percent)
                status_text.text(f"Saving Database: {percent}%")
        st.success("Database save ho gaya!")
        st.rerun()
    st.stop()

with st.sidebar.expander("⚙️ Database Management", expanded=False):
    st.write("Database: `Active`")
    if st.button("Change / Upload New Database"):
        if os.path.exists(user_mdb_path):
            os.remove(user_mdb_path)
        st.rerun()

try:
    tables = get_tables(user_mdb_path)
    if not tables:
        st.error("Database tables read nahi ho paye.")
        st.stop()

    # =========================================================================
    # CORE LOGIC: ONLY USE MiscMaster FOR ALL ACCOUNTS & LOCATIONS
    # =========================================================================
    if "MiscMaster" not in tables:
        st.error("Database me `MiscMaster` table nahi mila.")
        st.stop()

    misc_df = read_table(user_mdb_path, "MiscMaster")
    misc_id_col = find_col(misc_df, ["Misc_IdNo", "MiscIdNo", "IdNo", "Id"])
    misc_code_col = find_col(misc_df, ["Misc_Code", "MiscCode", "Code"])
    misc_name_col = find_col(misc_df, ["Misc_Name", "MiscName", "Name", "Desc"])
    misc_type_col = find_col(misc_df, ["Misc_Type_Id", "Misc_TypeId", "TypeId", "Type"])

    misc_df[misc_id_col] = pd.to_numeric(misc_df[misc_id_col], errors='coerce')
    misc_df['Clean_Code'] = misc_df[misc_code_col].astype(str).str.strip()
    misc_df['Clean_Name'] = misc_df[misc_name_col].astype(str).str.strip()
    misc_df['Display'] = misc_df['Clean_Code'] + " - " + misc_df['Clean_Name']

    # Read VoucherDetail to identify IDs used as Accounts vs Locations
    vd = read_table(user_mdb_path, "VoucherDetail")
    vd_acc_col = find_col(vd, ["VD_AccountIdNo", "AccountIdNo", "AccountId"])
    vd_loc_col = find_col(vd, ["VD_LocationIdNo", "LocationIdNo", "LocationId"])
    
    used_acc_ids = set(pd.to_numeric(vd[vd_acc_col], errors='coerce').dropna().unique())
    used_loc_ids = set(pd.to_numeric(vd[vd_loc_col], errors='coerce').dropna().unique())

    # Build Master Mapping Dictionaries
    all_misc_map = dict(zip(misc_df[misc_id_col], misc_df['Display']))
    all_code_to_id = dict(zip(misc_df['Clean_Code'], misc_df[misc_id_col]))

    # Filter Accounts (Used in VD_AccountIdNo OR containing dots like '23.101', '10.101')
    acc_filter = misc_df[misc_df[misc_id_col].isin(used_acc_ids) | misc_df['Clean_Code'].str.contains(r'^\d{2}\.', regex=True)].copy()
    acc_map = dict(zip(acc_filter['Display'], acc_filter[misc_id_col]))
    acc_list = sorted(list(acc_map.keys()))

    # Filter Locations (Used in VD_LocationIdNo)
    loc_filter = misc_df[misc_df[misc_id_col].isin(used_loc_ids)].copy()
    loc_map = dict(zip(loc_filter['Display'], loc_filter[misc_id_col]))
    loc_list = sorted(list(loc_map.keys()))

    report_type = st.sidebar.radio("Select Report Category", ["Account General Ledger", "Trial Balance (TB)", "Raw Table Browser"])

    # ==========================================================
    # 1. ACCOUNT GENERAL LEDGER
    # ==========================================================
    if report_type == "Account General Ledger":
        st.subheader("📖 Account General Ledger (via MiscMaster)")

        c1, c2, c3, c4 = st.columns([2, 1.5, 1, 1])
        with c1:
            selected_acc = st.selectbox("Select Ledger Account", acc_list)
            target_acc_id = acc_map[selected_acc]
        with c2:
            selected_loc = st.selectbox("Location Filter", ["All Locations"] + loc_list)
        with c3:
            start_date = st.date_input("Start Date", datetime.date(2026, 4, 1))
        with c4:
            end_date = st.date_input("Last Date", datetime.date(2026, 10, 14))

        if st.button("Generate Ledger Report", type="primary"):
            with st.spinner("Processing ledger entries via MiscMaster..."):
                vh = read_table(user_mdb_path, "VoucherHeader")
                bal_data = read_table(user_mdb_path, "BalanceData") if "BalanceData" in tables else pd.DataFrame()

                vd_vh_id = find_col(vd, ["VD_VHIdNo", "VHIdNo", "VH_Id"])
                vh_pk = find_col(vh, ["VH_IdNo", "VHIdNo", "VH_Id", "IdNo"])
                vh_date_col = find_col(vh, ["VH_VoucherDate", "VoucherDate", "Date"])
                vh_no_col = find_col(vh, ["VH_VoucherNo", "VoucherNo", "VouNo"])

                vd_dr_col = find_col(vd, ["VD_DebitAmount", "DebitAmount", "Debit"])
                vd_cr_col = find_col(vd, ["VD_CreditAmount", "CreditAmount", "Credit"])
                vd_supp_no = find_col(vd, ["VD_SuppVoucherNo", "SuppVoucherNo"])
                vd_supp_date = find_col(vd, ["VD_SuppVoucherDate", "SuppVoucherDate"])

                # Exact Filter by target_acc_id from MiscMaster
                vd[vd_acc_col] = pd.to_numeric(vd[vd_acc_col], errors='coerce')
                filtered_vd = vd[vd[vd_acc_col] == float(target_acc_id)].copy()

                if selected_loc != "All Locations":
                    chosen_loc_id = loc_map[selected_loc]
                    filtered_vd = filtered_vd[filtered_vd[vd_loc_col] == chosen_loc_id]

                # Merge Detail with Header
                merged = pd.merge(filtered_vd, vh, left_on=vd_vh_id, right_on=vh_pk, suffixes=('', '_vh'))

                # Filter by Date Range
                merged['Clean_Date'] = pd.to_datetime(merged[vh_date_col], errors='coerce').dt.date
                mask = (merged['Clean_Date'] >= start_date) & (merged['Clean_Date'] <= end_date)
                ledger_rows = merged.loc[mask].copy()
                ledger_rows = ledger_rows.sort_values(by=['Clean_Date', vh_no_col])

                # Opening Balance from BalanceData
                op_bal = 0.0
                if not bal_data.empty:
                    b_acc = find_col(bal_data, ["Balance_AccountIdNo", "AccountIdNo"])
                    b_loc = find_col(bal_data, ["Balance_LocationIdNo", "LocationIdNo"])
                    b_dr = find_col(bal_data, ["Balance_DebitAmount", "DebitAmount"])
                    b_cr = find_col(bal_data, ["Balance_CreditAmount", "CreditAmount"])

                    bal_data[b_acc] = pd.to_numeric(bal_data[b_acc], errors='coerce')
                    bal_match = bal_data[bal_data[b_acc] == float(target_acc_id)]
                    if selected_loc != "All Locations":
                        bal_match = bal_match[bal_match[b_loc] == chosen_loc_id]

                    if not bal_match.empty:
                        d_sum = pd.to_numeric(bal_match[b_dr], errors='coerce').fillna(0.0).sum()
                        c_sum = pd.to_numeric(bal_match[b_cr], errors='coerce').fillna(0.0).sum()
                        op_bal = d_sum - c_sum

                # Debit / Credit amounts
                ledger_rows['Debit Amount'] = pd.to_numeric(ledger_rows[vd_dr_col], errors='coerce').fillna(0.0)
                ledger_rows['Credit Amount'] = pd.to_numeric(ledger_rows[vd_cr_col], errors='coerce').fillna(0.0)
                ledger_rows['Net'] = ledger_rows['Debit Amount'] - ledger_rows['Credit Amount']

                # Running Balance
                ledger_rows['Running Balance'] = op_bal + ledger_rows['Net'].cumsum()
                ledger_rows['Running Balance Text'] = ledger_rows['Running Balance'].apply(
                    lambda x: f"{abs(x):,.2f}Dr" if x >= 0 else f"{abs(x):,.2f}Cr"
                )

                # Location Mapping directly from MiscMaster
                ledger_rows['Location Name'] = ledger_rows[vd_loc_col].map(all_misc_map).fillna(ledger_rows[vd_loc_col].astype(str))

                final_table = pd.DataFrame({
                    "Voucher Date": pd.to_datetime(ledger_rows['Clean_Date']).dt.strftime('%d-%b-%Y'),
                    "Voucher No.": ledger_rows[vh_no_col],
                    "Supp.VouNo": ledger_rows[vd_supp_no].fillna(''),
                    "Supp.VouDate": ledger_rows[vd_supp_date].fillna(''),
                    "Debit Amount": ledger_rows['Debit Amount'],
                    "Credit Amount": ledger_rows['Credit Amount'],
                    "Location Name": ledger_rows['Location Name'],
                    "Running Balance": ledger_rows['Running Balance Text']
                })

                st.markdown("---")
                st.markdown(f"**Account Desc. :** `{selected_acc}`")
                st.markdown(f"**Account Opening:** `{abs(op_bal):,.2f}-{'Dr' if op_bal >= 0 else 'Cr'}`")

                total_dr = final_table['Debit Amount'].sum()
                total_cr = final_table['Credit Amount'].sum()
                closing = op_bal + total_dr - total_cr

                m1, m2, m3 = st.columns(3)
                m1.metric("Total Debit", f"₹ {total_dr:,.2f}")
                m2.metric("Total Credit", f"₹ {total_cr:,.2f}")
                m3.metric("Closing Balance", f"{abs(closing):,.2f} {'Dr' if closing >= 0 else 'Cr'}")

                st.dataframe(final_table, use_container_width=True, height=520)

                # Excel Download
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine='openpyxl') as wr:
                    final_table.to_excel(wr, index=False, sheet_name="Ledger")
                st.download_button(
                    label="📥 Download Continuous Ledger (Excel)",
                    data=out.getvalue(),
                    file_name=f"Ledger_{selected_acc[:15]}_{start_date}_to_{end_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    # ==========================================================
    # 2. TRIAL BALANCE (TB)
    # ==========================================================
    elif report_type == "Trial Balance (TB)":
        st.subheader("⚖️ Account Trial Balance (via MiscMaster)")

        t1, t2, t3 = st.columns([1, 1, 1])
        with t1:
            tb_type = st.selectbox("Trial Balance Type", ["Merged Single", "Merged Splitted", "Separate"])
        with t2:
            tb_start = st.date_input("Start Date", datetime.date(2026, 4, 1), key="tbs")
        with t3:
            tb_end = st.date_input("Last Date", datetime.date(2027, 4, 1), key="tbe")

        if st.button("Generate Trial Balance", type="primary"):
            with st.spinner("Calculating Trial Balance..."):
                bal_data = read_table(user_mdb_path, "BalanceData") if "BalanceData" in tables else pd.DataFrame()
                if bal_data.empty:
                    st.warning("BalanceData table empty hai.")
                    st.stop()

                b_acc = find_col(bal_data, ["Balance_AccountIdNo", "AccountIdNo"])
                b_loc = find_col(bal_data, ["Balance_LocationIdNo", "LocationIdNo"])
                b_dr = find_col(bal_data, ["Balance_DebitAmount", "DebitAmount"])
                b_cr = find_col(bal_data, ["Balance_CreditAmount", "CreditAmount"])

                bal_data[b_acc] = pd.to_numeric(bal_data[b_acc], errors='coerce')
                bal_data[b_loc] = pd.to_numeric(bal_data[b_loc], errors='coerce')

                # Direct map via MiscMaster
                bal_data['Display_Acc'] = bal_data[b_acc].map(all_misc_map).fillna(bal_data[b_acc].astype(str))
                bal_data['Location_Display'] = bal_data[b_loc].map(all_misc_map).fillna(bal_data[b_loc].astype(str))

                bal_data['Year Opening Dr'] = pd.to_numeric(bal_data[b_dr], errors='coerce').fillna(0.0)
                bal_data['Year Opening Cr'] = pd.to_numeric(bal_data[b_cr], errors='coerce').fillna(0.0)

                if tb_type == "Merged Single":
                    tb_res = bal_data.groupby(['Display_Acc']).agg({
                        'Year Opening Dr': 'sum',
                        'Year Opening Cr': 'sum'
                    }).reset_index()

                    tb_res['Closing Dr'] = tb_res.apply(lambda r: max(0.0, r['Year Opening Dr'] - r['Year Opening Cr']), axis=1)
                    tb_res['Closing Cr'] = tb_res.apply(lambda r: max(0.0, r['Year Opening Cr'] - r['Year Opening Dr']), axis=1)

                    st.dataframe(tb_res, use_container_width=True, height=600)

                    out_tb = io.BytesIO()
                    with pd.ExcelWriter(out_tb, engine='openpyxl') as wr:
                        tb_res.to_excel(wr, index=False, sheet_name="TB_Merged_Single")
                    st.download_button("📥 Download Merged Single TB (Excel)", out_tb.getvalue(), "TB_Merged_Single.xlsx")

                elif tb_type == "Merged Splitted":
                    tb_res = bal_data.groupby(['Display_Acc', 'Location_Display']).agg({
                        'Year Opening Dr': 'sum',
                        'Year Opening Cr': 'sum'
                    }).reset_index()

                    st.dataframe(tb_res, use_container_width=True, height=600)

                    out_tb = io.BytesIO()
                    with pd.ExcelWriter(out_tb, engine='openpyxl') as wr:
                        tb_res.to_excel(wr, index=False, sheet_name="TB_Merged_Splitted")
                    st.download_button("📥 Download Merged Splitted TB (Excel)", out_tb.getvalue(), "TB_Merged_Splitted.xlsx")

                elif tb_type == "Separate":
                    locs = sorted(bal_data['Location_Display'].dropna().unique().tolist())
                    chosen_loc = st.selectbox("Choose Location", locs)

                    tb_loc = bal_data[bal_data['Location_Display'] == chosen_loc].groupby(['Display_Acc']).agg({
                        'Year Opening Dr': 'sum',
                        'Year Opening Cr': 'sum'
                    }).reset_index()

                    st.dataframe(tb_loc, use_container_width=True, height=600)

    # ==========================================================
    # 3. RAW TABLE BROWSER
    # ==========================================================
    elif report_type == "Raw Table Browser":
        st.subheader("🔍 Explore Tables")
        sel_t = st.selectbox("Select Table", tables)
        if sel_t:
            df_view = read_table(user_mdb_path, sel_t)
            st.write(f"Total Rows: {len(df_view)} | Columns: {list(df_view.columns)}")
            st.dataframe(df_view.head(200), use_container_width=True)

except Exception as e:
    st.error(f"Execution Error: {e}")
    st.code(traceback.format_exc)
