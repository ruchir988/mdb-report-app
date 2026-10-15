import streamlit as st
import pandas as pd
import numpy as np
import subprocess
import os
import io
import datetime
import traceback
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.set_page_config(page_title="VS-Power Accounting (AVVNL)", layout="wide", initial_sidebar_state="expanded")

# Persistent Directory for Uploaded Databases
UPLOAD_DIR = "uploaded_dbs"
os.makedirs(UPLOAD_DIR, exist_ok=True)

USER_CREDENTIALS = {
    "admin": "admin123",
    "ruchir": "avvnl@2026",
    "user": "user123"
}

# ==============================================================================
# HELPER FUNCTIONS & CACHED DATA LOADERS
# ==============================================================================
def get_tables(mdb_path):
    try:
        cmd = ["mdb-tables", "-1", mdb_path]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return [t.strip() for t in res.stdout.strip().split("\n") if t.strip()]
    except Exception as e:
        st.error(f"Error reading MDB tables: {e}")
        return []

@st.cache_data(show_spinner=False)
def load_mdb_table(mdb_path, table_name, file_mtime):
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

def generate_pdf_bytes(df, title_lines, col_widths=None, is_landscape=True):
    buf = io.BytesIO()
    pagesize = landscape(A4) if is_landscape else A4
    doc = SimpleDocTemplate(buf, pagesize=pagesize, leftMargin=15, rightMargin=15, topMargin=20, bottomMargin=20)
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('RepTitle', parent=styles['Heading2'], alignment=1, fontSize=11, spaceAfter=4)
    sub_style = ParagraphStyle('RepSub', parent=styles['Normal'], alignment=1, fontSize=9, spaceAfter=6)

    for idx, line in enumerate(title_lines):
        elements.append(Paragraph(line, title_style if idx == 0 else sub_style))
    elements.append(Spacer(1, 6))

    # Prepare table data (Single header at top, no repeat headers on page change)
    headers = list(df.columns)
    data = [headers]
    for row in df.itertuples(index=False):
        formatted_row = []
        for val in row:
            if isinstance(val, (float, np.floating)):
                formatted_row.append(f"{val:,.2f}")
            elif pd.isna(val):
                formatted_row.append("")
            else:
                formatted_row.append(str(val)[:42])
        data.append(formatted_row)

    t = Table(data, colWidths=col_widths, repeatRows=0)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1f5fbf")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7.5),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f6f8")]),
    ]))
    elements.append(t)
    doc.build(elements)
    return buf.getvalue()

# ==============================================================================
# AUTHENTICATION & SESSION MANAGEMENT
# ==============================================================================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""

if not st.session_state["logged_in"]:
    st.markdown("<h2 style='text-align: center;'>⚡ VS-Power Accounting (AVVNL) - Enterprise Web Suite</h2>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        with st.form("login_form"):
            st.subheader("🔐 User Login")
            uname = st.text_input("Username").strip().lower()
            upass = st.text_input("Password", type="password")
            submit_btn = st.form_submit_button("Login to Portal", use_container_width=True, type="primary")
            if submit_btn:
                if uname in USER_CREDENTIALS and USER_CREDENTIALS[uname] == upass:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = uname
                    st.rerun()
                else:
                    st.error("Invalid Username ya Password! (Try: admin / admin123 or ruchir / avvnl@2026)")
    st.stop()

username = st.session_state["username"]
user_mdb_path = os.path.join(UPLOAD_DIR, f"{username}_database.mdb")

# Sidebar Header
st.sidebar.markdown(f"### ⚡ VS-Power Accounting")
st.sidebar.markdown(f"👤 **User:** `{username.upper()}`")
if st.sidebar.button("🚪 Logout", use_container_width=True):
    st.session_state["logged_in"] = False
    st.session_state["username"] = ""
    st.rerun()

st.sidebar.markdown("---")

# ==============================================================================
# DATABASE UPLOAD & PERSISTENCE
# ==============================================================================
if not os.path.exists(user_mdb_path):
    st.info("👋 Pehli baar setup karne ke liye apna `.mdb` (AVVNL Accounting Database) upload karein. Ye server par save rahega.")
    up_file = st.file_uploader("Upload MS Access (.mdb) Database", type=["mdb"])
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
                status_text.text(f"Uploading & Saving Database: {percent}% ({bytes_written // (1024*1024)} MB / {file_size // (1024*1024)} MB)")
        st.success("Database successfully save ho gaya!")
        st.rerun()
    st.stop()

with st.sidebar.expander("⚙️ Database Management", expanded=False):
    db_size_mb = os.path.getsize(user_mdb_path) / (1024 * 1024)
    st.caption(f"Status: **Active** ({db_size_mb:.1f} MB)")
    if st.button("🔄 Change / Upload New .mdb", use_container_width=True):
        if os.path.exists(user_mdb_path):
            os.remove(user_mdb_path)
        st.cache_data.clear()
        st.rerun()

# ==============================================================================
# CORE DATA ENGINE (LOAD & MAP VIA MISCMASTER)
# ==============================================================================
try:
    file_mtime = os.path.getmtime(user_mdb_path)
    tables = get_tables(user_mdb_path)
    if not tables or "MiscMaster" not in tables:
        st.error("Invalid Database: `MiscMaster` table nahi mili.")
        st.stop()

    with st.spinner("Loading Master & Transaction Engine into Memory..."):
        misc_df = load_mdb_table(user_mdb_path, "MiscMaster", file_mtime)
        vh = load_mdb_table(user_mdb_path, "VoucherHeader", file_mtime)
        vd = load_mdb_table(user_mdb_path, "VoucherDetail", file_mtime)
        books_df = load_mdb_table(user_mdb_path, "AccountBook", file_mtime) if "AccountBook" in tables else pd.DataFrame()
        ac_grp_df = load_mdb_table(user_mdb_path, "AccountGroup", file_mtime) if "AccountGroup" in tables else pd.DataFrame()

        # Identify Exact Columns in MiscMaster
        m_id = find_col(misc_df, ["Misc_IdNo", "MiscIdNo", "IdNo"])
        m_code = find_col(misc_df, ["Misc_Code", "MiscCode", "Code"])
        m_desc = find_col(misc_df, ["Misc_Desc", "Misc_Name", "Desc", "Name"])
        m_type = find_col(misc_df, ["Misc_Type", "Misc_Type_Id", "Type"])
        m_rem4 = find_col(misc_df, ["Misc_Remarks4", "Remarks4"])

        misc_df[m_id] = pd.to_numeric(misc_df[m_id], errors='coerce')
        misc_df['Clean_Code'] = misc_df[m_code].fillna('').astype(str).str.strip()
        misc_df['Clean_Desc'] = misc_df[m_desc].fillna('').astype(str).str.strip()
        # Ensure we don't duplicate code if Misc_Desc already starts with Misc_Code
        def make_label(row):
            c = row['Clean_Code']
            d = row['Clean_Desc']
            if d.startswith(c):
                return d
            return f"{c}-{d}" if c else d

        misc_df['Full_Label'] = misc_df.apply(make_label, axis=1)

        id_to_label = dict(zip(misc_df[m_id], misc_df['Full_Label']))
        id_to_code = dict(zip(misc_df[m_id], misc_df['Clean_Code']))
        label_to_id = dict(zip(misc_df['Full_Label'], misc_df[m_id]))

        # Identify Exact Columns in VoucherHeader (H) & VoucherDetail (D)
        vh_id = find_col(vh, ["Voucher_IDNO", "Voucher_IdNo", "VH_IdNo"])
        vh_loc = find_col(vh, ["Voucher_LocationId", "VH_LocationIdNo", "LocationId"])
        vh_no = find_col(vh, ["Voucher_Number", "Voucher_No", "VH_VoucherNo"])
        vh_date = find_col(vh, ["Voucher_Date", "VH_VoucherDate", "Date"])
        vh_book = find_col(vh, ["Voucher_BookId", "BookId"])
        vh_ref_no = find_col(vh, ["Voucher_ReferenceNo", "RefNo"])
        vh_ref_date = find_col(vh, ["Voucher_ReferenceDate", "RefDate"])
        vh_narr = find_col(vh, ["Voucher_Narration", "Narration"])

        vd_id = find_col(vd, ["VouDtl_IdNo", "VD_IdNo"])
        vd_vou_id = find_col(vd, ["VouDtl_VouId", "VD_VHIdNo", "VouId"])
        vd_sr = find_col(vd, ["VouDtl_SerialNo", "Sr_No", "SerialNo"])
        vd_acc_id = find_col(vd, ["VouDtl_AccountId", "VD_AccountIdNo", "AccountId"])
        vd_sub_id = find_col(vd, ["VouDtl_SubLedgerId", "SubLedgerId"])
        vd_ana_id = find_col(vd, ["VouDtl_AnalysisId", "AnalysisId"])
        vd_drcr = find_col(vd, ["VouDtl_DrCrId", "DrCrId"])
        vd_amt = find_col(vd, ["VouDtl_Amount", "Amount"])
        vd_for_loc = find_col(vd, ["VouDtl_ForLocationId", "ForLocationId"])
        vd_narr = find_col(vd, ["VouDtl_Narration", "Narration"])

        # Convert types cleanly
        vh[vh_id] = pd.to_numeric(vh[vh_id], errors='coerce')
        vh[vh_loc] = pd.to_numeric(vh[vh_loc], errors='coerce')
        vh['Parsed_Date'] = pd.to_datetime(vh[vh_date], errors='coerce').dt.date

        vd[vd_vou_id] = pd.to_numeric(vd[vd_vou_id], errors='coerce')
        vd[vd_acc_id] = pd.to_numeric(vd[vd_acc_id], errors='coerce')
        vd[vd_drcr] = pd.to_numeric(vd[vd_drcr], errors='coerce')
        vd[vd_amt] = pd.to_numeric(vd[vd_amt], errors='coerce').fillna(0.0)

        # Pre-calculate Dr & Cr columns on VoucherDetail (101 = Debit, 102 = Credit)
        vd['Dr_Amt'] = np.where(vd[vd_drcr] == 101, vd[vd_amt], 0.0)
        vd['Cr_Amt'] = np.where(vd[vd_drcr] == 102, vd[vd_amt], 0.0)

        # Merge H and D once in memory for lightning-fast reports
        full_tx = pd.merge(
            vd,
            vh[[vh_id, vh_loc, vh_no, 'Parsed_Date', vh_book, vh_ref_no, vh_ref_date, vh_narr]],
            left_on=vd_vou_id,
            right_on=vh_id,
             how='inner'
        )
        full_tx['Account_Label'] = full_tx[vd_acc_id].map(id_to_label).fillna(full_tx[vd_acc_id].astype(str))
        full_tx['Account_Code_Raw'] = full_tx[vd_acc_id].map(id_to_code).fillna('')
        full_tx['Group_Code'] = full_tx['Account_Code_Raw'].str.slice(0, 2)
        full_tx['Location_Label'] = full_tx[vh_loc].map(id_to_label).fillna(full_tx[vh_loc].astype(str))

        # Active Accounts & Locations Lists
        active_acc_labels = sorted(full_tx['Account_Label'].dropna().unique().tolist())
        active_loc_labels = sorted(full_tx['Location_Label'].dropna().unique().tolist())

        # Location Hierarchy (Parent Circle to Child Divisions via Misc_Remarks4)
        parent_map = {}
        if m_rem4 in misc_df.columns:
            loc_rows = misc_df[misc_df[m_id].isin(full_tx[vh_loc].unique())].copy()
            for _, r in loc_rows.iterrows():
                rem4_val = str(r[m_rem4]).strip() if pd.notna(r[m_rem4]) else ""
                if rem4_val and rem4_val != "nan":
                    p_id = pd.to_numeric(rem4_val, errors='coerce')
                    p_label = id_to_label.get(p_id, f"Parent-{rem4_val}")
                    parent_map.setdefault(p_label, []).append(r['Full_Label'])

    # ==============================================================================
    # SIDEBAR NAVIGATION TREE (AS PER VSPA BLUEPRINT)
    # ==============================================================================
    nav_module = st.sidebar.radio(
        "📂 Navigation Menu",
        [
            "🏠 Dashboard & System Info",
            "⚖️ Trial Balance (TB Engine)",
            "📖 Account General Ledger",
            "📚 Day Books & Register",
            "👥 Sub-Ledger & Scheme Reports",
            "📊 Analytical & Group Summaries",
            "🧾 Voucher Explorer & Search",
            "🗂️ Masters & Chart of Accounts"
        ]
    )

    # Default FY Dates detected from DB
    min_db_date = full_tx['Parsed_Date'].dropna().min()
    max_db_date = full_tx['Parsed_Date'].dropna().max()
    default_fy_start = datetime.date(2026, 4, 1)
    default_fy_end = max_db_date if pd.notna(max_db_date) and max_db_date >= default_fy_start else datetime.date(2027, 3, 31)

    # ==============================================================================
    # MODULE 1: DASHBOARD & SYSTEM OVERVIEW
    # ==============================================================================
    if nav_module == "🏠 Dashboard & System Info":
        st.title("⚡ VS-Power Accounting (AVVNL) - System Dashboard")
        st.markdown("Commercial Accounting System (CAS) - Nagaur Circle / Division Consolidation")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Vouchers (Headers)", f"{len(vh):,}")
        k2.metric("Total Voucher Lines", f"{len(full_tx):,}")
        k3.metric("Active Account Heads", f"{len(active_acc_labels):,}")
        k4.metric("Active Locations / Units", f"{len(active_loc_labels):,}")

        st.markdown("---")
        c_left, c_right = st.columns(2)
        with c_left:
            st.subheader("📍 Active Accounting Locations in Database")
            loc_summary = full_tx.groupby('Location_Label').agg(
                Vouchers=(vh_id, 'nunique'),
                Total_Debit=('Dr_Amt', 'sum'),
                Total_Credit=('Cr_Amt', 'sum')
            ).reset_index()
            st.dataframe(loc_summary, use_container_width=True, height=350)

        with c_right:
            st.subheader("📘 Account Books Configured")
            if not books_df.empty:
                st.dataframe(books_df, use_container_width=True, height=350)
            else:
                st.info("AccountBook table not found.")

    # ==============================================================================
    # MODULE 2: TRIAL BALANCE ENGINE (EXACT VSPA_GenTBCSV & TXT REPORT LOGIC)
    # ==============================================================================
    elif nav_module == "⚖️ Trial Balance (TB Engine)":
        st.title("⚖️ Account Trial Balance")

        with st.container():
            r1c1, r1c2, r1c3, r1c4 = st.columns([1.5, 1.2, 1, 1])
            with r1c1:
                tb_mode = st.selectbox(
                    "Trial Balance Type",
                    [
                        "Merged Single (12-Col CSV/Excel Format)",
                        "Separate (Location-wise 12-Col Format)",
                        "Merged Splitted (Account -> Location Breakdown)"
                    ]
                )
            with r1c2:
                fy_start_date = st.date_input("FY Opening Cutoff Date", datetime.date(2026, 4, 1))
            with r1c3:
                tb_start_date = st.date_input("Start Date", datetime.date(2026, 4, 1))
            with r1c4:
                tb_last_date = st.date_input("Last Date", default_fy_end)

            r2c1, r2c2 = st.columns([2, 2])
            with r2c1:
                sel_locations = st.multiselect(
                    "Child Locations (Select All or Specific Units)",
                    options=active_loc_labels,
                    default=active_loc_labels
                )
            with r2c2:
                include_group_totals = st.checkbox("Include 2-Digit CAS Group Totals (Group 10, 12, 14, 23...)", value=True)

        if st.button("🚀 Generate Trial Balance", type="primary"):
            if not sel_locations:
                st.warning("Kripya kam se kam ek Child Location select karein!")
                st.stop()

            with st.spinner("Executing Trial Balance Engine..."):
                df_sub = full_tx[full_tx['Location_Label'].isin(sel_locations)].copy()

                # Slice 1: Year Opening (Voucher_Date < fy_start_date)
                df_sub['Raw_Open_Dr'] = np.where(df_sub['Parsed_Date'] < fy_start_date, df_sub['Dr_Amt'], 0.0)
                df_sub['Raw_Open_Cr'] = np.where(df_sub['Parsed_Date'] < fy_start_date, df_sub['Cr_Amt'], 0.0)

                # Slice 2: Prev Trn / Transaction Upto Period (fy_start_date <= Voucher_Date < tb_start_date)
                df_sub['Prev_Trn_Dr'] = np.where(
                    (df_sub['Parsed_Date'] >= fy_start_date) & (df_sub['Parsed_Date'] < tb_start_date),
                    df_sub['Dr_Amt'], 0.0
                )
                df_sub['Prev_Trn_Cr'] = np.where(
                    (df_sub['Parsed_Date'] >= fy_start_date) & (df_sub['Parsed_Date'] < tb_start_date),
                    df_sub['Cr_Amt'], 0.0
                )

                # Slice 3: Curr Trn / Transaction for the Period (tb_start_date <= Voucher_Date <= tb_last_date)
                df_sub['Curr_Trn_Dr'] = np.where(
                    (df_sub['Parsed_Date'] >= tb_start_date) & (df_sub['Parsed_Date'] <= tb_last_date),
                    df_sub['Dr_Amt'], 0.0
                )
                df_sub['Curr_Trn_Cr'] = np.where(
                    (df_sub['Parsed_Date'] >= tb_start_date) & (df_sub['Parsed_Date'] <= tb_last_date),
                    df_sub['Cr_Amt'], 0.0
                )

                # First aggregate at (Location, Account) level so each location's opening & closing is netted properly
                loc_acc_grp = df_sub.groupby(['Location_Label', 'Account_Label', 'Group_Code'], as_index=False).agg({
                    'Raw_Open_Dr': 'sum',
                    'Raw_Open_Cr': 'sum',
                    'Prev_Trn_Dr': 'sum',
                    'Prev_Trn_Cr': 'sum',
                    'Curr_Trn_Dr': 'sum',
                    'Curr_Trn_Cr': 'sum'
                })

                # Net Opening per Location+Account
                open_net = loc_acc_grp['Raw_Open_Dr'] - loc_acc_grp['Raw_Open_Cr']
                loc_acc_grp['Opening Dr'] = np.where(open_net > 0, open_net, 0.0)
                loc_acc_grp['Opening Cr'] = np.where(open_net < 0, -open_net, 0.0)

                # Net Prev Trn per Location+Account
                prev_net = loc_acc_grp['Prev_Trn_Dr'] - loc_acc_grp['Prev_Trn_Cr']
                loc_acc_grp['Prev Trn Dr'] = loc_acc_grp['Prev_Trn_Dr']
                loc_acc_grp['Prev Trn Cr'] = loc_acc_grp['Prev_Trn_Cr']

                loc_acc_grp['Curr Trn Dr'] = loc_acc_grp['Curr_Trn_Dr']
                loc_acc_grp['Curr Trn Cr'] = loc_acc_grp['Curr_Trn_Cr']

                # Net Closing per Location+Account
                close_net = (loc_acc_grp['Opening Dr'] - loc_acc_grp['Opening Cr']) + prev_net + (loc_acc_grp['Curr Trn Dr'] - loc_acc_grp['Curr Trn Cr'])
                loc_acc_grp['Closing Dr'] = np.where(close_net > 0, close_net, 0.0)
                loc_acc_grp['Closing Cr'] = np.where(close_net < 0, -close_net, 0.0)

                # Progressive Totals (FY transactions upto Last Date)
                loc_acc_grp['Prog Dr'] = loc_acc_grp['Prev Trn Dr'] + loc_acc_grp['Curr Trn Dr']
                loc_acc_grp['Prog Cr'] = loc_acc_grp['Prev Trn Cr'] + loc_acc_grp['Curr Trn Cr']

                num_cols = [
                    'Opening Dr', 'Opening Cr',
                    'Prev Trn Dr', 'Prev Trn Cr',
                    'Curr Trn Dr', 'Curr Trn Cr',
                    'Closing Dr', 'Closing Cr',
                    'Prog Dr', 'Prog Cr'
                ]

                # Filter out rows where all 10 numeric columns are 0
                active_mask = (loc_acc_grp[num_cols].abs().sum(axis=1) > 0.001)
                loc_acc_grp = loc_acc_grp[active_mask].copy()

                # --------------------------------------------------------------
                # MODE 1: MERGED SINGLE (1 Row per Account Code, Netted across selected locations)
                # --------------------------------------------------------------
                if tb_mode.startswith("Merged Single"):
                    acc_grp = loc_acc_grp.groupby(['Account_Label', 'Group_Code'], as_index=False)[num_cols].sum()
                    
                    # In Merged Single TB (like TB Merged Single.Txt), Opening Dr/Cr and Closing Dr/Cr are netted at Account level!
                    m_open_net = acc_grp['Opening Dr'] - acc_grp['Opening Cr']
                    acc_grp['Opening Dr'] = np.where(m_open_net > 0, m_open_net, 0.0)
                    acc_grp['Opening Cr'] = np.where(m_open_net < 0, -m_open_net, 0.0)

                    m_close_net = (acc_grp['Opening Dr'] - acc_grp['Opening Cr']) + (acc_grp['Prev Trn Dr'] - acc_grp['Prev Trn Cr']) + (acc_grp['Curr Trn Dr'] - acc_grp['Curr Trn Cr'])
                    acc_grp['Closing Dr'] = np.where(m_close_net > 0, m_close_net, 0.0)
                    acc_grp['Closing Cr'] = np.where(m_close_net < 0, -m_close_net, 0.0)

                    acc_grp = acc_grp[acc_grp[num_cols].abs().sum(axis=1) > 0.001].sort_values('Account_Label')
                    acc_grp['Location'] = "14-Nagaur (Merged)" if len(sel_locations) > 1 else sel_locations[0]
                    acc_grp.rename(columns={'Account_Label': 'Account Code'}, inplace=True)

                    final_rows = []
                    for grp_code, grp_df in acc_grp.groupby('Group_Code', sort=True):
                        for _, r in grp_df.iterrows():
                            final_rows.append(r[['Location', 'Account Code'] + num_cols].to_dict())
                        if include_group_totals:
                            g_sum = grp_df[num_cols].sum()
                            g_row = {'Location': '', 'Account Code': f"--- Group {grp_code} Total ---"}
                            g_row.update(g_sum.to_dict())
                            final_rows.append(g_row)

                    # Grand Total Row
                    gt_sum = acc_grp[num_cols].sum()
                    gt_row = {'Location': '', 'Account Code': '=== GRAND TOTAL ==='}
                    gt_row.update(gt_sum.to_dict())
                    final_rows.append(gt_row)

                    out_df = pd.DataFrame(final_rows)

                # --------------------------------------------------------------
                # MODE 2: SEPARATE (Sorted by Location -> Account Code)
                # --------------------------------------------------------------
                elif tb_mode.startswith("Separate"):
                    loc_acc_grp = loc_acc_grp.sort_values(['Location_Label', 'Account_Label'])
                    loc_acc_grp.rename(columns={'Location_Label': 'Location', 'Account_Label': 'Account Code'}, inplace=True)

                    final_rows = []
                    for loc_name, l_df in loc_acc_grp.groupby('Location', sort=True):
                        for grp_code, grp_df in l_df.groupby('Group_Code', sort=True):
                            for _, r in grp_df.iterrows():
                                final_rows.append(r[['Location', 'Account Code'] + num_cols].to_dict())
                            if include_group_totals:
                                g_sum = grp_df[num_cols].sum()
                                g_row = {'Location': loc_name, 'Account Code': f"--- Group {grp_code} Total ---"}
                                g_row.update(g_sum.to_dict())
                                final_rows.append(g_row)
                        l_sum = l_df[num_cols].sum()
                        l_row = {'Location': loc_name, 'Account Code': f"=== {loc_name} GRAND TOTAL ==="}
                        l_row.update(l_sum.to_dict())
                        final_rows.append(l_row)

                    out_df = pd.DataFrame(final_rows)

                # --------------------------------------------------------------
                # MODE 3: MERGED SPLITTED (Sorted by Account Code -> Location Breakdown)
                # --------------------------------------------------------------
                else:
                    loc_acc_grp = loc_acc_grp.sort_values(['Account_Label', 'Location_Label'])
                    loc_acc_grp.rename(columns={'Location_Label': 'Location', 'Account_Label': 'Account Code'}, inplace=True)

                    final_rows = []
                    for grp_code, grp_df in loc_acc_grp.groupby('Group_Code', sort=True):
                        for acc_name, a_df in grp_df.groupby('Account Code', sort=True):
                            for _, r in a_df.iterrows():
                                final_rows.append(r[['Location', 'Account Code'] + num_cols].to_dict())
                            a_sum = a_df[num_cols].sum()
                            a_row = {'Location': 'Account Total:', 'Account Code': acc_name}
                            a_row.update(a_sum.to_dict())
                            final_rows.append(a_row)
                        if include_group_totals:
                            g_sum = grp_df[num_cols].sum()
                            g_row = {'Location': 'Group Total:', 'Account Code': f"--- Group {grp_code} Total ---"}
                            g_row.update(g_sum.to_dict())
                            final_rows.append(g_row)

                    gt_sum = loc_acc_grp[num_cols].sum()
                    gt_row = {'Location': 'ALL LOCATIONS', 'Account Code': '=== GRAND TOTAL ==='}
                    gt_row.update(gt_sum.to_dict())
                    final_rows.append(gt_row)

                    out_df = pd.DataFrame(final_rows)

                # Display Summary Metrics
                raw_only = loc_acc_grp
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Opening Dr Total", f"₹ {raw_only['Opening Dr'].sum():,.2f}")
                m2.metric("Opening Cr Total", f"₹ {raw_only['Opening Cr'].sum():,.2f}")
                m3.metric("Period Dr Trans", f"₹ {raw_only['Curr Trn Dr'].sum():,.2f}")
                m4.metric("Period Cr Trans", f"₹ {raw_only['Curr Trn Cr'].sum():,.2f}")

                st.dataframe(out_df, use_container_width=True, height=580)

                # Download Buttons (CSV, Excel, PDF)
                dl1, dl2, dl3 = st.columns(3)
                with dl1:
                    csv_bytes = out_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "📥 Download 12-Col TB (.CSV)",
                        data=csv_bytes,
                        file_name=f"TB_{tb_mode[:10]}_{tb_start_date}_to_{tb_last_date}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                with dl2:
                    excel_buf = io.BytesIO()
                    with pd.ExcelWriter(excel_buf, engine='openpyxl') as wr:
                        out_df.to_excel(wr, index=False, sheet_name="Trial_Balance")
                    st.download_button(
                        "📥 Download Formatted TB (.XLSX)",
                        data=excel_buf.getvalue(),
                        file_name=f"TB_{tb_mode[:10]}_{tb_start_date}_to_{tb_last_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                with dl3:
                    pdf_bytes = generate_pdf_bytes(
                        out_df,
                        [
                            "Ajmer Vidyut Vitran Nigam Limited",
                            f"Account Trial Balance ({tb_mode.split('(')[0].strip()}) - From {tb_start_date.strftime('%d %b %Y')} To {tb_last_date.strftime('%d %b %Y')}"
                        ],
                        is_landscape=True
                    )
                    st.download_button(
                        "📥 Download Clean Continuous PDF",
                        data=pdf_bytes,
                        file_name=f"TB_{tb_mode[:10]}_{tb_start_date}_to_{tb_last_date}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

    # ==============================================================================
    # MODULE 3: ACCOUNT GENERAL LEDGER (CONTINUOUS, NO PAGE BREAK HEADERS)
    # ==============================================================================
    elif nav_module == "📖 Account General Ledger":
        st.title("📖 Account General Ledger")

        c1, c2, c3, c4 = st.columns([2.2, 1.8, 1, 1])
        with c1:
            sel_acc = st.selectbox("Select Ledger Account", active_acc_labels)
        with c2:
            sel_led_locs = st.multiselect("Select Locations", active_loc_labels, default=active_loc_labels)
        with c3:
            led_start = st.date_input("Start Date", datetime.date(2026, 4, 1))
        with c4:
            led_end = st.date_input("Last Date", datetime.date(2026, 10, 14))

        if st.button("📖 Generate General Ledger", type="primary"):
            with st.spinner("Generating Continuous Ledger..."):
                acc_tx = full_tx[
                    (full_tx['Account_Label'] == sel_acc) &
                    (full_tx['Location_Label'].isin(sel_led_locs))
                ].copy()

                # Opening Balance = All vouchers strictly before led_start
                open_tx = acc_tx[acc_tx['Parsed_Date'] < led_start]
                op_bal = float(open_tx['Dr_Amt'].sum() - open_tx['Cr_Amt'].sum())
                op_str = f"{abs(op_bal):,.2f}-{'Dr' if op_bal >= 0 else 'Cr'}"

                # Period Vouchers (led_start <= Parsed_Date <= led_end)
                period_tx = acc_tx[
                    (acc_tx['Parsed_Date'] >= led_start) &
                    (acc_tx['Parsed_Date'] <= led_end)
                ].copy()

                # Sort chronologically by Voucher_Date, then Voucher_No, then VouDtl_IdNo
                period_tx = period_tx.sort_values(by=['Parsed_Date', vh_no, vd_id])

                period_tx['Net_Change'] = period_tx['Dr_Amt'] - period_tx['Cr_Amt']
                period_tx['Run_Bal_Val'] = op_bal + period_tx['Net_Change'].cumsum()
                period_tx['Running Balance'] = period_tx['Run_Bal_Val'].apply(
                    lambda v: f"{abs(v):.2f}{'Dr' if v >= 0 else 'Cr'}"
                )

                led_view = pd.DataFrame({
                    "Voucher Date": pd.to_datetime(period_tx['Parsed_Date']).dt.strftime('%d-%b-%Y'),
                    "Voucher No.": period_tx[vh_no].fillna(''),
                    "Supp.VouNo": period_tx[vh_ref_no].fillna('') if vh_ref_no in period_tx.columns else '',
                    "Supp.VouDate": pd.to_datetime(period_tx[vh_ref_date], errors='coerce').dt.strftime('%d-%b-%Y').fillna('') if vh_ref_date in period_tx.columns else '',
                    "Debit Amount": period_tx['Dr_Amt'],
                    "Credit Amount": period_tx['Cr_Amt'],
                    "Location Name": period_tx['Location_Label'],
                    "Running Balance": period_tx['Running Balance'],
                    "Narration": period_tx[vd_narr].fillna(period_tx[vh_narr].fillna(''))
                })

                tot_dr = led_view['Debit Amount'].sum()
                tot_cr = led_view['Credit Amount'].sum()
                close_val = op_bal + tot_dr - tot_cr
                close_str = f"{abs(close_val):,.2f} {'Dr' if close_val >= 0 else 'Cr'}"

                st.markdown("---")
                st.markdown(f"**Account Desc. :** `{sel_acc}` | **Account Opening :** `{op_str}`")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Opening Balance", op_str)
                m2.metric("Period Debit Total", f"₹ {tot_dr:,.2f}")
                m3.metric("Period Credit Total", f"₹ {tot_cr:,.2f}")
                m4.metric("Closing Balance", close_str)

                st.dataframe(led_view, use_container_width=True, height=520)

                d1, d2 = st.columns(2)
                with d1:
                    xl_buf = io.BytesIO()
                    with pd.ExcelWriter(xl_buf, engine='openpyxl') as wr:
                        led_view.to_excel(wr, index=False, sheet_name="General_Ledger")
                    st.download_button(
                        "📥 Download Continuous Ledger (.XLSX)",
                        data=xl_buf.getvalue(),
                        file_name=f"Ledger_{sel_acc[:15]}_{led_start}_to_{led_end}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                with d2:
                    pdf_led = generate_pdf_bytes(
                        led_view.drop(columns=['Narration']),
                        [
                            "Ajmer Vidyut Vitran Nigam Limited - Account General Ledger",
                            f"Account: {sel_acc} | Opening: {op_str} | Period: {led_start.strftime('%d-%b-%Y')} to {led_end.strftime('%d-%b-%Y')} | Closing: {close_str}"
                        ],
                        is_landscape=True
                    )
                    st.download_button(
                        "📥 Download Continuous Ledger (.PDF)",
                        data=pdf_led,
                        file_name=f"Ledger_{sel_acc[:15]}_{led_start}_to_{led_end}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

    # ==============================================================================
    # MODULE 4: DAY BOOKS & REGISTER (ALL 12+ BOOKS)
    # ==============================================================================
    elif nav_module == "📚 Day Books & Register":
        st.title("📚 Multi-Book Day Book Register")

        if not books_df.empty:
            b_id_col = find_col(books_df, ["Book_IdNo", "IdNo"])
            b_code_col = find_col(books_df, ["Book_Code", "Code"])
            b_name_col = find_col(books_df, ["Book_Name", "Name"])
            books_df['Book_Display'] = books_df[b_code_col].astype(str).str.strip() + " - " + books_df[b_name_col].astype(str).str.strip()
            book_map = dict(zip(books_df['Book_Display'], pd.to_numeric(books_df[b_id_col], errors='coerce')))
            id_to_book = dict(zip(pd.to_numeric(books_df[b_id_col], errors='coerce'), books_df['Book_Display']))
            book_options = ["All Books"] + sorted(list(book_map.keys()))
        else:
            book_options = ["All Books"]
            id_to_book = {}

        c1, c2, c3, c4 = st.columns([1.8, 1.8, 1, 1])
        with c1:
            sel_book = st.selectbox("Select Account Book", book_options)
        with c2:
            sel_db_loc = st.selectbox("Select Location", ["All Locations"] + active_loc_labels)
        with c3:
            db_start = st.date_input("From Date", datetime.date(2026, 4, 1))
        with c4:
            db_end = st.date_input("To Date", datetime.date(2026, 10, 14))

        if st.button("📘 View Day Book Transactions", type="primary"):
            db_tx = full_tx[
                (full_tx['Parsed_Date'] >= db_start) &
                (full_tx['Parsed_Date'] <= db_end)
            ].copy()

            if sel_book != "All Books":
                b_id_val = book_map[sel_book]
                db_tx = db_tx[pd.to_numeric(db_tx[vh_book], errors='coerce') == b_id_val]

            if sel_db_loc != "All Locations":
                db_tx = db_tx[db_tx['Location_Label'] == sel_db_loc]

            db_tx['Book Name'] = pd.to_numeric(db_tx[vh_book], errors='coerce').map(id_to_book).fillna(db_tx[vh_book].astype(str))
            db_tx = db_tx.sort_values(by=['Parsed_Date', vh_no, vd_sr])

            daybook_view = pd.DataFrame({
                "Date": pd.to_datetime(db_tx['Parsed_Date']).dt.strftime('%d-%b-%Y'),
                "Voucher No": db_tx[vh_no],
                "Book": db_tx['Book Name'],
                "Location": db_tx['Location_Label'],
                "Account Head": db_tx['Account_Label'],
                "Debit": db_tx['Dr_Amt'],
                "Credit": db_tx['Cr_Amt'],
                "Narration": db_tx[vd_narr].fillna(db_tx[vh_narr].fillna(''))
            })

            st.metric("Total Day Book Entries", f"{len(daybook_view):,} lines (Dr: ₹ {daybook_view['Debit'].sum():,.2f} | Cr: ₹ {daybook_view['Credit'].sum():,.2f})")
            st.dataframe(daybook_view, use_container_width=True, height=550)

            xl_db = io.BytesIO()
            with pd.ExcelWriter(xl_db, engine='openpyxl') as wr:
                daybook_view.to_excel(wr, index=False, sheet_name="DayBook")
            st.download_button("📥 Download Day Book (.XLSX)", xl_db.getvalue(), "DayBook_Report.xlsx")

    # ==============================================================================
    # MODULE 5: SUB-LEDGER & SCHEME (ANALYSIS) REPORTS
    # ==============================================================================
    elif nav_module == "👥 Sub-Ledger & Scheme Reports":
        st.title("👥 Sub-Ledger, Scheme (Analysis) & Inter-Unit Reports")

        dim_type = st.radio(
            "Select Dimension Report",
            ["Sub-Ledger Report (Suppliers/Contractors/Staff)", "Analysis / Scheme Report (RDSS, APDRP, World Bank)", "Inter-Unit Reconciliation (Groups 30-37)"],
            horizontal=True
        )

        if dim_type.startswith("Sub-Ledger"):
            full_tx['SubLedger_Name'] = pd.to_numeric(full_tx[vd_sub_id], errors='coerce').map(id_to_label).fillna('None')
            sub_tx = full_tx[pd.to_numeric(full_tx[vd_sub_id], errors='coerce') > 0].copy()
            if sub_tx.empty:
                st.info("Is database me kisi voucher me Sub-Ledger ID attached nahi hai.")
            else:
                sub_grp = sub_tx.groupby(['SubLedger_Name', 'Account_Label'], as_index=False).agg(
                    Total_Debit=('Dr_Amt', 'sum'),
                    Total_Credit=('Cr_Amt', 'sum')
                )
                sub_grp['Net Balance'] = sub_grp['Total_Debit'] - sub_grp['Total_Credit']
                st.dataframe(sub_grp, use_container_width=True, height=550)

        elif dim_type.startswith("Analysis"):
            full_tx['Analysis_Name'] = pd.to_numeric(full_tx[vd_ana_id], errors='coerce').map(id_to_label).fillna('None')
            ana_tx = full_tx[pd.to_numeric(full_tx[vd_ana_id], errors='coerce') > 0].copy()
            if ana_tx.empty:
                st.info("Is database me Analysis / Scheme ID ke entries nahi hain.")
            else:
                ana_grp = ana_tx.groupby(['Analysis_Name', 'Account_Label', 'Location_Label'], as_index=False).agg(
                    Total_Debit=('Dr_Amt', 'sum'),
                    Total_Credit=('Cr_Amt', 'sum')
                )
                st.dataframe(ana_grp, use_container_width=True, height=550)

        else:
            iu_tx = full_tx[full_tx['Group_Code'].isin(['30', '31', '32', '33', '34', '36', '37', '38'])].copy()
            iu_tx['Target_Unit'] = pd.to_numeric(iu_tx[vd_for_loc], errors='coerce').map(id_to_label).fillna('Unspecified')
            iu_grp = iu_tx.groupby(['Account_Label', 'Location_Label', 'Target_Unit'], as_index=False).agg(
                Debit=('Dr_Amt', 'sum'),
                Credit=('Cr_Amt', 'sum')
            )
            iu_grp['Net IU Balance'] = iu_grp['Debit'] - iu_grp['Credit']
            st.dataframe(iu_grp, use_container_width=True, height=550)

    # ==============================================================================
    # MODULE 6: ANALYTICAL & GROUP SUMMARIES (GTB, LOCATION SUMMARY)
    # ==============================================================================
    elif nav_module == "📊 Analytical & Group Summaries":
        st.title("📊 Group Trial Balance (GTB) & Analytical Summaries")

        t1, t2 = st.tabs(["Group Trial Balance (2-Digit CAS Groups)", "Location-Wise Month Matrix"])

        with t1:
            gtb = full_tx.groupby('Group_Code', as_index=False).agg(
                Total_Debit=('Dr_Amt', 'sum'),
                Total_Credit=('Cr_Amt', 'sum'),
                Voucher_Lines=(vd_id, 'count')
            )
            if not ac_grp_df.empty:
                g_code_col = find_col(ac_grp_df, ["AcGrp_Code", "Code"])
                g_name_col = find_col(ac_grp_df, ["AcGrp_Name", "Name"])
                ac_grp_df['GCode'] = ac_grp_df[g_code_col].astype(str).str.strip()
                g_map = dict(zip(ac_grp_df['GCode'], ac_grp_df[g_name_col]))
                gtb['Group Description'] = gtb['Group_Code'].map(g_map).fillna('Other Group')
            gtb['Net Balance'] = gtb['Total_Debit'] - gtb['Total_Credit']
            st.dataframe(gtb, use_container_width=True, height=520)

        with t2:
            curr_fy = full_tx[full_tx['Parsed_Date'] >= datetime.date(2026, 4, 1)].copy()
            curr_fy['Year_Month'] = pd.to_datetime(curr_fy['Parsed_Date']).dt.strftime('%Y-%m (%b)')
            piv = curr_fy.pivot_table(
                index='Location_Label',
                columns='Year_Month',
                values='Dr_Amt',
                aggfunc='sum',
                fill_value=0.0
            )
            st.subheader("Month-wise Debit Volume by Location (FY 2026-27)")
            st.dataframe(piv.style.format("{:,.2f}"), use_container_width=True, height=500)

    # ==============================================================================
    # MODULE 7: VOUCHER EXPLORER & DOUBLE-ENTRY INSPECTOR
    # ==============================================================================
    elif nav_module == "🧾 Voucher Explorer & Search":
        st.title("🧾 Unified Voucher Search & Inspector")

        s1, s2 = st.columns([2, 2])
        with s1:
            search_vno = st.text_input("Search by Voucher Number (e.g., 14M312640383)").strip()
        with s2:
             imbalanced_check = st.checkbox("Show Only Imbalanced Vouchers (Dr != Cr Audit Check)")

        if imbalanced_check:
            v_chk = full_tx.groupby([vh_id, vh_no, 'Location_Label', 'Parsed_Date'], as_index=False).agg(
                Sum_Dr=('Dr_Amt', 'sum'),
                Sum_Cr=('Cr_Amt', 'sum')
            )
            v_chk['Diff'] = (v_chk['Sum_Dr'] - v_chk['Sum_Cr']).round(2)
            bad_v = v_chk[v_chk['Diff'].abs() > 0.01]
            if bad_v.empty:
                st.success("✅ Audit Passed! Saare vouchers me Total Debit == Total Credit 100% matched hai.")
            else:
                st.error(f"⚠️ Found {len(bad_v)} Imbalanced Vouchers:")
                st.dataframe(bad_v, use_container_width=True)

        if search_vno:
            v_matches = full_tx[full_tx[vh_no].astype(str).str.contains(search_vno, case=False, na=False)].copy()
            st.write(f"Matching Lines Found: **{len(v_matches)}**")
            st.dataframe(
                v_matches[['Parsed_Date', vh_no, 'Location_Label', 'Account_Label', 'Dr_Amt', 'Cr_Amt', vd_narr]],
                use_container_width=True
            )

    # ==============================================================================
    # MODULE 8: MASTERS & RAW TABLE BROWSER
    # ==============================================================================
    elif nav_module == "🗂️ Masters & Chart of Accounts":
        st.title("🗂️ Database Masters & Raw Table Explorer")
        sel_t = st.selectbox("Select Table to View / Export", tables, index=tables.index("MiscMaster") if "MiscMaster" in tables else 0)
        if sel_t:
            df_raw = load_mdb_table(user_mdb_path, sel_t, file_mtime)
            st.write(f"Total Rows: **{len(df_raw):,}** | Columns: `{list(df_raw.columns)}`")
            st.dataframe(df_raw, use_container_width=True, height=540)

            xl_raw = io.BytesIO()
            with pd.ExcelWriter(xl_raw, engine='openpyxl') as wr:
                df_raw.to_excel(wr, index=False, sheet_name=sel_t[:30])
            st.download_button(f"📥 Export {sel_t} to Excel", xl_raw.getvalue(), f"{sel_t}.xlsx")

except Exception as e:
    st.error(f"Execution Error: {e}")
    st.code(traceback.format_exc())
