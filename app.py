import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# 导入我们的模块
from modules.config import get_color, hex_to_rgba
from modules.data_loader import load_reference, load_raw_production, get_production_dicts, load_trade_flows
from modules.sankey_algo import run_sankey_algorithm, calculate_explicit_positions, get_node_name

st.set_page_config(page_title="Sankey Flow Generator", layout="wide")
st.title("🔋 Critical Mineral Flows Visualizer")

# ==================== 侧边栏 ====================
with st.sidebar:
    st.header("1. General Settings")

    # 【修改点 1】修改默认值为 Li, 2020
    # index=0 对应列表第一个元素 "Li"
    sel_metal = st.selectbox("Metal", ["Li", "Co", "Ni", "Mn"], index=0)

    # index=0 对应列表第一个元素 2020
    sel_year = st.selectbox("Year", [2020, 2021, 2022, 2023, 2024], index=0)

    # 【修改点 2】修改默认参考数量为 20000
    ref_qty = st.number_input("Ref Qty (t)", value=20000, step=1000)

    # ... (Header 1. General Settings 部分保持不变) ...

    st.divider()
    st.header("2. Layout Config")

    # -------------------------------------------------------
    # 【修改点 1】Layout Settings
    # 风格改为：Caption (指引) + Expander (操作区)
    # -------------------------------------------------------
    st.caption("Customize intermediate stages")  # 简短指引
    with st.expander("Open Configuration", expanded=False):
        # 原有的配置逻辑
        special_stages = {}
        alignments = {}


        def config_node(node_name, default_stage, inter_stage):
            opt = st.selectbox(f"{node_name}", [f"{default_stage}", f"{inter_stage}"])
            target = default_stage if default_stage in opt else inter_stage
            special_stages[node_name] = target


        st.markdown("**Mining Stage**")
        config_node("TFCM", "S1", "S1.5")
        config_node("TTCR", "S2", "S1.5")
        config_node("URMS", "S1", "S1.5")
        alignments["S1.5"] = st.radio("Align S1.5", ["Top", "Bottom"], index=0, horizontal=True)

        st.markdown("---")
        st.markdown("**Refining Stage**")
        config_node("UARP", "S2", "S2.5")
        config_node("NTRM", "S3", "S2.5")
        alignments["S2.5"] = st.radio("Align S2.5", ["Top", "Bottom"], index=0, horizontal=True)

        st.markdown("---")
        st.markdown("**Manuf. Input**")
        config_node("TFCR", "S3", "S3.5")
        config_node("MRMT", "S3", "S3.5")
        config_node("NCPC", "S4", "S3.5")
        alignments["S3.5"] = st.radio("Align S3.5", ["Top", "Bottom"], index=0, horizontal=True)

        st.markdown("---")
        st.markdown("**Manuf. Output**")
        config_node("NBCP", "S5", "S4.5")
        alignments["S4.5"] = st.radio("Align S4.5", ["Top", "Bottom"], index=0, horizontal=True)

    st.divider()
    st.header("3. Reference & Helpers")

    # -------------------------------------------------------
    # 【修改点 2】Search Country (保持原样，作为视觉参考)
    # -------------------------------------------------------
    st.caption("Find country ID by name")  # 简短指引
    id_map, ref_df = load_reference()
    search = st.text_input("Search Country", label_visibility="collapsed", placeholder="Type country name...")
    if search:
        res = ref_df[ref_df['text'].str.contains(search, case=False, na=False)]
        st.dataframe(res, hide_index=True)

    # -------------------------------------------------------
    # 【修改点 3】Acronym Legend
    # 风格改为：Caption (指引) + Expander (查看区)
    # -------------------------------------------------------
    st.caption("View special acronym definitions")  # 简短指引
    with st.expander("Show Legend"):
        st.markdown("""
            <small style='line-height: 1.4;'>
            <b>NBCP</b>: Non-Battery Cathode Products<br>
            <b>NCPC</b>: Trade to countries w/o production<br>
            <b>NTRM</b>: Unaccounted Raw Materials<br>
            <b>MRMT</b>: Missing Refined Trade<br>
            <b>URMS</b>: Unknown Raw Material Source<br>
            <b>UARP</b>: Unaccounted Refining Prod.<br>
            <b>TTCR</b>: Trade to non-refining countries<br>
            <b>TFCR</b>: Trade from non-refining countries<br>
            <b>TFCM</b>: Trade from non-mining countries
            </small>
            """, unsafe_allow_html=True)

# ==================== 数据加载 ====================
m_raw, r_raw, c_raw = load_raw_production()
s1_d, s2_d, s3_d = get_production_dicts(sel_metal, sel_year, m_raw, r_raw, c_raw)

with st.spinner("Loading trade data..."):
    t1_df = load_trade_flows("1st_post_trade", sel_metal, sel_year)
    t2_df = load_trade_flows("2nd_post_trade", sel_metal, sel_year)

# 预运行一次以获取节点列表
init_nodes, _, _ = run_sankey_algorithm(s1_d, s2_d, s3_d, t1_df, t2_df, id_map, special_stages)
stage_node_names = {}
for (stage, _), label in init_nodes.items():
    if stage not in stage_node_names: stage_node_names[stage] = []
    if label not in stage_node_names[stage] and label != "":
        stage_node_names[stage].append(label)

# ==================== 主界面 ====================
tab1, tab2 = st.tabs(["⚙️ Editor", "📊 Diagram"])

with tab1:
    # 定义编辑器组件函数
    def editor_widget(prod_dict, key):
        # 将字典转换为 DataFrame 用于编辑
        data = [{"ID": k, "Name": get_node_name(k, id_map), "Quantity": v} for k, v in prod_dict.items()]
        df = st.data_editor(pd.DataFrame(data), key=key, num_rows="dynamic", hide_index=True, use_container_width=True)
        # 将编辑后的 DataFrame 转回字典
        return dict(zip(df["ID"], df["Quantity"]))


    # 初始化排序字典
    user_sort = {}


    # 辅助函数：渲染排序组件
    def render_sort_widgets(stages_to_show):
        # 使用列布局让排序框横向排列，节省垂直空间
        cols = st.columns(len(stages_to_show))
        for idx, s in enumerate(stages_to_show):
            with cols[idx]:
                if s in stage_node_names and stage_node_names[s]:
                    user_sort[s] = st.multiselect(
                        f"Order: {s}",
                        stage_node_names[s],
                        default=stage_node_names[s],
                        label_visibility="collapsed"
                    )


    # ==========================================
    # 第一部分：Mining (S1)
    # ==========================================
    st.markdown("### S1: Mining Production")
    s1_final = editor_widget(s1_d, "s1")

    # 下方放置对应的排序 (S1 和 S1.5)
    with st.expander("Adjust Order (S1)", expanded=True):
        render_sort_widgets(["S1", "S1.5"])
    with st.expander("Adjust Order (S2: 1st post-trade)", expanded=True):
        render_sort_widgets(["S2", "S2.5"])

    st.divider()

    # ==========================================
    # 第二部分：Refining (S2)
    # ==========================================
    st.markdown("### S3: Refining Production")
    s2_final = editor_widget(s2_d, "s3")

    with st.expander("Adjust Order (S3)", expanded=True):
        render_sort_widgets(["S3", "S3.5"])
    with st.expander("Adjust Order (S4: 2nd post-trade)", expanded=True):
        render_sort_widgets(["S4", "S4.5"])

    st.divider()

    # ==========================================
    # 第三部分：Manufacturing (S3)
    # ==========================================
    st.markdown("### S5: Cathode & Electrolyte Manufacturing")
    s3_final = editor_widget(s3_d, "s5")
    with st.expander("Adjust Order (S5)", expanded=True):
        render_sort_widgets(["S5"])

with tab2:
    if st.button("Generate Sankey"):
        # 调用算法模块
        nodes, links, stage_flows = run_sankey_algorithm(s1_final, s2_final, s3_final, t1_df, t2_df, id_map,
                                                         special_stages)

        # 添加参考流
        if ref_qty > 0:
            rk1, rk2, rk3, rk4, rk5 = ("REF_S1", 0), ("REF_S2", 0), ("REF_S3", 0), ("REF_S4", 0), ("REF_S5", 0)
            nodes[rk1], nodes[rk2], nodes[rk3], nodes[rk4] = "", "", "", ""
            nodes[rk5] = f"{ref_qty:,.0f} t"
            trans = "rgba(0,0,0,0)"
            for s, t in [(rk1, rk2), (rk2, rk3), (rk3, rk4), (rk4, rk5)]:
                links.append({'source': s, 'target': t, 'value': ref_qty, 'color_code': trans})

        # 聚合 links
        agg_links = {}
        for l in links:
            k = (l['source'], l['target'])
            if k not in agg_links: agg_links[k] = {'value': 0, 'c_code': l.get('color_code'), 'c_id': l.get('color_id')}
            agg_links[k]['value'] += l['value']
            # 保留颜色属性 (优先特殊颜色)
            if l.get('color_code'): agg_links[k]['c_code'] = l['color_code']
            if l.get('color_id') and not agg_links[k]['c_id']: agg_links[k]['c_id'] = l['color_id']

        final_links = []
        for (s, t), d in agg_links.items():
            final_links.append(
                {'source': s, 'target': t, 'value': d['value'], 'color_code': d['c_code'], 'color_id': d['c_id']})

        # 计算坐标
        sorted_keys, nx, ny = calculate_explicit_positions(nodes, final_links, user_sort, stage_flows, alignments,
                                                           ref_qty)

        # 绘图
        node_map = {k: i for i, k in enumerate(sorted_keys)}
        node_lbl = [nodes[k] for k in sorted_keys]
        node_clr = ["#888888" if str(k[0]).startswith("REF_S5") else (
            "rgba(0,0,0,0)" if str(k[0]).startswith("REF_") else get_color(k[1])) for k in sorted_keys]

        lnk_src = [node_map[l['source']] for l in final_links]
        lnk_tgt = [node_map[l['target']] for l in final_links]
        lnk_val = [l['value'] for l in final_links]

        # 处理连线颜色
        lnk_clr = []
        for l in final_links:
            if l.get('color_code'):
                lnk_clr.append(l['color_code'])
            else:
                cid = l.get('color_id')
                # 修复潜在的 None 问题
                if cid is None: cid = 0
                lnk_clr.append(hex_to_rgba(get_color(cid), 0.4))

        fig = go.Figure(go.Sankey(
            arrangement="fixed",
            node=dict(pad=15, thickness=20, line=dict(color="black", width=0.5), label=node_lbl, color=node_clr, x=nx,
                      y=ny),
            link=dict(source=lnk_src, target=lnk_tgt, value=lnk_val, color=lnk_clr)
        ))

        # 计算高度
        max_f = max(stage_flows.values()) if stage_flows else 0
        h = (max_f / ref_qty * 50 + 200) if (ref_qty > 0 and max_f > 0) else 800
        fig.update_layout(height=max(600, int(h)), title_text=f"{sel_metal} {sel_year}")
        st.plotly_chart(fig, use_container_width=True)