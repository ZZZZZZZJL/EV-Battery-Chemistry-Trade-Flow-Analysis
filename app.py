import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os

# ==========================================
# 1. 全局配置与常量
# ==========================================
st.set_page_config(page_title="Critical Mineral Flows", layout="wide")

# 特殊节点 ID 定义
SPECIAL_IDS = {991, 992, 993, 994, 995, 996, 997, 998, 999}
UARP_ID, NTRM_ID, NBCP_ID = 994, 997, 999

# ID 颜色映射
ID_COLORS = {
    32: '#F6B50C', 36: '#DB05AA', 56: '#C8102E', 76: '#009639', 104: '#FFCD00',
    124: '#01FFFF', 140: '#3E6E48', 152: '#008A03', 156: '#E81313', 170: '#FFCD00',
    180: '#028573', 192: '#ADD8E6', 246: '#002F6C', 251: '#ED2939', 266: '#009E60',
    268: '#DA291C', 288: '#EF3340', 300: '#001489', 356: '#FF9933', 360: '#53C55E',
    384: '#FF8200', 392: '#FB9431', 398: '#00AFCA', 410: '#6D9EEB', 450: '#F2D2BD',
    458: '#0032A0', 484: '#006341', 504: '#C1272D', 540: '#30D5C8', 579: '#BA0C2F',
    598: '#FFCD00', 608: '#FFD580', 620: '#016201', 643: '#B7B7B7', 704: '#C8102E',
    710: '#773F05', 716: '#056002', 724: '#AA151B', 804: '#0057B7', 826: '#012169',
    842: '#635EFF', 894: '#FFC0CB', 986: '#4B535D',
    991: '#CCCCCC', 992: '#CCCCCC', 993: '#CCCCCC', 994: '#CCCCCC',
    995: '#CCCCCC', 996: '#CCCCCC', 997: '#CCCCCC', 998: '#CCCCCC', 999: '#CCCCCC'
}


def hex_to_rgba(hex_val, opacity=0.4):
    hex_val = hex_val.lstrip('#')
    rgb = tuple(int(hex_val[i:i + len(hex_val) // 3], 16) for i in range(0, len(hex_val), len(hex_val) // 3))
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {opacity})"


def get_color(node_id):
    try:
        return ID_COLORS.get(int(float(node_id)), "#CCCCCC")
    except:
        return "#CCCCCC"


# ==========================================
# 2. 核心逻辑 (缓存以提高速度)
# ==========================================
@st.cache_data
def get_sankey_data(year, metal, data_dir):
    """读取数据并构建 Nodes 和 Links"""
    file_path = os.path.join(data_dir, metal, f"{year}_matching.csv")

    if not os.path.exists(file_path):
        return None, None, None

    df = pd.read_csv(file_path)
    links = []
    nodes = {}

    # 阶段定义
    S1, S2, S3, S4, S5 = "S1", "S2", "S3", "S4", "S5"
    S_UARP = "S_UARP"
    stage_flows = {S1: 0, S2: 0, S3: 0, S4: 0, S5: 0}

    # 1. 1st Post-Trade
    t1_df = df.iloc[:, [3, 4, 5, 6, 7]].dropna(subset=[df.columns[7]])
    for _, row in t1_df.iterrows():
        sid, sname, tid, tname, val = int(row[0]), row[1], int(row[2]), row[3], row[4]
        if val <= 0 or (sid in SPECIAL_IDS and tid in SPECIAL_IDS): continue

        if sid == UARP_ID:
            src, tgt = (S_UARP, sid), (S3, tid)
            stage_flows[S3] += val
        elif tid == NTRM_ID:
            src, tgt = (S2, sid), (S3, tid)
            stage_flows[S2] += val
        else:
            src, tgt = (S1, sid), (S2, tid)
            stage_flows[S1] += val

        nodes[src], nodes[tgt] = sname, tname
        links.append({'source': src, 'target': tgt, 'value': val, 'color_id': sid})

    # 2. Refining Production
    s2_df = df.iloc[:, [8, 9, 10]].dropna()
    for _, row in s2_df.iterrows():
        nid, name, val = int(row[0]), row[1], row[2]
        if val > 0:
            src, tgt = (S2, nid), (S3, nid)
            nodes[src], nodes[tgt] = name, name
            links.append({'source': src, 'target': tgt, 'value': val, 'color_id': nid})
            stage_flows[S2] += val

            # 3. 2nd Post-Trade
    t2_df = df.iloc[:, [11, 12, 13, 14, 15]].dropna(subset=[df.columns[15]])
    for _, row in t2_df.iterrows():
        sid, sname, tid, tname, val = int(row[0]), row[1], int(row[2]), row[3], row[4]
        if val <= 0 or (sid in SPECIAL_IDS and tid in SPECIAL_IDS): continue

        if tid == NBCP_ID:
            src, tgt = (S4, sid), (S5, tid)
            stage_flows[S4] += val
        else:
            src, tgt = (S3, sid), (S4, tid)
            stage_flows[S3] += val

        nodes[src], nodes[tgt] = sname, tname
        links.append({'source': src, 'target': tgt, 'value': val, 'color_id': sid})

    # 4. Manufacturing Production
    s3_df = df.iloc[:, [16, 17, 18]].dropna()
    for _, row in s3_df.iterrows():
        nid, name, val = int(row[0]), row[1], row[2]
        if val > 0:
            src, tgt = (S4, nid), (S5, nid)
            nodes[src], nodes[tgt] = name, name
            links.append({'source': src, 'target': tgt, 'value': val, 'color_id': nid})
            stage_flows[S4] += val

    return nodes, links, stage_flows


# ==========================================
# 3. 网页界面与交互
# ==========================================
st.title("🔋 Critical Mineral Flows Visualizer")
st.markdown("Select a metal and year to visualize the global supply chain flows.")

# --- 侧边栏：控制面板 ---
with st.sidebar:
    st.header("Settings")

    # 选择金属
    selected_metal = st.selectbox("Select Metal", ["Li", "Co", "Ni", "Mn"], index=0)

    # 选择年份
    selected_year = st.selectbox("Select Year", [2020, 2021, 2022, 2023, 2024], index=4)

    st.divider()

    # 缩放控制 (参考块大小)
    st.subheader("Scale Reference")
    ref_qty = st.number_input("Reference Quantity (tons)", value=10000, step=1000)
    # 不再让用户输入像素，而是根据屏幕自动调整，或者这里仅仅是作为数据计算
    # 在网页上，固定像素高度可能不太好适配，但我们可以保留原始逻辑

    # 路径设置 (适配当前目录)
    # 假设 data 文件夹在 app.py 同级目录
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# --- 数据处理 ---
nodes, links, stage_flows = get_sankey_data(selected_year, selected_metal, DATA_DIR)

if nodes is None:
    st.error(f"Data not found for {selected_metal} in {selected_year}. Please check the 'data' folder structure.")
else:
    # --- 添加参考流逻辑 ---
    if ref_qty > 0:
        ref_label = f"{ref_qty:,.0f} t"
        k1, k2, k3, k4, k5 = ("REF_S1", 0), ("REF_S2", 0), ("REF_S3", 0), ("REF_S4", 0), ("REF_S5", 0)

        # 仅最后一个节点有标签
        nodes[k1], nodes[k2], nodes[k3], nodes[k4] = "", "", "", ""
        nodes[k5] = ref_label

        transparent = "rgba(0,0,0,0)"
        for s, t in [(k1, k2), (k2, k3), (k3, k4), (k4, k5)]:
            links.append({'source': s, 'target': t, 'value': ref_qty, 'color_code': transparent})

    # --- 绘图准备 ---
    sorted_node_keys = sorted(nodes.keys(), key=lambda x: (x[0], str(x[1])))
    node_map = {key: i for i, key in enumerate(sorted_node_keys)}

    node_labels = [nodes[k] for k in sorted_node_keys]

    node_colors = []
    for k in sorted_node_keys:
        if isinstance(k[0], str) and k[0].startswith("REF_"):
            node_colors.append("#888888" if k[0] == "REF_S5" else "rgba(0,0,0,0)")
        else:
            node_colors.append(get_color(k[1]))

    link_sources = [node_map[l['source']] for l in links]
    link_targets = [node_map[l['target']] for l in links]
    link_values = [l['value'] for l in links]

    link_colors = []
    for l in links:
        if 'color_code' in l:
            link_colors.append(l['color_code'])
        else:
            link_colors.append(hex_to_rgba(get_color(l['color_id']), 0.4))

    # --- 计算动态高度 ---
    # 网页端可以设置得稍微大一点
    # 逻辑：以 10000 吨 = 50px 为基准 (用户不可见，作为内部比例)
    base_ref_pixels = 50
    max_flow = max(stage_flows.values()) if stage_flows else 0
    if max_flow > 0:
        pixels_per_unit = base_ref_pixels / ref_qty
        calc_height = max_flow * pixels_per_unit + 250
        chart_height = max(600, int(calc_height))
    else:
        chart_height = 600

    # --- 生成图表 ---
    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15, thickness=20,
            line=dict(color="black", width=0.5),
            label=node_labels,
            color=node_colors,
            # 网页版建议不强制黑色字体，除非你把背景设为纯白
            # 这里留空，自适应 Streamlit 的明/暗模式
        ),
        link=dict(
            source=link_sources, target=link_targets,
            value=link_values, color=link_colors
        )
    )])

    fig.update_layout(
        title_text=f"{selected_metal} Flows - {selected_year}",
        font_size=12,
        height=chart_height,
        margin=dict(l=20, r=20, t=40, b=20)
    )

    # --- 显示 ---
    st.plotly_chart(fig, use_container_width=True)

    # 额外信息
    with st.expander("Show Statistics"):
        st.write(f"Max Stage Flow: {max_flow:,.0f} t")
        st.write(stage_flows)