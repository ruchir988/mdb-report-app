import streamlit as st
import pandas as pd
import subprocess
import tempfile
import os
import io

st.set_page_config(page_title="MDB Report Generator", layout="wide")
st.title("📂 MDB Financial Reports & Exporter")

# Helper function: Linux par mdb-tables se table names nikalna
def get_tables(mdb_path):
    try:
        cmd = ["mdb-tables", "-1", mdb_path]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        tables = [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]
        return tables
    except Exception as e:
        st.error(f"Error fetching tables: {e}")
        return []

# Helper function: Kisi bhi table ka data CSV ke through DataFrame me convert karna
def read_table(mdb_path, table_name):
    cmd = ["mdb-export", mdb_path, table_name]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return pd.read_csv(io.StringIO(result.stdout))

uploaded_file = st.file_uploader("Upload .mdb File", type=["mdb"])

if uploaded_file is not None:
    # Uploaded file ko temp disk pe save karein
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mdb") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    try:
        tables = get_tables(tmp_path)
        st.success(f"Database loaded! Total tables found: {len(tables)}")

        # Sidebar navigation
        menu = st.sidebar.selectbox("Choose Action / Report", ["Table Viewer", "Trial Balance", "Dynamic Export"])

        if menu == "Table Viewer":
            st.subheader("Database Table Explorer")
            selected_table = st.selectbox("Select Table to View", tables)
            if selected_table:
                df = read_table(tmp_path, selected_table)
                st.write(f"Row count: {len(df)}")
                st.dataframe(df, use_container_width=True)

                # Excel Export
                excel_buf = io.BytesIO()
                with pd.ExcelWriter(excel_buf, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name=selected_table[:30])
                
                st.download_button(
                    label=f"📥 Download {selected_table} as Excel",
                    data=excel_buf.getvalue(),
                    file_name=f"{selected_table}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        elif menu == "Trial Balance":
            st.subheader("Trial Balance (Summary)")
            # Agar BalanceMaster / BalanceData ya AccountMaster available hai
            if "AccountMaster" in tables:
                acc_df = read_table(tmp_path, "AccountMaster")
                st.dataframe(acc_df.head(100), use_container_width=True)
            else:
                st.warning("AccountMaster table is database me nahi mila.")

        elif menu == "Dynamic Export":
            st.subheader("Dynamic Filter & Multi-Table Export")
            st.info("Aap specific report criteria aur ledger formulas yahan configure kar sakte hain.")

    except Exception as e:
        st.error(f"Error reading .mdb file: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
