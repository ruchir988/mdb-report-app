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

    # Load MiscMaster
    misc_df = read_table(user_mdb_path, "MiscMaster")
    m_id = find_col(misc_df, ["Misc_IdNo", "MiscIdNo", "IdNo", "Id"])
    m_desc = find_col(misc_df, ["Misc_Desc", "Misc_Name", "MiscName", "Desc", "Name"])
    m_code = find_col(misc_df, ["Misc_Code", "MiscCode", "Code"])

    misc_df[m_id] = pd.to_numeric(misc_df[m_id], errors='coerce')
    misc_df['Display_Desc'] = misc_df[m_desc].astype(str).str.strip()
    
    # Mapping dictionaries
    id_to_desc = dict(zip(misc_df[m_id], misc_df['Display_Desc']))
    desc_to_id = dict(zip(misc_df['Display_Desc'], misc_df[m_id]))

    # Load VoucherDetail & VoucherHeader
    vd = read_table(user_mdb_path, "VoucherDetail")
    vh = read_table(user_mdb_path, "VoucherHeader")

    # Column Mapping from SQL Query:
    # H.Voucher_IDNO = D.VouDtl_VouId
    vh_id = find_col(vh, ["Voucher_IDNO", "Voucher_IdNo", "VH_IdNo", "IdNo"])
    vd_vou_id = find_col(vd, ["VouDtl_VouId", "VouDtl_VHId", "VD_VHIdNo", "VouId"])
    
    # D.VouDtl_AccountId = M.Misc_IdNo
    vd_acc_id = find_col(vd, ["VouDtl_AccountId", "VD_AccountIdNo", "AccountId"])
    
    # D.VouDtl_DrCrId (101=Dr, 102=Cr), D.VouDtl_Amount
    vd_drcr_id = find_col(vd, ["VouDtl_DrCrId", "VD_DrCrId", "DrCrId"])
    vd_amount = find_col(vd, ["VouDtl_Amount", "VD_Amount", "Amount"])
    
    # H.Voucher_Date, H.Voucher_No, H.Voucher_LocationId
    vh_date = find_col(vh, ["Voucher_Date", "VH_VoucherDate", "Date"])
    vh_no = find_col(vh, ["Voucher_No", "Voucher_Number", "VH_VoucherNo", "VouNo"])
    vh_loc = find_col(vh, ["Voucher_LocationId", "VH_LocationIdNo", "LocationId"])

    # Supplementary voucher columns (if any)
    vd_supp_no = find_col(vd, ["VouDtl_SuppVoucherNo", "VD_SuppVoucherNo", "SuppVoucherNo", "SuppVouNo"])
    vd_supp_date = find_col(vd, ["VouDtl_SuppVoucherDate", "VD_SuppVoucherDate", "SuppVoucherDate", "SuppVouDate"])

    # Clean numeric types
    vd[vd_acc_id] = pd.to_numeric(vd[vd_acc_id], errors='coerce')
    vd[vd_drcr_id] = pd.to_numeric(vd[vd_drcr_id], errors='coerce')
    vd[vd_amount] = pd.to_numeric(vd[vd_amount], errors='coerce').fillna(0.0)

    # Active accounts list
    used_acc_ids = set(vd[vd_acc_id].dropna().unique())
    acc_filter = misc_df[misc_df[m_id].isin(used_acc_ids)].copy()
    acc_list = sorted(acc_filter['Display_Desc'].dropna().unique().tolist())

    # Active locations list
    used_loc_ids = set(pd.to_numeric(vh[vh_loc], errors='coerce').dropna().unique())
    loc_filter = misc_df[misc_df[m_id].isin(used_loc_ids)].copy()
    loc_list = sorted(loc_filter['Display_Desc'].dropna().unique().tolist())

    report_type = st.sidebar.radio("Select Report Category", ["Account General Ledger", "Trial Balance (TB)", "Raw Table Browser"])

    # ==========================================================
    # 1. ACCOUNT GENERAL LEDGER
    # ==========================================================
    if report_type == "Account General Ledger":
        st.subheader("📖 Account General Ledger")

        c1, c2, c3, c4 = st.columns([2.5, 1.5, 1, 1])
        with c1:
            selected_acc = st.selectbox("Select Ledger Account", acc_list)
            target_acc_id = desc_to_id[selected_acc]
        with c2:
            selected_loc = st.selectbox("Location Filter", ["All Locations"] + loc_list)
        with c3:
            start_date = st.date_input("Start Date", datetime.date(2026, 4, 1))
        with c4:
            end_date = st.date_input("Last Date", datetime.date(2026, 10, 14))

        if st.button("Generate Ledger Report", type="primary"):
            with st.spinner("Processing voucher transactions..."):
                # Filter VoucherDetail by Target Account
                filtered_vd = vd[vd[vd_acc_id] == float(target_acc_id)].copy()

                # Inner Join H & D: H.Voucher_IDNO = D.VouDtl_VouId
                merged = pd.merge(filtered_vd, vh, left_on=vd_vou_id, right_on=vh_id, suffixes=('', '_h'))

                # Filter by Location if chosen
                if selected_loc != "All Locations":
                    chosen_loc_id = desc_to_id[selected_loc]
                    merged = merged[merged[vh_loc] == chosen_loc_id]

                # Clean Date
                merged['Clean_Date'] = pd.to_datetime(merged[vh_date], errors='coerce').dt.date

                # Calculate Opening Balance (Transactions before Start Date: Voucher_Date < start_date)
                prev_records = merged[merged['Clean_Date'] < start_date]
                prev_dr = prev_records[prev_records[vd_drcr_id] == 101][vd_amount].sum()
                prev_cr = prev_records[prev_records[vd_drcr_id] == 102][vd_amount].sum()
                op_bal = float(prev_dr - prev_cr)

                # Current Period Transactions: Start Date <= Voucher_Date <= End Date
                mask = (merged['Clean_Date'] >= start_date) & (merged['Clean_Date'] <= end_date)
                ledger_rows = merged.loc[mask].copy()
                ledger_rows = ledger_rows.sort_values(by=['Clean_Date', vh_no])

                # Calculate Debit and Credit Amounts
                ledger_rows['Debit Amount'] = ledger_rows.apply(
                    lambda r: r[vd_amount] if r[vd_drcr_id] == 101 else 0.0, axis=1
                )
                ledger_rows['Credit Amount'] = ledger_rows.apply(
                    lambda r: r[vd_amount] if r[vd_drcr_id] == 102 else 0.0, axis=1
                )
                ledger_rows['Net'] = ledger_rows['Debit Amount'] - ledger_rows['Credit Amount']

                # Running Balance
                ledger_rows['Running Balance'] = op_bal + ledger_rows['Net'].cumsum()
                ledger_rows['Running Balance Text'] = ledger_rows['Running Balance'].apply(
                    lambda x: f"{abs(x):,.2f}Dr" if x >= 0 else f"{abs(x):,.2f}Cr"
                )

                # Map Location Name from MiscMaster
                ledger_rows['Location Name'] = ledger_rows[vh_loc].map(id_to_desc).fillna(ledger_rows[vh_loc].astype(str))

                final_table = pd.DataFrame({
                    "Voucher Date": pd.to_datetime(ledger_rows['Clean_Date']).dt.strftime('%d-%b-%Y'),
                    "Voucher No.": ledger_rows[vh_no],
                    "Supp.VouNo": ledger_rows[vd_supp_no].fillna('') if vd_supp_no in ledger_rows.columns else '',
                    "Supp.VouDate": ledger_rows[vd_supp_date].fillna('') if vd_supp_date in ledger_rows.columns else '',
                    "Debit Amount": ledger_rows['Debit Amount'],
                    "Credit Amount": ledger_rows['Credit Amount'],
                    "Location Name": ledger_rows['Location Name'],
                    "Running Balance": ledger_rows['Running Balance Text']
                })

                st.markdown("---")
                st.markdown(f"**Account Desc.  :** `{selected_acc}`")
                st.markdown(f"**Account Opening :** `{abs(op_bal):,.2f}-{'Dr' if op_bal >= 0 else 'Cr'}`")

                total_dr = final_table['Debit Amount'].sum()
                total_cr = final_table['Credit Amount'].sum()
                closing = op_bal + total_dr - total_cr

                m1, m2, m3 = st.columns(3)
                m1.metric("Total Debit", f"₹ {total_dr:,.2f}")
                m2.metric("Total Credit", f"₹ {total_cr:,.2f}")
                m3.metric("Closing Balance", f"{abs(closing):,.2f} {'Dr' if closing >= 0 else 'Cr'}")

                st.dataframe(final_table, use_container_width=True, height=540)

                # Excel Export
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine='openpyxl') as wr:
                    final_table.to_excel(wr, index=False, sheet_name="Ledger")
                st.download_button(
                    label="📥 Download Continuous Ledger (Excel)",
                    data=out.getvalue(),
                    file_name=f"Ledger_{selected_acc[:20]}_{start_date}_to_{end_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    # ==========================================================
    # 2. TRIAL BALANCE (TB)
    # ==========================================================
    elif report_type == "Trial Balance (TB)":
        st.subheader("⚖️ Account Trial Balance (Direct Query Engine)")

        t1, t2, t3 = st.columns([1, 1, 1])
        with t1:
            tb_type = st.selectbox("Trial Balance Type", ["Merged Single", "Merged Splitted", "Separate"])
        with t2:
            tb_start = st.date_input("Start Date", datetime.date(2026, 4, 1), key="tbs")
        with t3:
            tb_end = st.date_input("Last Date", datetime.date(2027, 3, 31), key="tbe")

        if st.button("Generate Trial Balance", type="primary"):
            with st.spinner("Calculating Trial Balance using VoucherDetail & VoucherHeader..."):
                # Join H and D
                merged_tb = pd.merge(vd, vh, left_on=vd_vou_id, right_on=vh_id, suffixes=('', '_h'))
                merged_tb['Clean_Date'] = pd.to_datetime(merged_tb[vh_date], errors='coerce').dt.date

                # Year Opening / Previous (Date < tb_start)
                merged_tb['PrevDr'] = merged_tb.apply(
                    lambda r: r[vd_amount] if (r[vd_drcr_id] == 101 and r['Clean_Date'] < tb_start) else 0.0, axis=1
                )
                merged_tb['PrevCr'] = merged_tb.apply(
                    lambda r: r[vd_amount] if (r[vd_drcr_id] == 102 and r['Clean_Date'] < tb_start) else 0.0, axis=1
                )

                # Current Period (tb_start <= Date <= tb_end)
                merged_tb['CurrDr'] = merged_tb.apply(
                    lambda r: r[vd_amount] if (r[vd_drcr_id] == 101 and tb_start <= r['Clean_Date'] <= tb_end) else 0.0, axis=1
                )
                merged_tb['CurrCr'] = merged_tb.apply(
                    lambda r: r[vd_amount] if (r[vd_drcr_id] == 102 and tb_start <= r['Clean_Date'] <= tb_end) else 0.0, axis=1
                )

                # Map Names
                merged_tb['Account_Name'] = merged_tb[vd_acc_id].map(id_to_desc).fillna(merged_tb[vd_acc_id].astype(str))
                merged_tb['Location_Name'] = merged_tb[vh_loc].map(id_to_desc).fillna(merged_tb[vh_loc].astype(str))

                if tb_type == "Merged Single":
                    tb_res = merged_tb.groupby(['Account_Name']).agg({
                        'PrevDr': 'sum',
                        'PrevCr': 'sum',
                        'CurrDr': 'sum',
                        'CurrCr': 'sum'
                    }).reset_index()

                    # Net Balances
                    tb_res['Opening Net Dr'] = tb_res.apply(lambda r: max(0.0, r['PrevDr'] - r['PrevCr']), axis=1)
                    tb_res['Opening Net Cr'] = tb_res.apply(lambda r: max(0.0, r['PrevCr'] - r['PrevDr']), axis=1)
                    tb_res['Closing Dr'] = tb_res.apply(
                        lambda r: max(0.0, (r['Opening Net Dr'] + r['CurrDr']) - (r['Opening Net Cr'] + r['CurrCr'])), axis=1
                    )
                    tb_res['Closing Cr'] = tb_res.apply(
                        lambda r: max(0.0, (r['Opening Net Cr'] + r['CurrCr']) - (r['Opening Net Dr'] + r['CurrDr'])), axis=1
                    )

                    # Filter zero activity rows
                    tb_res = tb_res[
                        (tb_res['Opening Net Dr'] > 0) | (tb_res['Opening Net Cr'] > 0) | 
                        (tb_res['CurrDr'] > 0) | (tb_res['CurrCr'] > 0)
                    ].sort_values(by='Account_Name')

                    view_tb = pd.DataFrame({
                        "Account Code & Description": tb_res['Account_Name'],
                        "Year Opening Dr": tb_res['Opening Net Dr'],
                        "Year Opening Cr": tb_res['Opening Net Cr'],
                        "Current Dr Trans": tb_res['CurrDr'],
                        "Current Cr Trans": tb_res['CurrCr'],
                        "Closing Balance Dr": tb_res['Closing Dr'],
                        "Closing Balance Cr": tb_res['Closing Cr']
                    })

                    st.dataframe(view_tb, use_container_width=True, height=600)

                    out_tb = io.BytesIO()
                    with pd.ExcelWriter(out_tb, engine='openpyxl') as wr:
                        view_tb.to_excel(wr, index=False, sheet_name="TB_Merged_Single")
                    st.download_button("📥 Download Merged Single TB (Excel)", out_tb.getvalue(), "TB_Merged_Single.xlsx")

                elif tb_type == "Merged Splitted":
                    tb_split = merged_tb.groupby(['Account_Name', 'Location_Name']).agg({
                        'PrevDr': 'sum',
                        'PrevCr': 'sum',
                        'CurrDr': 'sum',
                        'CurrCr': 'sum'
                    }).reset_index()

                    tb_split['Closing Dr'] = tb_split.apply(
                        lambda r: max(0.0, (r['PrevDr'] + r['CurrDr']) - (r['PrevCr'] + r['CurrCr'])), axis=1
                    )
                    tb_split['Closing Cr'] = tb_split.apply(
                        lambda r: max(0.0, (r['PrevCr'] + r['CurrCr']) - (r['PrevDr'] + r['CurrDr'])), axis=1
                    )

                    st.dataframe(tb_split, use_container_width=True, height=600)

                    out_tb = io.BytesIO()
                    with pd.ExcelWriter(out_tb, engine='openpyxl') as wr:
                        tb_split.to_excel(wr, index=False, sheet_name="TB_Merged_Splitted")
                    st.download_button("📥 Download Merged Splitted TB (Excel)", out_tb.getvalue(), "TB_Merged_Splitted.xlsx")

                elif tb_type == "Separate":
                    sel_loc_tb = st.selectbox("Select Location for Separate TB", loc_list)
                    loc_id_target = desc_to_id[sel_loc_tb]
                    
                    loc_data = merged_tb[merged_tb[vh_loc] == loc_id_target].groupby(['Account_Name']).agg({
                        'PrevDr': 'sum',
                        'PrevCr': 'sum',
                        'CurrDr': 'sum',
                        'CurrCr': 'sum'
                    }).reset_index()

                    st.dataframe(loc_data, use_container_width=True, height=600)

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
    st.code(traceback.format_exc())
