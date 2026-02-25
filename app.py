import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# 导入我们的模块
from modules.config import get_color, hex_to_rgba, DEFAULT_ORDERS
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

    s5_mode = st.radio("Final Stage Output Mode", ["By Country", "By Chemistry Type"])

    calc_mass_balance = st.radio("Mass Balance Option", ["No (Default)", "Yes (Split Gap)"],
                                 index=0) == "Yes (Split Gap)"

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
s1_d, s2_d, s3_d, s3_breakdown = get_production_dicts(sel_metal, sel_year, m_raw, r_raw, c_raw)

with st.spinner("Loading trade data..."):
    t1_df = load_trade_flows("1st_post_trade", sel_metal, sel_year)
    t2_df = load_trade_flows("2nd_post_trade", sel_metal, sel_year)

# 预运行以获取排序列表 (注意这里多加了 init_links 来接住返回值)
init_nodes, init_links, _ = run_sankey_algorithm(s1_d, s2_d, s3_d, t1_df, t2_df, id_map, special_stages, s3_breakdown,
                                                 s5_mode, calc_mass_balance)

# === 【新增代码区】计算每个节点的流量大小 (用于 Quantity 排序) ===
node_sizes = {}
node_ins, node_outs = {}, {}
for l in init_links:
    t, s, v = l['target'], l['source'], l['value']
    node_ins[t] = node_ins.get(t, 0) + v
    node_outs[s] = node_outs.get(s, 0) + v
for n in init_nodes.keys():
    # 桑基图中节点的实际视觉大小等于 max(流入, 流出)
    node_sizes[n] = max(node_ins.get(n, 0), node_outs.get(n, 0))

# 收集每个阶段出现的名字
stage_node_names = {}
for (stage, _), label in init_nodes.items():
    if stage not in stage_node_names: stage_node_names[stage] = []
    if label not in stage_node_names[stage] and label != "":
        stage_node_names[stage].append(label)

for s in ["S1", "S1.5", "S2", "S2.5", "S3", "S3.5", "S4", "S4.5", "S5"]:
    if s not in stage_node_names: stage_node_names[s] = []


# === 【新增代码区】动态生成多选框初始列表的函数 ===
# === 【修改代码区】动态生成多选框初始列表的函数 ===
def get_sorted_stage_nodes(stage, sort_mode):
    names = stage_node_names.get(stage, [])
    if not names: return []

    # 1. 将名字映射到本阶段该国的总流量大小 (用于按数量排序)
    name_vals = {}
    for k, name in init_nodes.items():
        if k[0] == stage:
            name_vals[name] = name_vals.get(name, 0) + node_sizes.get(k, 0)

    # 2. 区分正常节点和特殊节点
    # (排除 NCM/NCA/LFP 这三个挂在特殊字典里的材料种类，它们应参与正常情况排序)
    REAL_SPECIALS = ['NBCP', 'NCPC', 'NTRM', 'MRMT', 'URMS', 'UARP', 'TTCR', 'TFCR', 'TFCM']
    normals = [n for n in names if n not in REAL_SPECIALS]
    specials = [n for n in names if n in REAL_SPECIALS]

    # 3. 排序正常节点 (Normal Nodes)
    if sort_mode == "Quantity":
        sorted_normals = sorted(normals, key=lambda x: name_vals.get(x, 0), reverse=True)
    else:  # Default
        if stage == "S5":
            if s5_mode == "By Chemistry Type":
                # NCA(902), NCM(901), LFP(903) 优先
                chem_order = [get_node_name(902, id_map), get_node_name(901, id_map), get_node_name(903, id_map)]
                ordered = [c for c in chem_order if c in normals]
                leftovers = [n for n in normals if n not in chem_order]
                sorted_normals = ordered + sorted(leftovers, key=lambda x: name_vals.get(x, 0), reverse=True)
            else:
                sorted_normals = sorted(normals, key=lambda x: name_vals.get(x, 0), reverse=True)
        else:
            # S1~S4 正常情况
            default_ids = DEFAULT_ORDERS.get(sel_metal, {}).get(stage, [])
            default_names = [get_node_name(i, id_map) for i in default_ids]

            ordered = [n for n in default_names if n in normals]
            leftovers = [n for n in normals if n not in ordered]
            sorted_normals = ordered + sorted(leftovers, key=lambda x: name_vals.get(x, 0), reverse=True)

    # 4. 排序特殊节点 (Special Nodes)
    # 首先将所有特殊节点按大小进行降序排序
    sorted_specials = sorted(specials, key=lambda x: name_vals.get(x, 0), reverse=True)

    top_specials = []
    bottom_specials = []

    # 5. 定义哪些特殊节点需要强行【置顶】
    top_set = set()

    if stage == "S5":
        top_set.add("NBCP")

    if sel_metal == "Li":
        if stage == "S2": top_set.add("TTCR")
        if stage == "S2.5": top_set.update(["UARP", "NTRM"])
        if stage == "S3": top_set.add("TFCR")
    elif sel_metal == "Ni":
        if stage == "S1": top_set.update(["TFCM", "URMS"])
        if stage == "S2.5": top_set.update(["NTRM", "UARP"])
    elif sel_metal == "Co":
        if stage == "S1": top_set.add("MRMT")
        if stage == "S2.5": top_set.update(["NTRM", "UARP"])
    elif sel_metal == "Mn":
        if stage == "S2.5": top_set.update(["NTRM", "UARP"])

    # 遍历排序好的特殊节点进行分流
    for s in sorted_specials:
        if s in top_set:
            top_specials.append(s)
        else:
            # 根据逻辑：未提及的、或明确要求放最下面的，都放入底部列表
            bottom_specials.append(s)

    # 6. 组合最终列表: 置顶特殊项 + 排序好的正常项 + 置底特殊项
    return top_specials + sorted_normals + bottom_specials


# =======================================================

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
        cols = st.columns(len(stages_to_show))
        for idx, s in enumerate(stages_to_show):
            with cols[idx]:
                if s in stage_node_names and stage_node_names[s]:
                    if len(stages_to_show) > 1:
                        st.caption(f"{s}")

                    # 1. 放置一个单选按钮，决定当前列的排序预设 (Default/Quantity)
                    sort_mode = st.radio(
                        f"Sort {s}",
                        ["Default", "Quantity"],
                        key=f"radio_{s}",
                        horizontal=True,
                        label_visibility="collapsed"
                    )

                    # 2. 根据用户的选择，调用函数获取建议的排列数组
                    suggested_order = get_sorted_stage_nodes(s, sort_mode)

                    # 3. 渲染拖拽框 (使用动态的 default 参数，仍保留手动拖拽调整功能)
                    user_sort[s] = st.multiselect(
                        f"Order: {s}",
                        stage_node_names[s],
                        default=suggested_order,
                        label_visibility="collapsed"
                    )


    # ==========================================
    # 第一部分：Mining (S1)
    # ==========================================
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("### S1: Mining Production")
    with col2:
        s1_file = st.file_uploader("Upload S1", type=["xlsx"], key="s1_up", label_visibility="collapsed")

    if s1_file is not None:
        m_custom = pd.read_excel(s1_file)
        # 仅替换 Mining 数据，重新生成字典
        s1_d, _, _, _ = get_production_dicts(sel_metal, sel_year, m_custom, r_raw, c_raw)

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
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("### S3: Refining Production")
    with col2:
        s2_file = st.file_uploader("Upload S2", type=["xlsx"], key="s2_up", label_visibility="collapsed")

    if s2_file is not None:
        r_custom = pd.read_excel(s2_file)
        # 仅替换 Refining 数据，重新生成字典
        _, s2_d, _, _ = get_production_dicts(sel_metal, sel_year, m_raw, r_custom, c_raw)

    s2_final = editor_widget(s2_d, "s2")

    with st.expander("Adjust Order (S3)", expanded=True):
        render_sort_widgets(["S3", "S3.5"])
    with st.expander("Adjust Order (S4: 2nd post-trade)", expanded=True):
        render_sort_widgets(["S4", "S4.5"])

    st.divider()

    # ==========================================
    # 第三部分：Manufacturing (S3)
    # ==========================================
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("### S5: Cathode & Electrolyte Manufacturing")
    with col2:
        s3_file = st.file_uploader("Upload S3", type=["xlsx"], key="s3_up", label_visibility="collapsed")

    if s3_file is not None:
        c_custom = pd.read_excel(s3_file)
        # 仅替换 Cathode 数据，并更新分类占比 (breakdown)
        _, _, s3_d, s3_breakdown = get_production_dicts(sel_metal, sel_year, m_raw, r_raw, c_custom)

    # 根据侧边栏选择的模式展示不同的表格
    if s5_mode == "By Country":
        # 模式1：只展示总量
        s3_final = editor_widget(s3_d, "s5")
        s3_breakdown_final = s3_breakdown  # 原封不动保留原始拆分比例
    else:
        # 模式2：展示 NCM, NCA, LFP 的分类产量
        chem_data = []
        for k in s3_d.keys():
            # 获取后台读取的原始分类数据，如果没有默认为 0
            b = s3_breakdown.get(k, {'NCM': 0.0, 'NCA': 0.0, 'LFP': 0.0})
            chem_data.append({
                "ID": k,
                "Name": get_node_name(k, id_map),
                "NCM": b.get('NCM', 0.0),
                "NCA": b.get('NCA', 0.0),
                "LFP": b.get('LFP', 0.0)
            })

        # 渲染含有分类列的新表格
        df_chem = st.data_editor(pd.DataFrame(chem_data), key="edit_s3_chem", num_rows="dynamic", hide_index=True,
                                 use_container_width=True)

        s3_final = {}
        s3_breakdown_final = {}
        # 重新打包用户编辑后的数据
        for _, row in df_chem.iterrows():
            cid = row["ID"]
            # 读取编辑后的值
            ncm, nca, lfp = row.get("NCM", 0.0), row.get("NCA", 0.0), row.get("LFP", 0.0)

            # 更新拆分字典
            s3_breakdown_final[cid] = {'NCM': ncm, 'NCA': nca, 'LFP': lfp}
            # S3 节点的总产量等于这三个材料之和
            s3_final[cid] = ncm + nca + lfp
    with st.expander("Adjust Order (S5)", expanded=True):
        render_sort_widgets(["S5"])

with tab2:
    if st.button("Generate Sankey"):
        # 1. Run Algo
        nodes, links, stage_flows = run_sankey_algorithm(s1_final, s2_final, s3_final, t1_df, t2_df, id_map,
                                                         special_stages, s3_breakdown_final, s5_mode, calc_mass_balance)
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