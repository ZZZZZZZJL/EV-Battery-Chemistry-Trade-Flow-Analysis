import streamlit as st
import pandas as pd
import os
import glob
from .config import REF_FILE, TRADE_DIR, DATA_DIR


@st.cache_data
def load_reference():
    if not os.path.exists(REF_FILE): return {}, pd.DataFrame()
    ref_df = pd.read_excel(REF_FILE)
    id_to_name = dict(zip(ref_df['id'], ref_df['text']))
    return id_to_name, ref_df[['id', 'text']]


@st.cache_data
def load_raw_production(s1_source="country", s3_source="country", s5_source="country"):
    """
    按阶段分别读取 production 数据：
    - S1 (Mining)
    - S3 (Refining)
    - S5 (Cathode Manufacturing)

    参数
    ----
    s1_source / s3_source / s5_source : str
        "country" 或 "ownership"
    """

    def normalize_source(x):
        x = str(x).strip().lower()
        if x not in ["country", "ownership"]:
            raise ValueError("production source must be 'country' or 'ownership'")
        return x

    s1_source = normalize_source(s1_source)
    s3_source = normalize_source(s3_source)
    s5_source = normalize_source(s5_source)

    production_root = os.path.join(DATA_DIR, "production")

    mining_path = os.path.join(production_root, s1_source, "Mining_Production.xlsx")
    refining_path = os.path.join(production_root, s3_source, "Refining_Production.xlsx")
    cathode_path = os.path.join(production_root, s5_source, "Cathode_Production_converted.xlsx")

    if not os.path.exists(mining_path):
        raise FileNotFoundError(f"Mining production file not found: {mining_path}")
    if not os.path.exists(refining_path):
        raise FileNotFoundError(f"Refining production file not found: {refining_path}")
    if not os.path.exists(cathode_path):
        raise FileNotFoundError(f"Cathode production file not found: {cathode_path}")

    m = pd.read_excel(mining_path)
    r = pd.read_excel(refining_path)
    c = pd.read_excel(cathode_path)

    return m, r, c


def get_production_dicts(metal, year, m_prod, r_prod, c_prod):
    """
    根据选择的金属和年份，从三个生产数据表中提取 {CountryID: Quantity} 字典。
    适配 LFP, NCM, NCA 三种正极材料体系。
    """

    # ==========================================
    # 1. Mining Production (S1)
    # ==========================================
    try:
        m_cols = [f"{metal}_ID", f"{metal}_Qty"]
        m_data = m_prod[m_prod['Year'] == year][m_cols].dropna()
        s1_prod = dict(zip(m_data[f"{metal}_ID"], m_data[f"{metal}_Qty"]))
    except KeyError:
        s1_prod = {}

    # ==========================================
    # 2. Refining Production (S2)
    # ==========================================
    try:
        r_cols = [f"{metal}_ID", f"{metal}_Qty"]
        r_data = r_prod[r_prod['Year'] == year][r_cols].dropna()
        s2_prod = dict(zip(r_data[f"{metal}_ID"], r_data[f"{metal}_Qty"]))
    except KeyError:
        s2_prod = {}

    # ==========================================
    # 3. Manufacturing Production (S3)
    # ==========================================
    c_df = c_prod[c_prod['Year'] == year]
    s3_list = []

    # 定义列名 (处理 CSV 中的拼写特例)
    # 注意：根据您的文件，NCA 的 Ni 列名为 'NCA_Ni_QMetal_ty'
    s3_breakdown = {}

    def add_breakdown(cid, ctype, qty):
        if cid not in s3_breakdown:
            s3_breakdown[cid] = {'NCM': 0, 'NCA': 0, 'LFP': 0}
        s3_breakdown[cid][ctype] += qty

    col_nca_ni = 'NCA_Ni_QMetal_ty' if 'NCA_Ni_QMetal_ty' in c_df.columns else 'NCA_Ni_Metal_Qty'

    if metal == "Li":
        for _, row in c_df.iterrows():
            if not pd.isna(row.get('NCM_ID')) and not pd.isna(row.get('NCM_Li_Metal_Qty')):
                s3_list.append({'id': row['NCM_ID'], 'qty': row['NCM_Li_Metal_Qty']})
                add_breakdown(row['NCM_ID'], 'NCM', row['NCM_Li_Metal_Qty'])
            if not pd.isna(row.get('NCA_ID')) and not pd.isna(row.get('NCA_Li_Metal_Qty')):
                s3_list.append({'id': row['NCA_ID'], 'qty': row['NCA_Li_Metal_Qty']})
                add_breakdown(row['NCA_ID'], 'NCA', row['NCA_Li_Metal_Qty'])
            if not pd.isna(row.get('LFP_ID')) and not pd.isna(row.get('LFP_Li_Metal_Qty')):
                s3_list.append({'id': row['LFP_ID'], 'qty': row['LFP_Li_Metal_Qty']})
                add_breakdown(row['LFP_ID'], 'LFP', row['LFP_Li_Metal_Qty'])

    elif metal == "Co":
        for _, row in c_df.iterrows():
            if not pd.isna(row.get('NCM_ID')) and not pd.isna(row.get('NCM_Co_Metal_Qty')):
                s3_list.append({'id': row['NCM_ID'], 'qty': row['NCM_Co_Metal_Qty']})
                add_breakdown(row['NCM_ID'], 'NCM', row['NCM_Co_Metal_Qty'])
            if not pd.isna(row.get('NCA_ID')) and not pd.isna(row.get('NCA_Co_Metal_Qty')):
                s3_list.append({'id': row['NCA_ID'], 'qty': row['NCA_Co_Metal_Qty']})
                add_breakdown(row['NCA_ID'], 'NCA', row['NCA_Co_Metal_Qty'])

    elif metal == "Ni":
        for _, row in c_df.iterrows():
            if not pd.isna(row.get('NCM_ID')) and not pd.isna(row.get('NCM_Ni_Metal_Qty')):
                s3_list.append({'id': row['NCM_ID'], 'qty': row['NCM_Ni_Metal_Qty']})
                add_breakdown(row['NCM_ID'], 'NCM', row['NCM_Ni_Metal_Qty'])
            if not pd.isna(row.get('NCA_ID')) and not pd.isna(row.get(col_nca_ni)):
                s3_list.append({'id': row['NCA_ID'], 'qty': row[col_nca_ni]})
                add_breakdown(row['NCA_ID'], 'NCA', row[col_nca_ni])

    elif metal == "Mn":
        mn_col = 'NCM_Mn_Metal_Qty'
        if mn_col in c_df.columns:
            for _, row in c_df.iterrows():
                if not pd.isna(row.get('NCM_ID')) and not pd.isna(row.get(mn_col)):
                    s3_list.append({'id': row['NCM_ID'], 'qty': row[mn_col]})
                    add_breakdown(row['NCM_ID'], 'NCM', row[mn_col])

    if s3_list:
        s3_prod = pd.DataFrame(s3_list).groupby('id')['qty'].sum().to_dict()
    else:
        s3_prod = {}

    # 增加了一个返回值 s3_breakdown
    return s1_prod, s2_prod, s3_prod, s3_breakdown


@st.cache_data
def load_trade_flows(folder_name, metal, year, trade_mode):
    """
    读取贸易流数据，并统一输出为标准方向:
    exporter -> importer

    参数
    ----
    folder_name : str
        "1st_post_trade" 或 "2nd_post_trade"
    metal : str
        "Li" / "Co" / "Ni" / "Mn"
    year : int
        目标年份
    trade_mode : str
        "import" 或 "export"

    数据语义
    ----
    1) import 文件:
       - 文件 id = 报告的进口国（买进）
       - Partner ID = 出口方（卖出）
       => exporter = Partner ID
          importer = 文件 id

    2) export 文件:
       - 文件 id = 报告的出口国（卖出）
       - Partner ID = 进口方（买进）
       => exporter = 文件 id
          importer = Partner ID
    """
    trade_mode = str(trade_mode).strip().lower()
    if trade_mode not in ["import", "export"]:
        raise ValueError("trade_mode must be 'import' or 'export'")

    path = os.path.join(TRADE_DIR, trade_mode, folder_name)
    flows = []

    if not os.path.exists(path):
        return pd.DataFrame(columns=["exporter", "importer", "value"])

    target_folders = [f for f in os.listdir(path) if f.startswith(metal)]

    for sub in target_folders:
        files = glob.glob(os.path.join(path, sub, "*_combined.csv"))

        for f in files:
            try:
                filename = os.path.basename(f)
                reporter_id = int(filename.split("_")[0])

                if reporter_id == 0:
                    continue

                df = pd.read_csv(
                    f,
                    usecols=["Year", "Partner ID", "Quantity"],
                    engine="c"
                )

                df_y = df[df["Year"] == year]

                for _, r in df_y.iterrows():
                    try:
                        partner_id = int(r["Partner ID"])
                        qty = float(r["Quantity"])

                        if partner_id == 0 or qty <= 0:
                            continue

                        if trade_mode == "import":
                            # 文件国 = importer, Partner = exporter
                            exporter_id = partner_id
                            importer_id = reporter_id
                        else:  # trade_mode == "export"
                            # 文件国 = exporter, Partner = importer
                            exporter_id = reporter_id
                            importer_id = partner_id

                        flows.append({
                            "exporter": exporter_id,
                            "importer": importer_id,
                            "value": qty
                        })

                    except:
                        continue

            except:
                continue

    return pd.DataFrame(flows) if flows else pd.DataFrame(columns=["exporter", "importer", "value"])
