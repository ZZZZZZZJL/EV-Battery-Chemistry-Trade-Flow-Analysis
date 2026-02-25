import os

# ==================== 路径配置 ====================
# 获取项目根目录 (假设 config.py 在 modules/ 下，所以往上跳两级)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

REF_FILE = os.path.join(DATA_DIR, "ListOfreference.xlsx")
TRADE_DIR = os.path.join(DATA_DIR, "trade")

# 生产数据
PROD_FILES = {
    "Mining": os.path.join(DATA_DIR, "production", "Mining_Production.xlsx"),
    "Refining": os.path.join(DATA_DIR, "production", "Refining_Production.xlsx"),
    "Cathode": os.path.join(DATA_DIR, "production", "Cathode_Electrolyte_Production_converted.xlsx")
}

# ==================== 特殊节点 ====================
SPECIAL_NODES_MAP = {
    "NBCP": 999, "NCPC": 998, "NTRM": 997, "MRMT": 996, "URMS": 995,
    "UARP": 994, "TTCR": 993, "TFCR": 992, "TFCM": 991,
    "NCM": 901, "NCA": 902, "LFP": 903
}

# ==================== 颜色配置 ====================
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
    995: '#CCCCCC', 996: '#CCCCCC', 997: '#CCCCCC', 998: '#CCCCCC', 999: '#CCCCCC',
    901: '#000086', 902: '#000086', 903: '#000086',
}

# 默认国家排序 (按照金属和阶段预设 ID)
DEFAULT_ORDERS = {
    "Li": {
        "S1": [76, 620, 716, 36, 156, 152, 32, 842],
        "S2": [156, 152, 32, 842],
        "S3": [156, 152, 32, 842],
        "S4": [156, 410, 392, 842, 124]
    },
    "Ni": {
        "S1": [156, 608, 540, 36, 643, 124, 76, 360, 842],
        "S2": [156, 410, 392, 826, 579, 710, 251, 246],
        "S3": [156, 410, 392, 826, 579, 710, 251, 246],
        "S4": [156, 410, 392, 842, 124]
    },
    "Co": {
        "S1": [180, 156, 124, 36, 450, 504, 643, 192, 608, 842, 360, 598],
        "S2": [180, 156, 392, 699, 894, 579, 710, 246, 56, 124, 36, 450, 504],
        "S3": [180, 156, 392, 699, 894, 579, 710, 246, 56, 124, 36, 450, 504],
        "S4": [156, 410, 392, 842, 124]
    },
    "Mn": {
        "S1": [156, 710, 36, 266, 76, 288, 384, 458, 104, 356, 398, 484, 804, 268, 704],
        "S2": [156, 356, 392, 724, 170, 842, 300],
        "S3": [156, 356, 392, 724, 170, 842, 300],
        "S4": [156, 410, 392, 842, 124]
    }
}

def darken_hex(hex_color, factor=0.5):
    """将十六进制颜色变暗 (factor 越小越暗)"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6: return "#888888"
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    darkened = tuple(int(c * factor) for c in rgb)
    return '#%02x%02x%02x' % darkened

def get_color(node_id):
    # 如果是带有 _gap 后缀的虚拟节点
    if isinstance(node_id, str) and str(node_id).endswith("_gap"):
        base_id = int(float(str(node_id).split("_")[0]))
        base_color = ID_COLORS.get(base_id, "#CCCCCC")
        return darken_hex(base_color, 0.4) # 0.4 表示亮度降到 40%

    # 正常的节点
    try:
        return ID_COLORS.get(int(float(node_id)), "#CCCCCC")
    except:
        return "#CCCCCC"

def hex_to_rgba(hex_val, opacity=0.4):
    hex_val = hex_val.lstrip('#')
    rgb = tuple(int(hex_val[i:i + len(hex_val)//3], 16) for i in range(0, len(hex_val), len(hex_val)//3))
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {opacity})"