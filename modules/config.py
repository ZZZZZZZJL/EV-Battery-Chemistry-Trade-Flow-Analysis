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
    "UARP": 994, "TTCR": 993, "TFCR": 992, "TFCM": 991
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
    995: '#CCCCCC', 996: '#CCCCCC', 997: '#CCCCCC', 998: '#CCCCCC', 999: '#CCCCCC'
}

def get_color(node_id):
    try:
        return ID_COLORS.get(int(float(node_id)), "#CCCCCC")
    except:
        return "#CCCCCC"

def hex_to_rgba(hex_val, opacity=0.4):
    hex_val = hex_val.lstrip('#')
    rgb = tuple(int(hex_val[i:i + len(hex_val)//3], 16) for i in range(0, len(hex_val), len(hex_val)//3))
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {opacity})"