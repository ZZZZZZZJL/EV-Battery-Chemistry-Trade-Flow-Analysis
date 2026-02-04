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
    """处理生产数据逻辑"""
    m_data = m_prod[m_prod['Year'] == year][[f"{metal}_ID", f"{metal}_Qty"]].dropna()
    s1_prod = dict(zip(m_data[f"{metal}_ID"], m_data[f"{metal}_Qty"]))

    r_data = r_prod[r_prod['Year'] == year][[f"{metal}_ID", f"{metal}_Qty"]].dropna()
    s2_prod = dict(zip(r_data[f"{metal}_ID"], r_data[f"{metal}_Qty"]))

    if metal == "Li":
        c_df = c_prod[c_prod['Year'] == year]
        s3_list = []
        for _, r in c_df.iterrows():
            if not pd.isna(r['NCX_ID']): s3_list.append({'id': r['NCX_ID'], 'qty': r['NCX_Li_Metal_Qty']})
            if not pd.isna(r['LFP_ID']): s3_list.append({'id': r['LFP_ID'], 'qty': r['LFP_Li_Metal_Qty']})
        s3_prod = pd.DataFrame(s3_list).groupby('id').sum().to_dict()['qty'] if s3_list else {}
    else:
        c_data = c_prod[c_prod['Year'] == year][["NCX_ID", f"NCX_{metal}_Metal_Qty"]].dropna()
        s3_prod = dict(zip(c_data["NCX_ID"], c_data[f"NCX_{metal}_Metal_Qty"]))

    return s1_prod, s2_prod, s3_prod


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