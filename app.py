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

# Session State Setup
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""

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

if not os.path.exists(user_mdb_path):
    st.info("👋 Pehli baar setup karne ke liye apna `.mdb` file upload karein.")
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

    # Load MiscMaster for Codes & Descriptions
    misc_df = read_table(user_mdb_path, "MiscMaster")
    m_id = find_col(misc_df, ["Misc_IdNo", "MiscIdNo", "IdNo", "Id"])
    m_desc = find_col(misc_df, ["Misc_Desc", "Misc_Name", "MiscName", "Desc", "Name"])
    m_code = find_col(misc_df, ["Misc_Code", "MiscCode", "Code"])

    misc_df[m_id] = pd.to_numeric(misc_df[m_id], errors='coerce')
    misc_df['Clean_Code'] = misc_df[m_code].astype(str).str.strip()
    misc_df['Clean_Name'] = misc_df[m_desc].astype(str).str.strip()
    misc_df['Account_Code_Desc'] = misc_df['Clean_Code'] + "-" + misc_df['Clean_Name']

    id_to_desc = dict(zip(misc_df[m_id], misc_df['Account_Code_Desc']))
    desc_to_id = dict(zip(misc_df['Account_Code_Desc'], misc_df[m_id]))

    # Load Core Tables
    vd = read_table(user_mdb_path, "VoucherDetail")
    vh = read_table(user_mdb_path, "VoucherHeader")
    bal_data = read_table(user_mdb_path, "BalanceData") if "BalanceData" in tables else pd.DataFrame()

    vh_id = find_col(vh, ["Voucher_IDNO", "Voucher_IdNo", "VH_IdNo", "IdNo"])
    vd_vou_id = find_col(vd, ["VouDtl_VouId", "VouDtl_VHId", "VD_VHIdNo", "VouId"])
    vd_acc_id = find_col(vd, ["VouDtl_AccountId", "VD_AccountIdNo", "AccountId"])
    vd_drcr_id = find_col(vd, ["VouDtl_DrCrId", "VD_DrCrId", "DrCrId"])
    vd_amount = find_col(vd, ["VouDtl_Amount", "VD_Amount", "Amount"])
    
    vh_date = find_col(vh, ["Voucher_Date", "VH_VoucherDate", "Date"])
    vh_no = find_col(vh, ["Voucher_No", "Voucher_Number", "VH_VoucherNo", "VouNo"])
    vh_loc = find_col(vh, ["Voucher_LocationId", "VH_LocationIdNo", "LocationId"])

    vd_supp_no = find_col(vd, ["VouDtl_SuppVoucherNo", "VD_SuppVoucherNo", "SuppVoucherNo"])
    vd_supp_date = find_col(vd, ["VouDtl_SuppVoucherDate", "VD_SuppVoucherDate", "SuppVoucherDate"])

    vd[vd_acc_id] = pd.to_numeric(vd[vd_acc_id], errors='coerce')
    vd[vd_drcr_id] = pd.to_numeric(vd[vd_drcr_id], errors='coerce')
    vd[vd_amount] = pd.to_numeric(vd[vd_amount], errors='coerce').fillna(0.0)

    # Active lists
    used_acc_ids = set(vd[vd_acc_id].dropna().unique())
    acc_filter = misc_df[misc_df[m_id].isin(used_acc_ids)].copy()
    acc_list = sorted(acc_filter['Account_Code_Desc'].dropna().unique().tolist())

    used_loc_ids = set(pd.to_numeric(vh[vh_loc], errors='coerce').dropna().unique())
    loc_filter = misc_df[misc_df[m_id].isin(used_loc_ids)].copy()
    loc_list = sorted(loc_filter['Account_Code_Desc'].dropna().unique().tolist())

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
                filtered_vd = vd[vd[vd_acc_id] == float(target_acc_id)].copy()
                merged = pd.merge(filtered_vd, vh, left_on=vd_vou_id, right_on=vh_id, suffixes=('', '_vh'))

                if selected_loc != "All Locations":
                    chosen_loc_id = desc_to_id[selected_loc]
                    merged = merged[merged[vh_loc] == chosen_loc_id]

                merged['Clean_Date'] = pd.to_datetime(merged[vh_date], errors='coerce').dt.date

                # Opening Balance from BalanceData
                op_bal = 0.0
                if not bal_data.empty:
                    b_acc = find_col(bal_data, ["Balance_AccountIdNo", "AccountIdNo"])
                    b_loc = find_col(bal_data, ["Balance_LocationIdNo", "LocationIdNo"])
                    b_dr = find_col(bal_data, ["Balance_DebitAmount", "DebitAmount"])
                    b_cr = find_col(bal_data, ["Balance_CreditAmount", "CreditAmount"])

                    bal_match = bal_data[pd.to_numeric(bal_data[b_acc], errors='coerce') == float(target_acc_id)]
                    if selected_loc != "All Locations":
                        bal_match = bal_match[pd.to_numeric(bal_match[b_loc], errors='coerce') == chosen_loc_id]

                    if not bal_match.empty:
                        d_sum = pd.to_numeric(bal_match[b_dr], errors='coerce').fillna(0.0).sum()
                        c_sum = pd.to_numeric(bal_match[b_cr], errors='coerce').fillna(0.0).sum()
                        op_bal = d_sum - c_sum

                fy_start = datetime.date(2026, 4, 1)
                if start_date > fy_start:
                    interim = merged[(merged['Clean_Date'] >= fy_start) & (merged['Clean_Date'] < start_date)]
                    int_dr = interim[interim[vd_drcr_id] == 101][vd_amount].sum()
                    int_cr = interim[interim[vd_drcr_id] == 102][vd_amount].sum()
                    op_bal += float(int_dr - int_cr)

                mask = (merged['Clean_Date'] >= start_date) & (merged['Clean_Date'] <= end_date)
                ledger_rows = merged.loc[mask].copy().sort_values(by=['Clean_Date', vh_no])

                ledger_rows['Debit Amount'] = ledger_rows.apply(lambda r: r[vd_amount] if r[vd_drcr_id] == 101 else 0.0, axis=1)
                ledger_rows['Credit Amount'] = ledger_rows.apply(lambda r: r[vd_amount] if r[vd_drcr_id] == 102 else 0.0, axis=1)
                ledger_rows['Net'] = ledger_rows['Debit Amount'] - ledger_rows['Credit Amount']

                ledger_rows['Running Balance'] = op_bal + ledger_rows['Net'].cumsum()
                ledger_rows['Running Balance Text'] = ledger_rows['Running Balance'].apply(
                    lambda x: f"{abs(x):,.2f}Dr" if x >= 0 else f"{abs(x):,.2f}Cr"
                )

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
    # 2. TRIAL BALANCE (TB) - EXACT 12 COLUMNS & 2 TYPES
    # ==========================================================
    elif report_type == "Trial Balance (TB)":
        st.subheader("⚖️ Account Trial Balance (12-Column Engine)")

        t1, t2, t3, t4 = st.columns([1.5, 1.5, 1, 1])
        with t1:
            tb_type = st.selectbox("Trial Balance Type", ["Merged Single", "Separate"])
        with t2:
            selected_tb_loc = st.selectbox("Location Filter", ["All Locations"] + loc_list)
        with t3:
            tb_start = st.date_input("Start Date", datetime.date(2026, 4, 1), key="tbs")
        with t4:
            tb_end = st.date_input("Last Date", datetime.date(2027, 3, 31), key="tbe")

        if st.button("Generate Trial Balance", type="primary"):
            with st.spinner("Calculating 12-Column Trial Balance..."):
                fy_start = datetime.date(2026, 4, 1)

                # --- STEP A: Opening Balance from BalanceData ---
                b_acc = find_col(bal_data, ["Balance_AccountIdNo", "AccountIdNo"])
                b_loc = find_col(bal_data, ["Balance_LocationIdNo", "LocationIdNo"])
                b_dr = find_col(bal_data, ["Balance_DebitAmount", "DebitAmount"])
                b_cr = find_col(bal_data, ["Balance_CreditAmount", "CreditAmount"])

                bal_df = bal_data.copy()
                bal_df[b_acc] = pd.to_numeric(bal_df[b_acc], errors='coerce')
                bal_df[b_loc] = pd.to_numeric(bal_df[b_loc], errors='coerce')
                bal_df['OpenDr'] = pd.to_numeric(bal_df[b_dr], errors='coerce').fillna(0.0)
                bal_df['OpenCr'] = pd.to_numeric(bal_df[b_cr], errors='coerce').fillna(0.0)

                if selected_tb_loc != "All Locations" and tb_type == "Separate":
                    chosen_loc_id = desc_to_id[selected_tb_loc]
                    bal_df = bal_df[bal_df[b_loc] == chosen_loc_id]

                # --- STEP B: Transactions from VoucherDetail + Header ---
                merged_v = pd.merge(vd, vh, left_on=vd_vou_id, right_on=vh_id, suffixes=('', '_vh'))
                merged_v['Clean_Date'] = pd.to_datetime(merged_v[vh_date], errors='coerce').dt.date

                if selected_tb_loc != "All Locations" and tb_type == "Separate":
                    chosen_loc_id = desc_to_id[selected_tb_loc]
                    merged_v = merged_v[merged_v[vh_loc] == chosen_loc_id]

                # 1. Previous Period Transactions (FY Start to Start Date - 1 day)
                prev_mask = (merged_v['Clean_Date'] >= fy_start) & (merged_v['Clean_Date'] < tb_start)
                prev_v = merged_v.loc[prev_mask].copy()
                prev_v['PDr'] = prev_v.apply(lambda r: r[vd_amount] if r[vd_drcr_id] == 101 else 0.0, axis=1)
                prev_v['PCr'] = prev_v.apply(lambda r: r[vd_amount] if r[vd_drcr_id] == 102 else 0.0, axis=1)

                # 2. Current Period Transactions (Start Date to End Date)
                curr_mask = (merged_v['Clean_Date'] >= tb_start) & (merged_v['Clean_Date'] <= tb_end)
                curr_v = merged_v.loc[curr_mask].copy()
                curr_v['CDr'] = curr_v.apply(lambda r: r[vd_amount] if r[vd_drcr_id] == 101 else 0.0, axis=1)
                curr_v['CCr'] = curr_v.apply(lambda r: r[vd_amount] if r[vd_drcr_id] == 102 else 0.0, axis=1)

                # --- STEP C: Grouping and Merging for 12 Columns ---
                if tb_type == "Merged Single":
                    op_agg = bal_df.groupby(b_acc).agg({'OpenDr': 'sum', 'OpenCr': 'sum'}).reset_index()
                    prev_agg = prev_v.groupby(vd_acc_id).agg({'PDr': 'sum', 'PCr': 'sum'}).reset_index()
                    curr_agg = curr_v.groupby(vd_acc_id).agg({'CDr': 'sum', 'CCr': 'sum'}).reset_index()

                    # Merge all
                    tb_m = pd.merge(op_agg, prev_agg, left_on=b_acc, right_on=vd_acc_id, how='outer')
                    tb_m['AccountId'] = tb_m[b_acc].combine_first(tb_m[vd_acc_id])
                    tb_m = pd.merge(tb_m, curr_agg, left_on='AccountId', right_on=vd_acc_id, how='outer')
                    tb_m['AccountId'] = tb_m['AccountId'].combine_first(tb_m[vd_acc_id])

                    tb_m['Location'] = "All Locations"
                    tb_m['Account Code'] = tb_m['AccountId'].map(id_to_desc).fillna(tb_m['AccountId'].astype(str))

                    tb_m['Opening Dr'] = tb_m['OpenDr'].fillna(0.0)
                    tb_m['Opening Cr'] = tb_m['OpenCr'].fillna(0.0)
                    tb_m['Prev Trn Dr'] = tb_m['PDr'].fillna(0.0)
                    tb_m['Prev Trn Cr'] = tb_m['PCr'].fillna(0.0)
                    tb_m['Curr Trn Dr'] = tb_m['CDr'].fillna(0.0)
                    tb_m['Curr Trn Cr'] = tb_m['CCr'].fillna(0.0)

                    # Closing & Progressive calculation
                    def calc_12_cols(r):
                        op_net = (r['Opening Dr'] + r['Prev Trn Dr']) - (r['Opening Cr'] + r['Prev Trn Dr']) # simplified
                        # Let's use exact algebraic sum
                        dr_tot = r['Opening Dr'] + r['Prev Trn Dr'] + r['Curr Trn Dr']
                        cr_tot = r['Opening Cr'] + r['Prev Trn Cr'] + r['Curr Trn Cr']
                        
                        op_sum = r['Opening Dr'] - r['Opening Cr']
                        prev_sum = r['Prev Trn Dr'] - r['Prev Trn Cr']
                        open_tot = op_sum + prev_sum
                        
                        od = open_tot if open_tot > 0 else 0.0
                        oc = abs(open_tot) if open_tot < 0 else 0.0

                        net_close = open_tot + (r['Curr Trn Dr'] - r['Curr Trn Cr'])
                        cd = net_close if net_close > 0 else 0.0
                        cc = abs(net_close) if net_close < 0 else 0.0

                        return pd.Series([od, oc, cd, cc, dr_tot, cr_tot])

                    tb_m[['Opening Dr', 'Opening Cr', 'Closing Dr', 'Closing Cr', 'Prog Dr', 'Prog Cr']] = tb_m.apply(calc_12_cols, axis=1)

                    res_final = tb_m[
                        (tb_m['Opening Dr'] > 0) | (tb_m['Opening Cr'] > 0) |
                        (tb_m['Prev Trn Dr'] > 0) | (tb_m['Prev Trn Cr'] > 0) |
                        (tb_m['Curr Trn Dr'] > 0) | (tb_m['Curr Trn Cr'] > 0)
                    ].sort_values(by='Account Code')

                    cols_12 = [
                        'Location', 'Account Code', 
                        'Opening Dr', 'Opening Cr', 
                        'Prev Trn Dr', 'Prev Trn Cr', 
                        'Curr Trn Dr', 'Curr Trn Cr', 
                        'Closing Dr', 'Closing Cr', 
                        'Prog Dr', 'Prog Cr'
                    ]
                    final_csv = res_final[cols_12].reset_index(drop=True)

                    st.dataframe(final_csv, use_container_width=True, height=620)

                    out_tb = io.BytesIO()
                    with pd.ExcelWriter(out_tb, engine='openpyxl') as wr:
                        final_csv.to_excel(wr, index=False, sheet_name="TB_Merged_Single")
                    st.download_button("📥 Download Merged Single TB (Excel)", out_tb.getvalue(), "TB_Merged_Single.xlsx")

                elif tb_type == "Separate":
                    if selected_tb_loc == "All Locations":
                        st.warning("Kripya Separate Trial Balance ke liye koi ek specific Location select karein.")
                    else:
                        op_agg = bal_df.groupby([b_loc, b_acc]).agg({'OpenDr': 'sum', 'OpenCr': 'sum'}).reset_index()
                        prev_agg = prev_v.groupby([vh_loc, vd_acc_id]).agg({'PDr': 'sum', 'PCr': 'sum'}).reset_index()
                        curr_agg = curr_v.groupby([vh_loc, vd_acc_id]).agg({'CDr': 'sum', 'CCr': 'sum'}).reset_index()

                        tb_s = pd.merge(op_agg, prev_agg, left_on=[b_loc, b_acc], right_on=[vh_loc, vd_acc_id], how='outer')
                        tb_s['LocationId'] = tb_s[b_loc].combine_first(tb_s[vh_loc])
                        tb_s['AccountId'] = tb_s[b_acc].combine_first(tb_s[vd_acc_id])
                        tb_s = pd.merge(tb_s, curr_agg, left_on=['LocationId', 'AccountId'], right_on=[vh_loc, vd_acc_id], how='outer')

                        tb_s['Location'] = tb_s['LocationId'].map(id_to_desc).fillna(tb_s['LocationId'].astype(str))
                        tb_s['Account Code'] = tb_s['AccountId'].map(id_to_desc).fillna(tb_s['AccountId'].astype(str))

                        tb_s['Opening Dr'] = tb_s['OpenDr'].fillna(0.0)
                        tb_s['Opening Cr'] = tb_s['OpenCr'].fillna(0.0)
                        tb_s['Prev Trn Dr'] = tb_s['PDr'].fillna(0.0)
                        tb_s['Prev Trn Cr'] = tb_s['PCr'].fillna(0.0)
                        tb_s['Curr Trn Dr'] = tb_s['CDr'].fillna(0.0)
                        tb_s['Curr Trn Cr'] = tb_s['CCr'].fillna(0.0)

                        tb_s[['Opening Dr', 'Opening Cr', 'Closing Dr', 'Closing Cr', 'Prog Dr', 'Prog Cr']] = tb_s.apply(calc_12_cols, axis=1)

                        chosen_loc_name = selected_tb_loc
                        sep_final = tb_s[tb_s['Location'] == chosen_loc_name].sort_values(by='Account Code')

                        cols_12 = [
                            'Location', 'Account Code', 
                            'Opening Dr', 'Opening Cr', 
                            'Prev Trn Dr', 'Prev Trn Cr', 
                            'Curr Trn Dr', 'Curr Trn Cr', 
                            'Closing Dr', 'Closing Cr', 
                            'Prog Dr', 'Prog Cr'
                        ]
                        final_sep = sep_final[cols_12].reset_index(drop=True)

                        st.dataframe(final_sep, use_container_width=True, height=620)

                        out_tb2 = io.BytesIO()
                        with pd.ExcelWriter(out_tb2, engine='openpyxl') as wr:
                            final_sep.to_excel(wr, index=False, sheet_name="TB_Separate")
                        st.download_button("📥 Download Separate TB (Excel)", out_tb2.getvalue(), f"TB_Separate_{chosen_loc_name[:15]}.xlsx")

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
