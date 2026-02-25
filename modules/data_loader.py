import streamlit as st
import pandas as pd
import os
import glob
from .config import REF_FILE, PROD_FILES, TRADE_DIR


@st.cache_data
def load_reference():
    if not os.path.exists(REF_FILE): return {}, pd.DataFrame()
    ref_df = pd.read_excel(REF_FILE)
    id_to_name = dict(zip(ref_df['id'], ref_df['text']))
    return id_to_name, ref_df[['id', 'text']]


@st.cache_data
def load_raw_production():
    """读取所有生产数据 Excel"""
    m = pd.read_excel(PROD_FILES["Mining"])
    r = pd.read_excel(PROD_FILES["Refining"])
    c = pd.read_excel(PROD_FILES["Cathode"])
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
def load_trade_flows(folder_name, metal, year):
    """
    针对 CSV 优化的读取函数
    """
    path = os.path.join(TRADE_DIR, folder_name)
    flows = []
    if not os.path.exists(path): return pd.DataFrame()

    target_folders = [f for f in os.listdir(path) if f.startswith(metal)]
    for sub in target_folders:
        files = glob.glob(os.path.join(path, sub, "*_combined.csv"))
        for f in files:
            try:
                # 简单文件名检查，避免无效 IO
                filename = os.path.basename(f)
                importer_id = int(filename.split('_')[0])
                if importer_id == 0: continue

                # 【核心优化】只读取需要的列，显著提升 CSV 读取速度
                df = pd.read_csv(
                    f,
                    usecols=['Year', 'Partner ID', 'Quantity'],
                    engine='c'  # 强制使用 C 引擎
                )

                # 过滤年份
                df_y = df[df['Year'] == year]

                # 转换为 List of Dicts (比 DataFrame append 快)
                for _, r in df_y.iterrows():
                    try:
                        exporter_id = int(r['Partner ID'])
                        if exporter_id == 0: continue
                        flows.append({'exporter': exporter_id, 'importer': importer_id, 'value': r['Quantity']})
                    except:
                        continue
            except:
                continue

    return pd.DataFrame(flows) if flows else pd.DataFrame(columns=['exporter', 'importer', 'value'])