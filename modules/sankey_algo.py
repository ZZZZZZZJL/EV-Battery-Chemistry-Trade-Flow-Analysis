from .config import SPECIAL_NODES_MAP, get_color, hex_to_rgba


# 辅助函数：获取节点名称
def get_node_name(name_or_id, id_to_name_map):
    # 【新增】识别 _gap 后缀，加上文本注释
    if isinstance(name_or_id, str) and str(name_or_id).endswith("_gap"):
        base_id = int(float(str(name_or_id).split("_")[0]))
        return f"{get_node_name(base_id, id_to_name_map)} (Gap)"

    if name_or_id in SPECIAL_NODES_MAP: return name_or_id
    try:
        cid = int(float(name_or_id))
        for name, sid in SPECIAL_NODES_MAP.items():
            if cid == sid: return name
        return id_to_name_map.get(cid, str(cid))
    except:
        return str(name_or_id)


def balance(prod_dict, trade_df):
    flow_dict = {}
    miss_prod = {}
    for pid, qty in prod_dict.items():
        flow_dict[pid] = {pid: qty}
    if not trade_df.empty:
        for _, row in trade_df.iterrows():
            exporter = row['exporter']
            importer = row['importer']
            val = row['value']
            if exporter not in flow_dict: flow_dict[exporter] = {exporter: 0}
            flow_dict[exporter].setdefault(importer, 0)
            flow_dict[exporter][importer] += val
            flow_dict[exporter][exporter] -= val
    for exp in list(flow_dict.keys()):
        if flow_dict[exp][exp] < 0:
            miss_prod.setdefault(exp, 0)
            miss_prod[exp] -= flow_dict[exp][exp]
            flow_dict[exp][exp] = 0
    return flow_dict, miss_prod


def run_sankey_algorithm(s1_prod, s2_prod, s3_prod, t1_df, t2_df, id_to_name, special_stages, s3_breakdown, s5_mode, calc_mass_balance):
    """
    运行桑基图核心逻辑，生成 Nodes 和 Links
    """
    mrbal, mmiss = balance(s1_prod, t1_df)
    rcbal, rmiss = balance(s2_prod, t2_df)

    links = []
    nodes = {}
    stage_flows = {}

    # 默认阶段定义
    S1, S2, S3, S4, S5 = "S1", "S2", "S3", "S4", "S5"
    S_UARP = "S2"

    def get_stage(node_name, default_stage):
        if node_name in special_stages:
            return special_stages[node_name]
        return default_stage

    def add_link(src_stage, src_id, tgt_stage, tgt_id, val, color_id):
        s_name = get_node_name(src_id, id_to_name)
        if s_name in SPECIAL_NODES_MAP:
            src_stage_actual = get_stage(s_name, src_stage)
        else:
            src_stage_actual = src_stage

        t_name = get_node_name(tgt_id, id_to_name)
        if t_name in SPECIAL_NODES_MAP:
            tgt_stage_actual = get_stage(t_name, tgt_stage)
        else:
            tgt_stage_actual = tgt_stage

        src_key = (src_stage_actual, src_id)
        tgt_key = (tgt_stage_actual, tgt_id)

        nodes[src_key] = s_name
        nodes[tgt_key] = t_name
        links.append({'source': src_key, 'target': tgt_key, 'value': val, 'color_id': color_id})

        stage_flows[src_stage_actual] = stage_flows.get(src_stage_actual, 0) + val
        stage_flows[tgt_stage_actual] = stage_flows.get(tgt_stage_actual, 0) + val

    # --- PART 1: Mining Trade ---
    for exporter, trade in mrbal.items():
        is_miner = (exporter in s1_prod) or (exporter == SPECIAL_NODES_MAP["URMS"])

        # 【新增】计算 Gap 的拆分比例
        gap_ratio = 0.0
        actual_ratio = 1.0
        # 如果开启了 Mass Balance，且该出口国存在亏空 (mmiss 记录了出口>产量的差值)
        if calc_mass_balance and exporter in mmiss and mmiss[exporter] > 0:
            total_export = sum(v for v in trade.values() if v > 1e-9)
            if total_export > 0:
                gap_ratio = mmiss[exporter] / total_export
                actual_ratio = 1.0 - gap_ratio

        for importer, value in trade.items():
            if value <= 1e-9: continue

            if is_miner:
                if importer in s2_prod:
                    tgt_id = importer
                else:
                    tgt_id = SPECIAL_NODES_MAP["TTCR"]

                # 【新增】如果开启了拆分且存在亏空，将一条线拆成两条
                if calc_mass_balance and gap_ratio > 0:
                    val_actual = value * actual_ratio
                    val_gap = value * gap_ratio

                    if val_actual > 0:
                        add_link(S1, exporter, S2, tgt_id, val_actual, exporter)
                    if val_gap > 0:
                        gap_id = f"{exporter}_gap"  # 生成虚拟 ID
                        add_link(S1, gap_id, S2, tgt_id, val_gap, gap_id)
                else:
                    # 默认情况（不拆分）
                    add_link(S1, exporter, S2, tgt_id, value, exporter)
            else:
                tfcm_id = SPECIAL_NODES_MAP["TFCM"]
                if importer in s2_prod:
                    add_link(S1, tfcm_id, S2, importer, value, tfcm_id)

    # --- PART 2: Refining Internal ---
    refindict = {}
    for exporter, trade in mrbal.items():
        for importer, value in trade.items():
            if value > 0:
                refindict.setdefault(importer, 0)
                refindict[importer] += value
    for country, prod in s2_prod.items():
        refin = refindict.get(country, 0)
        diff = refin - prod
        if diff >= 0:
            ntrm_id = SPECIAL_NODES_MAP["NTRM"]
            add_link(S2, country, S3, ntrm_id, diff, country)
        else:
            urms_id = SPECIAL_NODES_MAP["URMS"]
            add_link(S1, urms_id, S2, country, -diff, urms_id)

    # --- PART 4: Refining Prod ---
    for country, prod in s2_prod.items():
        if prod > 0:
            add_link(S2, country, S3, country, prod, country)

    # --- PART 5: Refining Trade ---
    for exporter, trade in rcbal.items():
        is_refiner = (exporter in s2_prod) or (exporter == SPECIAL_NODES_MAP["MRMT"])
        for importer, value in trade.items():
            if value <= 1e-9: continue
            if is_refiner:
                if importer in s3_prod:
                    add_link(S3, exporter, S4, importer, value, exporter)
                else:
                    ncpc_id = SPECIAL_NODES_MAP["NCPC"]
                    add_link(S3, exporter, S4, ncpc_id, value, exporter)
            else:
                tfcr_id = SPECIAL_NODES_MAP["TFCR"]
                if importer in s3_prod:
                    add_link(S3, tfcr_id, S4, importer, value, tfcr_id)

    # --- PART 6: UARP ---
    for importer, value in rmiss.items():
        if importer in s2_prod:
            uarp_id = SPECIAL_NODES_MAP["UARP"]
            add_link(S_UARP, uarp_id, S3, importer, value, uarp_id)

    # --- PART 7: Manufacturing Internal ---
    cathindict = {}
    for exporter, trade in rcbal.items():
        for importer, value in trade.items():
            if value > 0:
                cathindict.setdefault(importer, 0)
                cathindict[importer] += value
    for country, prod in s3_prod.items():
        cathin = cathindict.get(country, 0)
        diff = cathin - prod
        if diff >= 0:
            nbcp_id = SPECIAL_NODES_MAP["NBCP"]
            add_link(S4, country, S5, nbcp_id, diff, country)
        else:
            mrmt_id = SPECIAL_NODES_MAP["MRMT"]
            add_link(S3, mrmt_id, S4, country, -diff, mrmt_id)

    # --- PART 8: Manufacturing Prod ---
    # --- PART 8: Manufacturing Prod ---
    for country, prod in s3_prod.items():
        if prod > 0:
            if s5_mode == "By Chemistry Type" and country in s3_breakdown:
                # 为了兼容在网页 Editor 中手动修改过总产量的情况，根据原始比例分配
                original_total = sum(s3_breakdown[country].values())
                if original_total > 0:
                    ratio = prod / original_total
                    for chem_type, chem_qty in s3_breakdown[country].items():
                        scaled_qty = chem_qty * ratio
                        if scaled_qty > 0:
                            chem_id = SPECIAL_NODES_MAP[chem_type]
                            # 起点为 S4 国家，终点为 S5 种类节点，连线颜色跟随起点国家
                            add_link(S4, country, S5, chem_id, scaled_qty, country)
                    continue  # 种类连线生成完毕，跳过默认的国家连线

            # 默认：按国家输出 (或者遇到了没有拆分数据的手动新增国家)
            add_link(S4, country, S5, country, prod, country)

    return nodes, links, stage_flows


def calculate_explicit_positions(nodes, links, user_sort_order, stage_flows, alignments, ref_qty=None):
    """
    计算显式坐标 (修复重叠版)
    """
    # 1. 计算每个节点的高度权重 (Value)
    node_values = {}
    node_ins, node_outs = {}, {}
    for l in links:
        t, v = l['target'], l['value']
        node_ins[t] = node_ins.get(t, 0) + v
        s, v = l['source'], l['value']
        node_outs[s] = node_outs.get(s, 0) + v

    for n in nodes.keys():
        # Sankey 节点高度由 Max(In, Out) 决定
        node_values[n] = max(node_ins.get(n, 0), node_outs.get(n, 0))

    # 2. 分阶段分组
    nodes_by_stage = {}
    for k in nodes.keys():
        stage = k[0]
        if isinstance(stage, str) and stage.startswith("REF_"):
            real_stage = stage.replace("REF_", "")
            if real_stage not in nodes_by_stage: nodes_by_stage[real_stage] = []
            nodes_by_stage[real_stage].append(k)
        else:
            if stage not in nodes_by_stage: nodes_by_stage[stage] = []
            nodes_by_stage[stage].append(k)

    # 3. 确定 X 坐标映射
    x_map = {
        "S1": 0.01, "S1.5": 0.13,
        "S2": 0.25, "S2.5": 0.38,
        "S3": 0.50, "S3.5": 0.63,
        "S4": 0.75, "S4.5": 0.88,
        "S5": 0.99
    }

    # =========================================================
    # 4. [关键修复] 动态计算 Y 轴缩放比例 (y_scale)
    # 必须考虑到 GAP 占用的空间，否则节点多时会溢出/重叠
    # =========================================================
    GAP = 0.02  # 节点之间的间隙 (可调大调小)
    min_calculated_scale = float('inf')

    # 遍历每一列，看哪一列是“瓶颈”（即需要空间最大的列）
    for stage, stage_nodes in nodes_by_stage.items():
        if not stage_nodes: continue

        # 该列所有节点的总流量
        total_val_in_stage = sum(node_values.get(n, 0) for n in stage_nodes)

        # 该列需要的 Gap 总高度
        num_nodes = len(stage_nodes)
        total_gap_height = (num_nodes - 1) * GAP

        # 剩余给 Flow 的空间 (保留 5% 的上下边距，所以用 0.95)
        available_height_for_flow = 0.95 - total_gap_height

        # 如果节点太多导致 GAP 占满了屏幕，做一个保护
        if available_height_for_flow <= 0.1:
            available_height_for_flow = 0.1

            # 计算这一列能承受的最大 Scale
        if total_val_in_stage > 0:
            current_scale = available_height_for_flow / total_val_in_stage
        else:
            current_scale = 1.0

        # 全局 Scale 必须满足最拥挤的那一列
        if current_scale < min_calculated_scale:
            min_calculated_scale = current_scale

    y_scale = min_calculated_scale
    # =========================================================

    sorted_node_keys = []
    x_coords = []
    y_coords = []

    all_stages = sorted(list(nodes_by_stage.keys()), key=lambda s: x_map.get(s, 0))

    for stage in all_stages:
        stage_nodes = nodes_by_stage[stage]
        if not stage_nodes: continue

        # --- 排序 ---
        order_list = user_sort_order.get(stage, [])

        def sort_key(n):
            if isinstance(n[0], str) and n[0].startswith("REF_"): return 999999
            name = nodes[n]
            if name in order_list: return order_list.index(name)
            if name in SPECIAL_NODES_MAP: return 90000
            return 10000 - node_values.get(n, 0)

        stage_nodes.sort(key=sort_key)
        sorted_node_keys.extend(stage_nodes)

        # --- 对齐与坐标生成 ---
        alignment = alignments.get(stage, "Top")

        if alignment == "Top":
            current_y = 0.01
            for n in stage_nodes:
                # 节点在图中的实际高度
                h = node_values.get(n, 0) * y_scale

                # Plotly 的 y 是中心点
                cy = current_y + h / 2

                x_coords.append(x_map.get(stage, 0.5))
                y_coords.append(cy)

                current_y += h + GAP

        else:  # Bottom Alignment
            # 1. 先计算这一整组节点如果不加 padding，总共多高
            total_val = sum(node_values.get(n, 0) for n in stage_nodes)
            total_h_pixels = total_val * y_scale
            total_gap_pixels = (len(stage_nodes) - 1) * GAP

            group_height = total_h_pixels + total_gap_pixels

            # 2. 从底部倒推起始点
            current_y = 0.99 - group_height
            if current_y < 0.01: current_y = 0.01  # 溢出保护

            for n in stage_nodes:
                h = node_values.get(n, 0) * y_scale
                cy = current_y + h / 2
                x_coords.append(x_map.get(stage, 0.5))
                y_coords.append(cy)
                current_y += h + GAP

    return sorted_node_keys, x_coords, y_coords