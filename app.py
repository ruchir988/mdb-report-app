import streamlit as st
import pandas as pd
import subprocess
import tempfile
import os
import io
import datetime

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
    return pd.read_csv(io.StringIO(res.stdout), low_memory=False)

# --- Upload Database ---
uploaded_file = st.file_uploader("Upload .mdb Database File", type=["mdb"])

if uploaded_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mdb") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    try:
        tables = get_tables(tmp_path)
        
        # Load core master tables
        with st.spinner("Loading Accounts & Locations Masters..."):
            acc_master = read_table(tmp_path, "AccountMaster") if "AccountMaster" in tables else pd.DataFrame()
            loc_master = read_table(tmp_path, "LocationMaster") if "LocationMaster" in tables else pd.DataFrame()
            
            # Map code columns dynamically
            acc_code_col = [c for c in acc_master.columns if 'Code' in c or 'code' in c]
            acc_name_col = [c for c in acc_master.columns if 'Name' in c or 'name' in c]
            acc_code = acc_code_col[0] if acc_code_col else acc_master.columns[1]
            acc_name = acc_name_col[0] if acc_name_col else acc_master.columns[2]

            acc_master['Display_Acc'] = acc_master[acc_code].astype(str) + " - " + acc_master[acc_name].astype(str)

        # Top Navigation
        report_type = st.sidebar.radio("Select Report Category", ["Account General Ledger", "Trial Balance (TB)", "Raw Table Browser"])

        # ==========================================================
        # 1. ACCOUNT GENERAL LEDGER
        # ==========================================================
        if report_type == "Account General Ledger":
            st.subheader("📖 Account General Ledger")
            
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                selected_acc = st.selectbox("Select Ledger Account", acc_master['Display_Acc'].tolist())
                acc_selected_code = selected_acc.split(" - ")[0].strip()
            with c2:
                start_date = st.date_input("Start Date", datetime.date(2026, 4, 1))
            with c3:
                end_date = st.date_input("Last Date", datetime.date(2026, 10, 14))

            # Fetch Transactions
            if st.button("Generate Ledger Report", type="primary"):
                with st.spinner("Processing ledger entries..."):
                    vd = read_table(tmp_path, "VoucherDetail") if "VoucherDetail" in tables else pd.DataFrame()
                    vh = read_table(tmp_path, "VoucherHeader") if "VoucherHeader" in tables else pd.DataFrame()
                    
                    if not vd.empty and not vh.empty:
                        # Normalize headers
                        vd.columns = [c.strip() for c in vd.columns]
                        vh.columns = [c.strip() for c in vh.columns]
                        
                        # Match headers & detail on VH_Id
                        vh_id_col = [c for c in vd.columns if 'vh' in c.lower() or 'header' in c.lower()][0]
                        vh_pk = [c for c in vh.columns if 'vh' in c.lower() or 'id' in c.lower()][0]
                        
                        merged_v = pd.merge(vd, vh, left_on=vh_id_col, right_on=vh_pk, suffixes=('', '_h'))
                        
                        # Filter by Account
                        acc_id_col = [c for c in vd.columns if 'acc' in c.lower()][0]
                        target_acc_id = acc_master[acc_master[acc_code] == acc_selected_code].iloc[0][0]
                        
                        ledger_df = merged_v[merged_v[acc_id_col] == target_acc_id].copy()
                        
                        # Date parsing
                        date_col = [c for c in ledger_df.columns if 'date' in c.lower()][0]
                        ledger_df['V_Date'] = pd.to_datetime(ledger_df[date_col], errors='coerce')
                        
                        # Filter Date Range
                        mask = (ledger_df['V_Date'].dt.date >= start_date) & (ledger_df['V_Date'].dt.date <= end_date)
                        ledger_df = ledger_df.loc[mask].sort_values(by='V_Date')
                        
                        dr_col = [c for c in ledger_df.columns if 'debit' in c.lower()][0]
                        cr_col = [c for c in ledger_df.columns if 'credit' in c.lower()][0]
                        
                        # Opening Balance Fetch from BalanceData
                        bal_data = read_table(tmp_path, "BalanceData") if "BalanceData" in tables else pd.DataFrame()
                        op_bal = 0.0
                        if not bal_data.empty:
                            bal_acc_col = [c for c in bal_data.columns if 'acc' in c.lower()][0]
                            bal_rows = bal_data[bal_data[bal_acc_col] == target_acc_id]
                            if not bal_rows.empty:
                                b_dr = [c for c in bal_rows.columns if 'dr' in c.lower() or 'debit' in c.lower()][0]
                                b_cr = [c for c in bal_rows.columns if 'cr' in c.lower() or 'credit' in c.lower()][0]
                                op_bal = float(bal_rows[b_dr].sum()) - float(bal_rows[b_cr].sum())

                        # Calculate Running Balance continuously
                        ledger_df['Debit Amount'] = pd.to_numeric(ledger_df[dr_col], errors='coerce').fillna(0.0)
                        ledger_df['Credit Amount'] = pd.to_numeric(ledger_df[cr_col], errors='coerce').fillna(0.0)
                        ledger_df['Net'] = ledger_df['Debit Amount'] - ledger_df['Credit Amount']
                        ledger_df['Running Balance'] = op_bal + ledger_df['Net'].cumsum()
                        ledger_df['Running Balance Display'] = ledger_df['Running Balance'].apply(
                            lambda x: f"{abs(x):.2f} Dr" if x >= 0 else f"{abs(x):.2f} Cr"
                        )

                        # Clean Final Display Table (Bina Kisi Page Header Repeat Ke)
                        v_no_col = [c for c in ledger_df.columns if 'vou' in c.lower() and 'no' in c.lower()][0]
                        final_view = pd.DataFrame({
                            "Voucher Date": ledger_df['V_Date'].dt.strftime('%d-%b-%Y'),
                            "Voucher No": ledger_df[v_no_col],
                            "Debit Amount": ledger_df['Debit Amount'],
                            "Credit Amount": ledger_df['Credit Amount'],
                            "Running Balance": ledger_df['Running Balance Display']
                        })

                        # Summary Metrics
                        st.markdown(f"**Account Description:** `{selected_acc}`")
                        st.markdown(f"**Account Opening:** `{abs(op_bal):.2f} {'Dr' if op_bal >= 0 else 'Cr'}`")
                        
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Total Debit", f"₹ {final_view['Debit Amount'].sum():,.2f}")
                        m2.metric("Total Credit", f"₹ {final_view['Credit Amount'].sum():,.2f}")
                        m3.metric("Closing Balance", final_view['Running Balance'].iloc[-1] if not final_view.empty else f"{op_bal:,.2f}")

                        st.dataframe(final_view, use_container_width=True, height=500)

                        # Single continuous Excel download
                        out = io.BytesIO()
                        with pd.ExcelWriter(out, engine='openpyxl') as wr:
                            final_view.to_excel(wr, index=False, sheet_name="Ledger")
                        st.download_button("📥 Download Ledger (Excel)", out.getvalue(), f"Ledger_{acc_selected_code}.xlsx")
                    else:
                        st.warning("VoucherDetail / VoucherHeader tables nahi mile.")

        # ==========================================================
        # 2. TRIAL BALANCE (TB)
        # ==========================================================
        elif report_type == "Trial Balance (TB)":
            st.subheader("⚖️ Trial Balance Report")

            colA, colB, colC = st.columns([1, 1, 1])
            with colA:
                tb_type = st.selectbox("Trial Balance Type", ["Merged Single", "Merged Splitted", "Separate"])
            with colB:
                tb_start = st.date_input("Start Date", datetime.date(2026, 4, 1), key="tb_s")
            with colC:
                tb_end = st.date_input("Last Date", datetime.date(2027, 4, 1), key="tb_e")

            if st.button("Generate Trial Balance", type="primary"):
                with st.spinner("Generating Trial Balance..."):
                    bal_data = read_table(tmp_path, "BalanceData") if "BalanceData" in tables else pd.DataFrame()
                    vd = read_table(tmp_path, "VoucherDetail") if "VoucherDetail" in tables else pd.DataFrame()
                    
                    if not bal_data.empty:
                        # Join with AccountMaster
                        bal_acc_col = [c for c in bal_data.columns if 'acc' in c.lower()][0]
                        acc_pk = acc_master.columns[0]
                        
                        tb_merged = pd.merge(bal_data, acc_master, left_on=bal_acc_col, right_on=acc_pk, how="left")
                        
                        b_dr = [c for c in bal_data.columns if 'dr' in c.lower() or 'debit' in c.lower()][0]
                        b_cr = [c for c in bal_data.columns if 'cr' in c.lower() or 'credit' in c.lower()][0]
                        
                        tb_merged['Opening Dr'] = pd.to_numeric(tb_merged[b_dr], errors='coerce').fillna(0.0)
                        tb_merged['Opening Cr'] = pd.to_numeric(tb_merged[b_cr], errors='coerce').fillna(0.0)

                        if tb_type == "Merged Single":
                            # 1 single row per Account Head
                            tb_summary = tb_merged.groupby(['Display_Acc']).agg({
                                'Opening Dr': 'sum',
                                'Opening Cr': 'sum'
                            }).reset_index()

                            # Closing Balances calculation
                            tb_summary['Closing Dr'] = tb_summary.apply(lambda r: max(0.0, r['Opening Dr'] - r['Opening Cr']), axis=1)
                            tb_summary['Closing Cr'] = tb_summary.apply(lambda r: max(0.0, r['Opening Cr'] - r['Opening Dr']), axis=1)

                            st.dataframe(tb_summary, use_container_width=True, height=600)
                            
                            # Excel Export
                            out_tb = io.BytesIO()
                            with pd.ExcelWriter(out_tb, engine='openpyxl') as wr:
                                tb_summary.to_excel(wr, index=False, sheet_name="Trial_Balance_Single")
                            st.download_button("📥 Download Merged Single TB (Excel)", out_tb.getvalue(), "TB_Merged_Single.xlsx")

                        elif tb_type == "Merged Splitted":
                            # Grouped by Account Head + Sub Location
                            loc_col = [c for c in bal_data.columns if 'loc' in c.lower()][0]
                            tb_split = tb_merged.groupby(['Display_Acc', loc_col]).agg({
                                'Opening Dr': 'sum',
                                'Opening Cr': 'sum'
                            }).reset_index()

                            st.dataframe(tb_split, use_container_width=True, height=600)
                            
                            out_tb2 = io.BytesIO()
                            with pd.ExcelWriter(out_tb2, engine='openpyxl') as wr:
                                tb_split.to_excel(wr, index=False, sheet_name="Trial_Balance_Splitted")
                            st.download_button("📥 Download Merged Splitted TB (Excel)", out_tb2.getvalue(), "TB_Merged_Splitted.xlsx")

                        elif tb_type == "Separate":
                            loc_col = [c for c in bal_data.columns if 'loc' in c.lower()][0]
                            locs = tb_merged[loc_col].dropna().unique().tolist()
                            sel_loc = st.selectbox("Select Location for Separate TB", locs)
                            
                            loc_tb = tb_merged[tb_merged[loc_col] == sel_loc].groupby(['Display_Acc']).agg({
                                'Opening Dr': 'sum',
                                'Opening Cr': 'sum'
                            }).reset_index()
                            
                            st.dataframe(loc_tb, use_container_width=True, height=600)

        # ==========================================================
        # 3. RAW TABLE BROWSER
        # ==========================================================
        elif report_type == "Raw Table Browser":
            st.subheader("🔍 Explore Tables in .mdb")
            target = st.selectbox("Select Table", tables)
            if target:
                df_t = read_table(tmp_path, target)
                st.write(f"Total Rows: {len(df_t)}")
                st.dataframe(df_t.head(200), use_container_width=True)

    except Exception as err:
        st.error(f"Execution Error: {err}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
