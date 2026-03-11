import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from modules.config import get_color, hex_to_rgba, DEFAULT_ORDERS
from modules.data_loader import (
    load_reference,
    load_raw_production,
    get_production_dicts,
    load_trade_flows,
)
from modules.sankey_algo import (
    run_sankey_algorithm,
    calculate_explicit_positions,
    get_node_name,
)

from streamlit_theme import st_theme
from streamlit_sortables import sort_items


# ==================== 页面基础设置 ====================
st.set_page_config(page_title="Sankey Flow Generator", layout="wide")
st.title("🔋 Critical Mineral Flows Visualizer")

theme = st_theme(key="app_theme", adjust=False)

YEARS = [2020, 2021, 2022, 2023, 2024]
REAL_SPECIALS = ["NBCP", "NCPC", "NTRM", "MRMT", "URMS", "UARP", "TTCR", "TFCR", "TFCM"]
MAIN_STAGES = ["S1", "S2", "S3", "S4", "S5"]
ALL_STAGES = ["S1", "S1.5", "S2", "S2.5", "S3", "S3.5", "S4", "S4.5", "S5"]

# ==================== Session State 初始化 ====================
if "editor_year" not in st.session_state:
    st.session_state.editor_year = 2020

if "diagram_year" not in st.session_state:
    st.session_state.diagram_year = 2020

if "generated_figs_by_year" not in st.session_state:
    st.session_state.generated_figs_by_year = None

if "diagram_generated" not in st.session_state:
    st.session_state.diagram_generated = False

if "diagram_generated_note" not in st.session_state:
    st.session_state.diagram_generated_note = ""

# 按 context 分桶保存，避免不同 metal/source 互相污染
if "year_override_s1_store" not in st.session_state:
    st.session_state.year_override_s1_store = {}

if "year_override_s2_store" not in st.session_state:
    st.session_state.year_override_s2_store = {}

if "year_override_s3_store" not in st.session_state:
    st.session_state.year_override_s3_store = {}

if "year_override_s3_breakdown_store" not in st.session_state:
    st.session_state.year_override_s3_breakdown_store = {}

if "custom_default_orders_store" not in st.session_state:
    st.session_state.custom_default_orders_store = {}


# ==================== 工具函数 ====================
def read_uploaded_excel(uploaded_file):
    if uploaded_file is None:
        return None
    uploaded_file.seek(0)
    return pd.read_excel(uploaded_file)


def choose_df(upload_key, fallback_df):
    uploaded = st.session_state.get(upload_key)
    uploaded_df = read_uploaded_excel(uploaded)
    return uploaded_df if uploaded_df is not None else fallback_df


def get_theme_text_color(theme_obj):
    theme_base = ""
    if theme_obj and isinstance(theme_obj, dict):
        theme_base = str(theme_obj.get("base", "")).strip().lower()
    return "#FFFFFF" if theme_base == "dark" else "#000000"


def aggregate_links(links):
    agg_links = {}
    for l in links:
        k = (l["source"], l["target"])
        if k not in agg_links:
            agg_links[k] = {
                "value": 0,
                "c_code": l.get("color_code"),
                "c_id": l.get("color_id"),
            }
        agg_links[k]["value"] += l["value"]

        if l.get("color_code"):
            agg_links[k]["c_code"] = l["color_code"]
        if l.get("color_id") and not agg_links[k]["c_id"]:
            agg_links[k]["c_id"] = l["color_id"]

    final_links = []
    for (s, t), d in agg_links.items():
        final_links.append(
            {
                "source": s,
                "target": t,
                "value": d["value"],
                "color_code": d["c_code"],
                "color_id": d["c_id"],
            }
        )
    return final_links


def add_reference_flow(nodes, links, ref_qty_value):
    if ref_qty_value <= 0:
        return nodes, links

    rk1, rk2, rk3, rk4, rk5 = ("REF_S1", 0), ("REF_S2", 0), ("REF_S3", 0), ("REF_S4", 0), ("REF_S5", 0)
    nodes[rk1], nodes[rk2], nodes[rk3], nodes[rk4] = "", "", "", ""
    nodes[rk5] = f"{ref_qty_value:,.0f} t"

    trans = "rgba(0,0,0,0)"
    for s, t in [(rk1, rk2), (rk2, rk3), (rk3, rk4), (rk4, rk5)]:
        links.append({"source": s, "target": t, "value": ref_qty_value, "color_code": trans})

    return nodes, links


def compute_node_values(nodes, links):
    node_ins, node_outs = {}, {}
    for l in links:
        t, s, v = l["target"], l["source"], l["value"]
        node_ins[t] = node_ins.get(t, 0) + v
        node_outs[s] = node_outs.get(s, 0) + v

    node_values = {}
    for n in nodes.keys():
        node_values[n] = max(node_ins.get(n, 0), node_outs.get(n, 0))
    return node_values


def get_top_special_set(stage, metal):
    top_set = set()

    if stage == "S5":
        top_set.add("NBCP")

    if metal == "Li":
        if stage == "S2":
            top_set.add("TTCR")
        if stage == "S2.5":
            top_set.update(["UARP", "NTRM"])
        if stage == "S3":
            top_set.add("TFCR")
    elif metal == "Ni":
        if stage == "S1":
            top_set.update(["TFCM", "URMS"])
        if stage == "S2.5":
            top_set.update(["NTRM", "UARP"])
    elif metal == "Co":
        if stage == "S1":
            top_set.add("MRMT")
        if stage == "S2.5":
            top_set.update(["NTRM", "UARP"])
    elif metal == "Mn":
        if stage == "S2.5":
            top_set.update(["NTRM", "UARP"])

    return top_set


def build_initial_default_order(stage, normal_names, stage_name_values, sel_metal_value, s5_mode_value, id_map_local):
    if not normal_names:
        return []

    if stage == "S5" and s5_mode_value == "By Chemistry Type":
        chem_order = [get_node_name(902, id_map_local), get_node_name(901, id_map_local), get_node_name(903, id_map_local)]
        ordered = [n for n in chem_order if n in normal_names]
        leftovers = [n for n in normal_names if n not in ordered]
        leftovers = sorted(leftovers, key=lambda x: stage_name_values.get(x, 0), reverse=True)
        return ordered + leftovers

    if stage in ["S1", "S2", "S3", "S4"]:
        default_ids = DEFAULT_ORDERS.get(sel_metal_value, {}).get(stage, [])
        default_names = [get_node_name(i, id_map_local) for i in default_ids]
        ordered = [n for n in default_names if n in normal_names]
        leftovers = [n for n in normal_names if n not in ordered]
        leftovers = sorted(leftovers, key=lambda x: stage_name_values.get(x, 0), reverse=True)
        return ordered + leftovers

    return sorted(normal_names, key=lambda x: stage_name_values.get(x, 0), reverse=True)


def sync_custom_default_order(stage, normal_names, stage_name_values, sel_metal_value, s5_mode_value, id_map_local, custom_orders_bucket):
    current = custom_orders_bucket.get(stage, [])

    if not current:
        custom_orders_bucket[stage] = build_initial_default_order(
            stage, normal_names, stage_name_values, sel_metal_value, s5_mode_value, id_map_local
        )
        return

    current_filtered = [n for n in current if n in normal_names]
    new_items = [n for n in normal_names if n not in current_filtered]
    new_items = sorted(new_items, key=lambda x: stage_name_values.get(x, 0), reverse=True)

    custom_orders_bucket[stage] = current_filtered + new_items


def scale_breakdown_to_totals(total_dict, base_breakdown):
    scaled = {}
    for cid, total in total_dict.items():
        b = base_breakdown.get(cid, {"NCM": 0.0, "NCA": 0.0, "LFP": 0.0})
        base_sum = float(b.get("NCM", 0.0) + b.get("NCA", 0.0) + b.get("LFP", 0.0))

        if base_sum > 0:
            ratio = float(total) / base_sum
            scaled[cid] = {
                "NCM": float(b.get("NCM", 0.0)) * ratio,
                "NCA": float(b.get("NCA", 0.0)) * ratio,
                "LFP": float(b.get("LFP", 0.0)) * ratio,
            }
        else:
            scaled[cid] = {
                "NCM": float(total),
                "NCA": 0.0,
                "LFP": 0.0,
            }
    return scaled


def editor_widget(prod_dict, key, id_map_local):
    data = [{"ID": k, "Name": get_node_name(k, id_map_local), "Quantity": v} for k, v in prod_dict.items()]
    df = st.data_editor(
        pd.DataFrame(data),
        key=key,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
    )
    return dict(zip(df["ID"], df["Quantity"]))


def build_chem_editor_df(s3_prod_dict, s3_breakdown_dict, id_map_local):
    chem_data = []
    for k in s3_prod_dict.keys():
        b = s3_breakdown_dict.get(k, {"NCM": 0.0, "NCA": 0.0, "LFP": 0.0})
        chem_data.append(
            {
                "ID": k,
                "Name": get_node_name(k, id_map_local),
                "NCM": b.get("NCM", 0.0),
                "NCA": b.get("NCA", 0.0),
                "LFP": b.get("LFP", 0.0),
            }
        )
    return pd.DataFrame(chem_data)


def freeze_nested_dict(obj):
    """把嵌套 dict/list 转成可稳定 hash 的结构，供 st.cache_data 使用。"""
    if isinstance(obj, dict):
        return ("__dict__", tuple((k, freeze_nested_dict(v)) for k, v in sorted(obj.items(), key=lambda x: str(x[0]))))
    if isinstance(obj, list):
        return ("__list__", tuple(freeze_nested_dict(v) for v in obj))
    return obj


def unfreeze_nested_dict(obj):
    if not isinstance(obj, tuple) or len(obj) != 2:
        return obj

    tag, payload = obj
    if tag == "__dict__":
        return {k: unfreeze_nested_dict(v) for k, v in payload}
    if tag == "__list__":
        return [unfreeze_nested_dict(v) for v in payload]
    return obj


# ==================== 侧边栏：1. General Settings ====================
with st.sidebar:
    st.header("1. General Settings")

    sel_metal = st.selectbox("Metal", ["Li", "Co", "Ni", "Mn"], index=0)

    trade_mode_label = st.radio("Trade Data Source", ["Import", "Export"], index=0)
    trade_mode = trade_mode_label.lower()

    st.caption("Choose production data source for each production stage")
    s1_source_label = st.selectbox("S1 Production Source (Mining)", ["Country", "Ownership"], index=0)
    s3_source_label = st.selectbox("S3 Production Source (Refining)", ["Country", "Ownership"], index=0)
    s5_source_label = st.selectbox("S5 Production Source (Cathode)", ["Country", "Ownership"], index=0)

    s1_source = s1_source_label.lower()
    s3_source = s3_source_label.lower()
    s5_source = s5_source_label.lower()

    ref_qty = st.number_input("Ref Qty (t)", value=20000, step=1000)

    s5_mode = st.radio("Final Stage Output Mode", ["By Country", "By Chemistry Type"])

    calc_mass_balance = (
        st.radio("Mass Balance Option", ["No (Default)", "Yes (Split Gap)"], index=0) == "Yes (Split Gap)"
    )

    st.divider()
    st.header("2. Layout Config")

    st.caption("Global order strategy for 2020–2024")
    sort_mode_by_stage = {
        "S1": st.selectbox("S1 Order Mode", ["Default", "Quantity"], index=0),
        "S2": st.selectbox("S2 Order Mode", ["Default", "Quantity"], index=0),
        "S3": st.selectbox("S3 Order Mode", ["Default", "Quantity"], index=0),
        "S4": st.selectbox("S4 Order Mode", ["Default", "Quantity"], index=0),
        "S5": st.selectbox("S5 Order Mode", ["Default", "Quantity"], index=0),
    }

    st.caption("Customize intermediate stages")
    with st.expander("Open Intermediate Configuration", expanded=False):
        special_stages = {}
        alignments = {}

        def config_node(node_name, default_stage, inter_stage):
            opt = st.selectbox(
                f"{node_name}",
                [default_stage, inter_stage],
                key=f"cfg_{node_name}",
            )
            special_stages[node_name] = opt

        st.markdown("**Mining Stage**")
        config_node("TFCM", "S1", "S1.5")
        config_node("TTCR", "S2", "S1.5")
        config_node("URMS", "S1", "S1.5")
        alignments["S1.5"] = st.radio("Align S1.5", ["Top", "Bottom"], index=0, horizontal=True, key="align_s15")

        st.markdown("---")
        st.markdown("**Refining Stage**")
        config_node("UARP", "S2", "S2.5")
        config_node("NTRM", "S3", "S2.5")
        alignments["S2.5"] = st.radio("Align S2.5", ["Top", "Bottom"], index=0, horizontal=True, key="align_s25")

        st.markdown("---")
        st.markdown("**Manuf. Input**")
        config_node("TFCR", "S3", "S3.5")
        config_node("MRMT", "S3", "S3.5")
        config_node("NCPC", "S4", "S3.5")
        alignments["S3.5"] = st.radio("Align S3.5", ["Top", "Bottom"], index=0, horizontal=True, key="align_s35")

        st.markdown("---")
        st.markdown("**Manuf. Output**")
        config_node("NBCP", "S5", "S4.5")
        alignments["S4.5"] = st.radio("Align S4.5", ["Top", "Bottom"], index=0, horizontal=True, key="align_s45")

    st.divider()
    st.header("3. Reference & Helpers")

# ==================== 当前 context key ====================
context_key = f"{sel_metal}|{trade_mode}|{s1_source}|{s3_source}|{s5_source}|{s5_mode}|{calc_mass_balance}"

override_s1_bucket = st.session_state.year_override_s1_store.setdefault(context_key, {})
override_s2_bucket = st.session_state.year_override_s2_store.setdefault(context_key, {})
override_s3_bucket = st.session_state.year_override_s3_store.setdefault(context_key, {})
override_s3_breakdown_bucket = st.session_state.year_override_s3_breakdown_store.setdefault(context_key, {})
custom_default_orders_bucket = st.session_state.custom_default_orders_store.setdefault(context_key, {})

# ==================== 公共数据加载 ====================
id_map, ref_df = load_reference()

# 基础生产数据：country / ownership 各读一套
country_m_raw, country_r_raw, country_c_raw = load_raw_production(
    s1_source="country", s3_source="country", s5_source="country"
)
ownership_m_raw, ownership_r_raw, ownership_c_raw = load_raw_production(
    s1_source="ownership", s3_source="ownership", s5_source="ownership"
)

# 如果用户在“Global Order & Uploads”页上传了文件，则全局覆盖对应 level-stage 的源表
country_m_df = choose_df("upload_country_s1", country_m_raw)
country_r_df = choose_df("upload_country_s3", country_r_raw)
country_c_df = choose_df("upload_country_s5", country_c_raw)

ownership_m_df = choose_df("upload_ownership_s1", ownership_m_raw)
ownership_r_df = choose_df("upload_ownership_s3", ownership_r_raw)
ownership_c_df = choose_df("upload_ownership_s5", ownership_c_raw)

# 根据 sidebar 当前选择的 source，确定当前图和编辑器使用的“有效生产表”
m_effective = country_m_df if s1_source == "country" else ownership_m_df
r_effective = country_r_df if s3_source == "country" else ownership_r_df
c_effective = country_c_df if s5_source == "country" else ownership_c_df


def get_year_stage_data(year):
    s1_base, s2_base, s3_base, s3_breakdown_base = get_production_dicts(
        sel_metal, year, m_effective, r_effective, c_effective
    )

    s1_final = dict(override_s1_bucket.get(year, s1_base))
    s2_final = dict(override_s2_bucket.get(year, s2_base))

    if year in override_s3_breakdown_bucket:
        s3_breakdown_final = dict(override_s3_breakdown_bucket[year])
        s3_final = {
            cid: v.get("NCM", 0.0) + v.get("NCA", 0.0) + v.get("LFP", 0.0)
            for cid, v in s3_breakdown_final.items()
        }
    elif year in override_s3_bucket:
        s3_final = dict(override_s3_bucket[year])
        s3_breakdown_final = scale_breakdown_to_totals(s3_final, s3_breakdown_base)
    else:
        s3_final = s3_base
        s3_breakdown_final = s3_breakdown_base

    return s1_final, s2_final, s3_final, s3_breakdown_final


@st.cache_data(show_spinner=False)
def build_global_stage_stats_cached(
    sel_metal_value,
    trade_mode_value,
    s5_mode_value,
    calc_mass_balance_value,
    special_stages_frozen,
    m_effective_df,
    r_effective_df,
    c_effective_df,
    year_override_s1_frozen,
    year_override_s2_frozen,
    year_override_s3_frozen,
    year_override_s3_breakdown_frozen,
    id_map_frozen,
):
    special_stages_local = unfreeze_nested_dict(special_stages_frozen)
    override_s1_local = unfreeze_nested_dict(year_override_s1_frozen)
    override_s2_local = unfreeze_nested_dict(year_override_s2_frozen)
    override_s3_local = unfreeze_nested_dict(year_override_s3_frozen)
    override_s3_breakdown_local = unfreeze_nested_dict(year_override_s3_breakdown_frozen)
    id_map_local = unfreeze_nested_dict(id_map_frozen)

    def get_year_stage_data_local(year):
        s1_base, s2_base, s3_base, s3_breakdown_base = get_production_dicts(
            sel_metal_value, year, m_effective_df, r_effective_df, c_effective_df
        )

        s1_final = dict(override_s1_local.get(year, s1_base))
        s2_final = dict(override_s2_local.get(year, s2_base))

        if year in override_s3_breakdown_local:
            s3_breakdown_final = dict(override_s3_breakdown_local[year])
            s3_final = {
                cid: v.get("NCM", 0.0) + v.get("NCA", 0.0) + v.get("LFP", 0.0)
                for cid, v in s3_breakdown_final.items()
            }
        elif year in override_s3_local:
            s3_final = dict(override_s3_local[year])
            s3_breakdown_final = scale_breakdown_to_totals(s3_final, s3_breakdown_base)
        else:
            s3_final = s3_base
            s3_breakdown_final = s3_breakdown_base

        return s1_final, s2_final, s3_final, s3_breakdown_final

    agg_stage_names = {s: set() for s in ALL_STAGES}
    agg_stage_values = {s: {} for s in ALL_STAGES}

    for year in YEARS:
        s1_y, s2_y, s3_y, s3_breakdown_y = get_year_stage_data_local(year)
        t1_y = load_trade_flows("1st_post_trade", sel_metal_value, year, trade_mode_value)
        t2_y = load_trade_flows("2nd_post_trade", sel_metal_value, year, trade_mode_value)

        nodes, links, _ = run_sankey_algorithm(
            s1_y,
            s2_y,
            s3_y,
            t1_y,
            t2_y,
            id_map_local,
            special_stages_local,
            s3_breakdown_y,
            s5_mode_value,
            calc_mass_balance_value,
        )

        node_values = compute_node_values(nodes, links)

        for node_key, label in nodes.items():
            if label == "":
                continue
            stage = node_key[0]
            agg_stage_names.setdefault(stage, set()).add(label)
            agg_stage_values.setdefault(stage, {})
            agg_stage_values[stage][label] = (
                agg_stage_values[stage].get(label, 0) + node_values.get(node_key, 0)
            )

    agg_stage_names = {k: sorted(list(v)) for k, v in agg_stage_names.items()}
    return agg_stage_names, agg_stage_values


with st.spinner("Preparing global ordering data for 2020–2024..."):
    agg_stage_names, agg_stage_values = build_global_stage_stats_cached(
        sel_metal,
        trade_mode,
        s5_mode,
        calc_mass_balance,
        freeze_nested_dict(special_stages),
        m_effective,
        r_effective,
        c_effective,
        freeze_nested_dict(override_s1_bucket),
        freeze_nested_dict(override_s2_bucket),
        freeze_nested_dict(override_s3_bucket),
        freeze_nested_dict(override_s3_breakdown_bucket),
        freeze_nested_dict(id_map),
    )

# 同步 custom default order（只针对主阶段 S1~S5 的正常节点）
for stage in MAIN_STAGES:
    normal_names = [n for n in agg_stage_names.get(stage, []) if n not in REAL_SPECIALS]
    stage_name_values = agg_stage_values.get(stage, {})
    sync_custom_default_order(stage, normal_names, stage_name_values, sel_metal, s5_mode, id_map, custom_default_orders_bucket)


def compose_stage_order(stage):
    names = agg_stage_names.get(stage, [])
    stage_values = agg_stage_values.get(stage, {})

    if not names:
        return []

    normals = [n for n in names if n not in REAL_SPECIALS]
    specials = [n for n in names if n in REAL_SPECIALS]

    if stage in MAIN_STAGES:
        sort_mode = sort_mode_by_stage.get(stage, "Default")
    else:
        sort_mode = "Quantity"

    if stage in MAIN_STAGES and sort_mode == "Default":
        preferred = custom_default_orders_bucket.get(stage, [])
        ordered = [n for n in preferred if n in normals]
        leftovers = [n for n in normals if n not in ordered]
        leftovers = sorted(leftovers, key=lambda x: stage_values.get(x, 0), reverse=True)
        sorted_normals = ordered + leftovers
    else:
        sorted_normals = sorted(normals, key=lambda x: stage_values.get(x, 0), reverse=True)

    sorted_specials = sorted(specials, key=lambda x: stage_values.get(x, 0), reverse=True)
    top_set = get_top_special_set(stage, sel_metal)

    top_specials = [s for s in sorted_specials if s in top_set]
    bottom_specials = [s for s in sorted_specials if s not in top_set]

    return top_specials + sorted_normals + bottom_specials


user_sort = {stage: compose_stage_order(stage) for stage in ALL_STAGES}

# ==================== Sidebar Helpers ====================
with st.sidebar:
    st.caption("Find country ID by name")
    search = st.text_input("Search Country", label_visibility="collapsed", placeholder="Type country name...")
    if search:
        res = ref_df[ref_df["text"].str.contains(search, case=False, na=False)]
        st.dataframe(res, hide_index=True, width="stretch")

    st.caption("View special acronym definitions")
    with st.expander("Show Legend"):
        st.markdown(
            """
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
            """,
            unsafe_allow_html=True,
        )


def build_sankey_figure_for_year(year):
    s1_y, s2_y, s3_y, s3_breakdown_y = get_year_stage_data(year)
    t1_y = load_trade_flows("1st_post_trade", sel_metal, year, trade_mode)
    t2_y = load_trade_flows("2nd_post_trade", sel_metal, year, trade_mode)

    nodes, links, stage_flows = run_sankey_algorithm(
        s1_y,
        s2_y,
        s3_y,
        t1_y,
        t2_y,
        id_map,
        special_stages,
        s3_breakdown_y,
        s5_mode,
        calc_mass_balance,
    )

    nodes, links = add_reference_flow(nodes, links, ref_qty)
    final_links = aggregate_links(links)

    sorted_keys, nx, ny = calculate_explicit_positions(
        nodes,
        final_links,
        user_sort,
        stage_flows,
        alignments,
        ref_qty,
    )

    node_map = {k: i for i, k in enumerate(sorted_keys)}
    node_lbl = [nodes[k] for k in sorted_keys]
    node_clr = [
        "#888888"
        if str(k[0]).startswith("REF_S5")
        else ("rgba(0,0,0,0)" if str(k[0]).startswith("REF_") else get_color(k[1]))
        for k in sorted_keys
    ]

    lnk_src = [node_map[l["source"]] for l in final_links]
    lnk_tgt = [node_map[l["target"]] for l in final_links]
    lnk_val = [l["value"] for l in final_links]

    lnk_clr = []
    for l in final_links:
        if l.get("color_code"):
            lnk_clr.append(l["color_code"])
        else:
            cid = l.get("color_id")
            if cid is None:
                cid = 0
            lnk_clr.append(hex_to_rgba(get_color(cid), 0.4))

    theme_text_color = get_theme_text_color(theme)

    fig = go.Figure(
        go.Sankey(
            arrangement="fixed",
            textfont=dict(
                color=theme_text_color,
                size=13,
                shadow="none",
            ),
            node=dict(
                pad=15,
                thickness=20,
                line=dict(color="rgba(0,0,0,0)", width=0),
                label=node_lbl,
                color=node_clr,
                x=nx,
                y=ny,
            ),
            link=dict(
                source=lnk_src,
                target=lnk_tgt,
                value=lnk_val,
                color=lnk_clr,
            ),
        )
    )

    max_f = max(stage_flows.values()) if stage_flows else 0
    h = (max_f / ref_qty * 50 + 200) if (ref_qty > 0 and max_f > 0) else 800

    fig.update_layout(
        height=max(600, int(h)),
        title_text=f"{sel_metal} {year}",
        font=dict(color=theme_text_color),
        title_font=dict(color=theme_text_color),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )

    return fig


# ==================== 主界面 ====================
tab_diagram, tab_editor, tab_global = st.tabs(
    ["📊 Diagram", "⚙️ Year Editor", "🗂️ Global Order & Uploads"]
)

# ---------- Diagram ----------
with tab_diagram:
    st.markdown("### Generate Diagram")

    view_year = st.slider(
        "Drag to view year",
        min_value=2020,
        max_value=2024,
        value=st.session_state.diagram_year,
        step=1,
        key="diagram_year",
    )

    if st.button("Generate / Regenerate Sankey", key="generate_sankey_btn", type="primary"):
        with st.spinner("Generating Sankey diagrams for 2020–2024..."):
            st.session_state.generated_figs_by_year = {
                year: build_sankey_figure_for_year(year) for year in YEARS
            }
            st.session_state.diagram_generated = True
            st.session_state.diagram_generated_note = (
                "Generated using the current settings. "
                "Any later edits will not change the diagram until you click Generate / Regenerate Sankey again."
            )

    if st.session_state.diagram_generated and st.session_state.generated_figs_by_year:
        st.caption(st.session_state.diagram_generated_note)
        st.plotly_chart(
            st.session_state.generated_figs_by_year[view_year],
            width="stretch"
        )
    else:
        st.info("Click 'Generate / Regenerate Sankey' to build and cache the 2020–2024 diagrams.")


# ---------- Year Editor ----------
with tab_editor:
    st.markdown("### Editor / Order Base Year")
    editor_year = st.selectbox("Editor / Order Base Year", YEARS, key="editor_year")

    st.caption(
        f"Current production source selection — S1: {s1_source.title()}, "
        f"S3: {s3_source.title()}, S5: {s5_source.title()}"
    )

    s1_edit, s2_edit, s3_edit, s3_breakdown_edit = get_year_stage_data(editor_year)

    st.markdown("### S1: Mining Production")
    s1_final = editor_widget(s1_edit, f"edit_s1_{context_key}_{editor_year}", id_map)
    override_s1_bucket[editor_year] = s1_final

    st.divider()

    st.markdown("### S3: Refining Production")
    s2_final = editor_widget(s2_edit, f"edit_s2_{context_key}_{editor_year}", id_map)
    override_s2_bucket[editor_year] = s2_final

    st.divider()

    st.markdown("### S5: Cathode & Electrolyte Manufacturing")

    if s5_mode == "By Country":
        s3_final = editor_widget(s3_edit, f"edit_s3_{context_key}_{editor_year}", id_map)
        override_s3_bucket[editor_year] = s3_final
        if editor_year in override_s3_breakdown_bucket:
            del override_s3_breakdown_bucket[editor_year]
    else:
        df_chem = st.data_editor(
            build_chem_editor_df(s3_edit, s3_breakdown_edit, id_map),
            key=f"edit_s3_chem_{context_key}_{editor_year}",
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
        )

        s3_final = {}
        s3_breakdown_final = {}
        for _, row in df_chem.iterrows():
            cid = row["ID"]
            ncm = float(row.get("NCM", 0.0))
            nca = float(row.get("NCA", 0.0))
            lfp = float(row.get("LFP", 0.0))

            s3_breakdown_final[cid] = {"NCM": ncm, "NCA": nca, "LFP": lfp}
            s3_final[cid] = ncm + nca + lfp

        override_s3_bucket[editor_year] = s3_final
        override_s3_breakdown_bucket[editor_year] = s3_breakdown_final


# ---------- Global Order & Uploads ----------
with tab_global:
    st.markdown("### Global Default Order (S1–S5)")
    st.caption("Drag to reorder the global default order. These orders affect 2020–2024 whenever the stage order mode is set to Default.")

    order_cols = st.columns(2)
    stage_groups = [["S1", "S2", "S3"], ["S4", "S5"]]

    for col, stages in zip(order_cols, stage_groups):
        with col:
            for stage in stages:
                normal_names = [n for n in agg_stage_names.get(stage, []) if n not in REAL_SPECIALS]
                if not normal_names:
                    st.info(f"{stage}: no nodes available")
                    continue

                st.markdown(f"**{stage}**")

                current_order = custom_default_orders_bucket.get(stage, normal_names)
                current_order = [n for n in current_order if n in normal_names]
                missing_items = [n for n in normal_names if n not in current_order]
                current_order = current_order + missing_items

                sorted_items = sort_items(
                    current_order,
                    key=f"sortable_{context_key}_{stage}",
                )

                custom_default_orders_bucket[stage] = sorted_items

    st.divider()
    st.markdown("### Global Production File Uploads")
    st.caption("Upload source files by level. The selected Country / Ownership source in the sidebar determines which one is used.")

    col_country, col_ownership = st.columns(2)

    with col_country:
        st.markdown("#### Country-level")
        st.file_uploader(
            "Upload Country-level S1 (Mining)",
            type=["xlsx"],
            key="upload_country_s1",
        )
        st.file_uploader(
            "Upload Country-level S3 (Refining)",
            type=["xlsx"],
            key="upload_country_s3",
        )
        st.file_uploader(
            "Upload Country-level S5 (Cathode)",
            type=["xlsx"],
            key="upload_country_s5",
        )

    with col_ownership:
        st.markdown("#### Ownership-level")
        st.file_uploader(
            "Upload Ownership-level S1 (Mining)",
            type=["xlsx"],
            key="upload_ownership_s1",
        )
        st.file_uploader(
            "Upload Ownership-level S3 (Refining)",
            type=["xlsx"],
            key="upload_ownership_s3",
        )
        st.file_uploader(
            "Upload Ownership-level S5 (Cathode)",
            type=["xlsx"],
            key="upload_ownership_s5",
        )