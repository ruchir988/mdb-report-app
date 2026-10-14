import streamlit as st
import pandas as pd
import subprocess
import tempfile
import os
import io
import datetime
import traceback

st.set_page_config(page_title="AVVNL Accounts & Reports", layout="wide")
st.title("⚡ AVVNL Account Reports Engine")

# --- Helper Functions for Linux / MDBTools ---
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

# Helper to safely locate columns regardless of exact casing or prefix
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

uploaded_file = st.file_uploader("Upload .mdb Database File", type=["mdb"])

if uploaded_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mdb") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    try:
        tables = get_tables(tmp_path)
        
        # 1. Load Account Master
        if "AccountMaster" in tables:
            acc_master = read_table(tmp_path, "AccountMaster")
            acc_id_col = find_col(acc_master, ["Account_IdNo", "AccountId", "IdNo", "Id"])
            acc_code_col = find_col(acc_master, ["Account_Code", "AccountCode", "Code"])
            acc_name_col = find_col(acc_master, ["Account_Name", "AccountName", "Name", "Desc"])

            acc_master['Display_Acc'] = (
                acc_master[acc_code_col].astype(str) + " - " + acc_master[acc_name_col].astype(str)
            )
            acc_list = sorted(acc_master['Display_Acc'].dropna().unique().tolist())
        else:
            st.error("AccountMaster table is database me nahi mila.")
            st.stop()

        # 2. Load Location Master
        loc_map = {}
        if "LocationMaster" in tables:
            loc_master = read_table(tmp_path, "LocationMaster")
            loc_id_col = find_col(loc_master, ["Location_IdNo", "LocationId", "IdNo", "Id"])
            loc_code_col = find_col(loc_master, ["Location_Code", "LocationCode", "Code"])
            loc_name_col = find_col(loc_master, ["Location_Name", "LocationName", "Name"])
            
            loc_master['Display_Loc'] = (
                loc_master[loc_code_col].astype(str) + "-" + loc_master[loc_name_col].astype(str)
            )
            loc_map = dict(zip(loc_master[loc_id_col], loc_master['Display_Loc']))

        # Sidebar navigation
        report_type = st.sidebar.radio("Select Report Category", ["Account General Ledger", "Trial Balance (TB)", "Raw Table Browser"])

        # ==========================================================
        # 1. ACCOUNT GENERAL LEDGER
        # ==========================================================
        if report_type == "Account General Ledger":
            st.subheader("📖 Account General Ledger")
            
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                selected_acc = st.selectbox("Select Ledger Account", acc_list)
                acc_selected_code = selected_acc.split(" - ")[0].strip()
            with c2:
                start_date = st.date_input("Start Date", datetime.date(2026, 4, 1))
            with c3:
                end_date = st.date_input("Last Date", datetime.date(2026, 10, 14))

            if st.button("Generate Ledger Report", type="primary"):
                with st.spinner("Processing ledger entries..."):
                    vd = read_table(tmp_path, "VoucherDetail") if "VoucherDetail" in tables else pd.DataFrame()
                    vh = read_table(tmp_path, "VoucherHeader") if "VoucherHeader" in tables else pd.DataFrame()
                    bal_data = read_table(tmp_path, "BalanceData") if "BalanceData" in tables else pd.DataFrame()

                    if vd.empty or vh.empty:
                        st.warning("VoucherDetail ya VoucherHeader table empty hai.")
                        st.stop()

                    # Exact column matching from AVVNL Access Structure
                    vd_vh_id = find_col(vd, ["VD_VHIdNo", "VHIdNo", "VH_Id", "HeaderId"])
                    vh_pk = find_col(vh, ["VH_IdNo", "VHIdNo", "VH_Id", "IdNo"])
                    vd_acc_id = find_col(vd, ["VD_AccountIdNo", "AccountIdNo", "AccountId"])
                    
                    vh_date_col = find_col(vh, ["VH_VoucherDate", "VoucherDate", "Date"])
                    vh_no_col = find_col(vh, ["VH_VoucherNo", "VoucherNo", "VouNo"])
                    
                    vd_dr_col = find_col(vd, ["VD_DebitAmount", "DebitAmount", "Debit"])
                    vd_cr_col = find_col(vd, ["VD_CreditAmount", "CreditAmount", "Credit"])
                    vd_loc_col = find_col(vd, ["VD_LocationIdNo", "LocationIdNo", "LocationId"])
                    vd_supp_no = find_col(vd, ["VD_SuppVoucherNo", "SuppVoucherNo"])
                    vd_supp_date = find_col(vd, ["VD_SuppVoucherDate", "SuppVoucherDate"])

                    # Target Account ID
                    acc_match = acc_master[acc_master[acc_code_col] == acc_selected_code]
                    if acc_match.empty:
                        st.error("Account ID match nahi hua.")
                        st.stop()
                    target_acc_id = acc_match.iloc[0][acc_id_col]

                    # Filter transactions for selected account
                    vd_filtered = vd[vd[vd_acc_id] == target_acc_id].copy()

                    # Merge Voucher Detail with Header
                    merged_v = pd.merge(vd_filtered, vh, left_on=vd_vh_id, right_on=vh_pk, suffixes=('', '_vh'))

                    # Parse dates
                    merged_v['V_Date'] = pd.to_datetime(merged_v[vh_date_col], errors='coerce')
                    
                    # Filter Date Range
                    mask = (merged_v['V_Date'].dt.date >= start_date) & (merged_v['V_Date'].dt.date <= end_date)
                    ledger_df = merged_v.loc[mask].sort_values(by=['V_Date', vh_no_col])

                    # Calculate Opening Balance from BalanceData
                    op_bal = 0.0
                    if not bal_data.empty:
                        b_acc = find_col(bal_data, ["Balance_AccountIdNo", "AccountIdNo", "AccountId"])
                        b_dr = find_col(bal_data, ["Balance_DebitAmount", "DebitAmount", "Debit"])
                        b_cr = find_col(bal_data, ["Balance_CreditAmount", "CreditAmount", "Credit"])
                        
                        bal_rows = bal_data[bal_data[b_acc] == target_acc_id]
                        if not bal_rows.empty:
                            dr_sum = pd.to_numeric(bal_rows[b_dr], errors='coerce').fillna(0.0).sum()
                            cr_sum = pd.to_numeric(bal_rows[b_cr], errors='coerce').fillna(0.0).sum()
                            op_bal = dr_sum - cr_sum

                    # Amounts
                    ledger_df['Debit Amount'] = pd.to_numeric(ledger_df[vd_dr_col], errors='coerce').fillna(0.0)
                    ledger_df['Credit Amount'] = pd.to_numeric(ledger_df[vd_cr_col], errors='coerce').fillna(0.0)
                    ledger_df['Net'] = ledger_df['Debit Amount'] - ledger_df['Credit Amount']
                    
                    # Running balance calculation
                    ledger_df['Running Balance'] = op_bal + ledger_df['Net'].cumsum()
                    ledger_df['Running Balance Text'] = ledger_df['Running Balance'].apply(
                        lambda x: f"{abs(x):,.2f}Dr" if x >= 0 else f"{abs(x):,.2f}Cr"
                    )

                    # Location Name Mapping
                    ledger_df['Location Name'] = ledger_df[vd_loc_col].map(loc_map).fillna(ledger_df[vd_loc_col].astype(str))

                    # Clean Output DataFrame (Page headers strip logic: pure continuous table)
                    final_view = pd.DataFrame({
                        "Voucher Date": ledger_df['V_Date'].dt.strftime('%d-%b-%Y'),
                        "Voucher No.": ledger_df[vh_no_col],
                        "Supp.VouNo": ledger_df[vd_supp_no].fillna(''),
                        "Supp.VouDate": ledger_df[vd_supp_date].fillna(''),
                        "Debit Amount": ledger_df['Debit Amount'],
                        "Credit Amount": ledger_df['Credit Amount'],
                        "Location Name": ledger_df['Location Name'],
                        "Running Balance": ledger_df['Running Balance Text']
                    })

                    # Top Details Matching AVVNL text format
                    st.markdown("---")
                    st.markdown(f"**Account Desc. :** `{selected_acc}`")
                    st.markdown(f"**Account Opening:** `{abs(op_bal):,.2f}-{'Dr' if op_bal >= 0 else 'Cr'}`")
                    
                    total_dr = final_view['Debit Amount'].sum()
                    total_cr = final_view['Credit Amount'].sum()
                    final_bal = op_bal + total_dr - total_cr
                    
                    col_m1, col_m2, col_m3 = st.columns(3)
                    col_m1.metric("Total Debit", f"₹ {total_dr:,.2f}")
                    col_m2.metric("Total Credit", f"₹ {total_cr:,.2f}")
                    col_m3.metric("Closing Balance", f"{abs(final_bal):,.2f} {'Dr' if final_bal >= 0 else 'Cr'}")

                    # Display continuous clean rows without repeat headers
                    st.dataframe(final_view, use_container_width=True, height=520)

                    # 1-Click Excel Download
                    out = io.BytesIO()
                    with pd.ExcelWriter(out, engine='openpyxl') as wr:
                        final_view.to_excel(wr, index=False, sheet_name="Ledger")
                    st.download_button(
                        label="📥 Download Continuous Ledger (Excel)",
                        data=out.getvalue(),
                        file_name=f"Ledger_{acc_selected_code}_{start_date}_to_{end_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

        # ==========================================================
        # 2. TRIAL BALANCE (TB)
        # ==========================================================
        elif report_type == "Trial Balance (TB)":
            st.subheader("⚖️ Account Trial Balance")
            
            t1, t2, t3 = st.columns([1, 1, 1])
            with t1:
                tb_type = st.selectbox("Trial Balance Type", ["Merged Single", "Merged Splitted", "Separate"])
            with t2:
                tb_start = st.date_input("Start Date", datetime.date(2026, 4, 1), key="tbs")
            with t3:
                tb_end = st.date_input("Last Date", datetime.date(2027, 4, 1), key="tbe")

            if st.button("Generate Trial Balance", type="primary"):
                with st.spinner("Calculating Trial Balance..."):
                    bal_data = read_table(tmp_path, "BalanceData") if "BalanceData" in tables else pd.DataFrame()
                    if bal_data.empty:
                        st.warning("BalanceData table nahi mila.")
                        st.stop()

                    b_acc = find_col(bal_data, ["Balance_AccountIdNo", "AccountIdNo", "AccountId"])
                    b_loc = find_col(bal_data, ["Balance_LocationIdNo", "LocationIdNo", "LocationId"])
                    b_dr = find_col(bal_data, ["Balance_DebitAmount", "DebitAmount", "Debit"])
                    b_cr = find_col(bal_data, ["Balance_CreditAmount", "CreditAmount", "Credit"])

                    tb_df = pd.merge(bal_data, acc_master, left_on=b_acc, right_on=acc_id_col, how="left")
                    tb_df['Location_Display'] = tb_df[b_loc].map(loc_map).fillna(tb_df[b_loc].astype(str))
                    
                    tb_df['Year Opening Dr'] = pd.to_numeric(tb_df[b_dr], errors='coerce').fillna(0.0)
                    tb_df['Year Opening Cr'] = pd.to_numeric(tb_df[b_cr], errors='coerce').fillna(0.0)

                    if tb_type == "Merged Single":
                        tb_res = tb_df.groupby(['Display_Acc']).agg({
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
                        tb_res = tb_df.groupby(['Display_Acc', 'Location_Display']).agg({
                            'Year Opening Dr': 'sum',
                            'Year Opening Cr': 'sum'
                        }).reset_index()

                        st.dataframe(tb_res, use_container_width=True, height=600)

                        out_tb = io.BytesIO()
                        with pd.ExcelWriter(out_tb, engine='openpyxl') as wr:
                            tb_res.to_excel(wr, index=False, sheet_name="TB_Merged_Splitted")
                        st.download_button("📥 Download Merged Splitted TB (Excel)", out_tb.getvalue(), "TB_Merged_Splitted.xlsx")

                    elif tb_type == "Separate":
                        locs = sorted(tb_df['Location_Display'].dropna().unique().tolist())
                        chosen_loc = st.selectbox("Choose Location", locs)
                        
                        tb_loc = tb_df[tb_df['Location_Display'] == chosen_loc].groupby(['Display_Acc']).agg({
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
                df_view = read_table(tmp_path, sel_t)
                st.write(f"Total Rows: {len(df_view)} | Columns: {list(df_view.columns)}")
                st.dataframe(df_view.head(200), use_container_width=True)

    except Exception as e:
        st.error(f"Execution Error: {e}")
        st.code(traceback.format_exc())
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
