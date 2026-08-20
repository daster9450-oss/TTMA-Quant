# -*- coding: utf-8 -*-
"""
TTMA-Quant「產業金流與跨市場連動」模組 — 後端數據引擎

需要安裝的套件（若缺少會自動安裝，無需手動執行）：
    - yfinance   (抓取台股/美股/日股/韓股/中股歷史股價)
    - pandas     (資料處理)
    - numpy      (數值運算 / 正規化)

執行方式：
    python main.py

輸出：
    sector_data.json  (供前端 SectorDashboard.tsx 讀取)

【跨時區對齊說明】
本程式使用日 K（EOD）資料，yfinance 回傳的日期索引即為該交易所「當地交易日」，
因此不需要額外做分鐘級時區換算；但跨市場比較時，仍需遵守 CLAUDE.md 規定：
    「台股與日股等 T 日資料若對標美股收盤價，必須使用美股 T-1 日收盤價」
原因是：美股收盤時間在台北時間為凌晨，晚於台股/日股/韓股當日收盤，
所以「亞股 T 日」的交易行為，實際上只可能反映「美股 T-1 收盤」的資訊，
故本程式在建立跨市場連動表時，美股欄位一律取「前一個交易日」的收盤與漲跌幅，
並在資料中明確標註 as_of，避免誤用未發生的美股當日收盤價。

此外，各市場計價幣別不同（TWD / JPY / KRW / CNY / USD），加總「成交金額」前
會先用即時匯率（USDTWD=X 等）換算為美元，避免直接加總不同幣別造成的錯誤。
"""

import sys
import subprocess
import importlib


# ---------------------------------------------------------------------------
# 0. 自動檢查並安裝所需套件
# ---------------------------------------------------------------------------
REQUIRED_PACKAGES = {
    "yfinance": "yfinance",
    "pandas": "pandas",
    "numpy": "numpy",
}


def ensure_packages_installed():
    missing = []
    for module_name, pip_name in REQUIRED_PACKAGES.items():
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        print(f"[提示] 偵測到缺少必要套件：{', '.join(missing)}，正在自動安裝...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
        print("[提示] 套件安裝完成，繼續執行程式。")


ensure_packages_installed()

import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf


# ---------------------------------------------------------------------------
# 1. 產業與跨市場代表性標的設定
# ---------------------------------------------------------------------------
# 市場代碼對照：TW=台股、CN=中股、US=美股、JP=日股、KR=韓股
# 【重要提醒】以下 40 個細分板塊的跨市場代表標的，是依產業研究常識彙整的「概念股／龍頭股」
# 對照表，並非官方產業分類，且未逐檔即時查證代碼是否仍然有效（例如下市、更名、代碼變更）。
# 若某檔代碼已失效或近期無成交資料，download_history() 與 compute_ticker_metrics() 會自動
# 略過該標的並印出警告（不會中斷程式），但正式使用前仍建議自行覆核代碼正確性。
SECTOR_MAP = {
    # ------------------------------------------------------------------
    # 半導體與電子零組件 (16)
    # ------------------------------------------------------------------
    "晶圓代工": {
        "TW": ["2330.TW", "2303.TW", "6770.TW"],   # 台積電、聯電、力積電
        "CN": ["688981.SS"],                        # 中芯國際
        "US": ["INTC"],                             # Intel（含晶圓代工業務）
        "KR": ["005930.KS"],                        # 三星電子
    },
    "IC設計": {
        "TW": ["2454.TW", "3034.TW"],       # 聯發科、聯詠
        "US": ["NVDA", "AVGO"],             # NVIDIA、博通
        "JP": ["6723.T"],                   # 瑞薩電子
    },
    "記憶體": {
        "TW": ["2408.TW", "3260.TWO"],      # 南亞科、威剛（威剛為上櫃股）
        "US": ["MU"],                       # 美光科技
        "KR": ["000660.KS", "005930.KS"],   # SK海力士、三星電子
    },
    "先進封裝": {
        "TW": ["3711.TW", "6239.TW"],       # 日月光投控（2018年與矽品合併後改代碼為3711）、力成
        "CN": ["600584.SS"],                # 長電科技
        "US": ["AMKR"],                     # Amkor Technology
    },
    "IC載板": {
        "TW": ["3037.TW", "8046.TW"],       # 欣興、南電
    },
    "半導體設備": {
        "TW": ["3583.TW"],                  # 辛耘
        "US": ["AMAT", "LRCX"],             # 應用材料、科林研發
        "JP": ["8035.T", "6146.T"],         # 東京威力科創、Disco
    },
    "半導體材料": {
        "TW": ["3532.TW"],                  # 台勝科
        "US": ["ENTG"],                     # Entegris
        "JP": ["4063.T"],                   # 信越化學
    },
    "被動元件": {
        "TW": ["2327.TW", "2492.TW"],       # 國巨、華新科
        "US": ["VSH"],                      # Vishay
        "JP": ["6981.T"],                   # 村田製作所
        "KR": ["009150.KS"],                # 三星電機
    },
    "PCB印刷電路板": {
        "TW": ["2313.TW", "3044.TW"],       # 華通、健鼎
        "CN": ["002463.SZ"],                # 滬電股份
        "US": ["TTMI"],                     # TTM Technologies
    },
    "連接器": {
        "TW": ["2392.TW"],                  # 正崴
        "US": ["APH"],                      # 安費諾
    },
    "面板顯示器": {
        "TW": ["2409.TW", "3481.TW"],       # 友達、群創
        "CN": ["000725.SZ"],                # 京東方
        "JP": ["6753.T"],                   # 夏普
        "KR": ["034220.KS"],                # LG Display
    },
    "LED": {
        "TW": ["3081.TWO"],                 # 全新（LED磊晶片，上櫃股）
    },
    "光通訊與光模組": {
        "TW": ["3363.TWO"],                 # 上詮（上櫃股）
        "US": ["AAOI", "COHR"],             # Applied Optoelectronics、Coherent
    },
    "散熱液冷": {
        "TW": ["3017.TW", "3324.TWO"],      # 奇鋐、雙鴻（雙鴻為上櫃股，代碼字尾為 .TWO）
        "CN": ["002050.SZ"],                # 三花智控
        "US": ["VRT"],                      # Vertiv
        "JP": ["6504.T"],                   # 富士電機
        "KR": ["009150.KS"],                # 三星電機
    },
    "電源供應器": {
        "TW": ["2308.TW", "6412.TW"],       # 台達電、群電
        "US": ["MPWR"],                     # Monolithic Power Systems
    },
    "網通設備": {
        "TW": ["2345.TW", "6285.TW"],       # 智邦、啟碁
        "US": ["CSCO", "ANET"],             # 思科、Arista Networks
    },

    # ------------------------------------------------------------------
    # 系統組裝與終端應用 (5)
    # ------------------------------------------------------------------
    "AI伺服器與雲端基建": {
        "TW": ["2317.TW", "2382.TW", "3231.TW"],   # 鴻海、廣達、緯創
        "US": ["SMCI", "DELL"],                     # 美超微、戴爾
        "JP": ["6702.T"],                           # 富士通
        "KR": ["000660.KS"],                        # SK海力士
    },
    "手機組裝/蘋果供應鏈": {
        "TW": ["2317.TW", "3008.TW"],       # 鴻海、大立光
        "CN": ["002475.SZ"],                # 立訊精密
        "US": ["AAPL"],                     # 蘋果
        "KR": ["005930.KS"],                # 三星電子
    },
    "筆電代工": {
        "TW": ["2382.TW", "2356.TW"],       # 廣達、英業達
        "US": ["HPQ"],                      # 惠普
    },
    "工業電腦": {
        "TW": ["2395.TW", "6414.TW"],       # 研華、樺漢
    },
    "遊戲與數位內容": {
        "TW": ["6180.TWO", "3293.TWO"],     # 橘子、鈊象（皆為上櫃股）
        "US": ["TTWO"],                     # Take-Two Interactive
        "JP": ["7974.T"],                   # 任天堂
        "KR": ["036570.KS"],                # NCsoft
    },

    # ------------------------------------------------------------------
    # 電動車、車用電子與能源 (7)
    # ------------------------------------------------------------------
    "電動車供應鏈": {
        "TW": ["3665.TW", "2231.TW"],       # 貿聯-KY、為升
        "CN": ["002594.SZ"],                # 比亞迪
        "US": ["TSLA"],                     # Tesla
        "JP": ["6752.T"],                   # Panasonic
        "KR": ["006400.KS"],                # 三星SDI
    },
    "車用電子": {
        "TW": ["2308.TW", "3665.TW"],       # 台達電、貿聯-KY
        "US": ["NXPI"],                     # 恩智浦
        "JP": ["6902.T"],                   # 電裝
        "KR": ["012330.KS"],                # 現代摩比斯
    },
    "重電與電網": {
        "TW": ["1519.TW", "1503.TW"],       # 華城、士電
        "US": ["GEV"],                      # GE Vernova
        "JP": ["6501.T"],                   # 日立製作所
        "KR": ["267260.KS"],                # HD現代電機
    },
    "太陽能": {
        "TW": ["3576.TW"],                  # 聯合再生
        "CN": ["601012.SS"],                # 隆基綠能
        "US": ["FSLR"],                     # First Solar
    },
    "風電": {
        "TW": ["9958.TW"],                  # 世紀鋼
        "US": ["GEV"],                      # GE Vernova（含離岸風電業務）
    },
    "儲能": {
        "TW": ["2308.TW"],                  # 台達電
        "CN": ["300750.SZ"],                # 寧德時代
        "US": ["FLNC"],                     # Fluence Energy
        "JP": ["6752.T"],                   # Panasonic
        "KR": ["006400.KS"],                # 三星SDI
    },
    "電信": {
        "TW": ["2412.TW", "3045.TW"],       # 中華電、台灣大
        "US": ["VZ"],                       # Verizon
        "JP": ["9432.T"],                   # 日本電信電話 (NTT)
        "KR": ["017670.KS"],                # SK Telecom
    },

    # ------------------------------------------------------------------
    # 生醫、金融與傳產 (9)
    # ------------------------------------------------------------------
    "生技新藥": {
        "TW": ["4174.TWO", "1795.TW"],      # 浩鼎（上櫃股）、美時
        "US": ["XBI"],                      # 標普生技類股ETF
        "JP": ["4502.T"],                   # 武田藥品
        "KR": ["207940.KS"],                # 三星生物製劑
    },
    "醫療器材": {
        "TW": ["4106.TW", "1786.TW"],       # 雃博、科妍
        "US": ["MDT"],                      # 美敦力
        "JP": ["4543.T"],                   # Terumo
    },
    "金融": {
        "TW": ["2881.TW", "2882.TW"],       # 富邦金、國泰金
        "CN": ["601398.SS"],                # 中國工商銀行
        "US": ["XLF"],                      # 金融類股ETF
        "JP": ["8306.T"],                   # 三菱UFJ金融集團
        "KR": ["105560.KS"],                # KB金融
    },
    "貨櫃航運": {
        "TW": ["2603.TW", "2609.TW"],       # 長榮、陽明
        "US": ["ZIM"],                      # ZIM以星航運
        "JP": ["9101.T"],                   # 日本郵船
        "KR": ["011200.KS"],                # HMM
    },
    "散裝航運": {
        "TW": ["2606.TW", "2615.TW"],       # 裕民、萬海
        "US": ["BOAT"],                     # 全球航運類股ETF
    },
    "航空": {
        "TW": ["2610.TW", "2618.TW"],       # 華航、長榮航
        "US": ["DAL"],                      # 達美航空
        "JP": ["9201.T"],                   # 日本航空
        "KR": ["003490.KS"],                # 大韓航空
    },
    "鋼鐵": {
        "TW": ["2002.TW", "2027.TW"],       # 中鋼、大成鋼
        "CN": ["600019.SS"],                # 寶山鋼鐵
        "US": ["NUE"],                      # 紐克鋼鐵
        "JP": ["5401.T"],                   # 日本製鐵
        "KR": ["005490.KS"],                # POSCO控股
    },
    "塑化": {
        "TW": ["1301.TW", "1303.TW"],       # 台塑、南亞
        "CN": ["600028.SS"],                # 中國石化
        "US": ["DOW"],                      # 陶氏化學
        "KR": ["051910.KS"],                # LG化學
    },
    "水泥": {
        "TW": ["1101.TW", "1102.TW"],       # 台泥、亞泥
        "CN": ["600585.SS"],                # 海螺水泥
    },

    # ------------------------------------------------------------------
    # 民生消費 (3)
    # ------------------------------------------------------------------
    "紡織": {
        "TW": ["1440.TW", "1477.TW"],       # 南紡、聚陽
    },
    "食品": {
        "TW": ["1216.TW", "1201.TW"],       # 統一、味全
    },
    "零售通路": {
        "TW": ["2912.TW", "5903.TWO"],      # 統一超、全家（全家為上櫃股）
        "US": ["XRT"],                      # 零售類股ETF
    },
}

# 靜態代碼→名稱對照（避免逐檔呼叫 yfinance .info 造成速度緩慢 / 速率限制）
NAME_MAP = {
    # --- 半導體與電子零組件 ---
    "2330.TW": "台積電", "2303.TW": "聯電", "6770.TW": "力積電",
    "688981.SS": "中芯國際", "INTC": "Intel", "005930.KS": "三星電子",
    "2454.TW": "聯發科", "3034.TW": "聯詠", "NVDA": "NVIDIA", "AVGO": "博通",
    "6723.T": "瑞薩電子",
    "2408.TW": "南亞科", "3260.TWO": "威剛", "MU": "美光科技", "000660.KS": "SK海力士",
    "3711.TW": "日月光投控", "6239.TW": "力成", "600584.SS": "長電科技", "AMKR": "Amkor",
    "3037.TW": "欣興", "8046.TW": "南電",
    "3583.TW": "辛耘", "AMAT": "應用材料", "LRCX": "科林研發",
    "8035.T": "東京威力科創", "6146.T": "Disco",
    "3532.TW": "台勝科", "ENTG": "Entegris", "4063.T": "信越化學",
    "2327.TW": "國巨", "2492.TW": "華新科", "VSH": "Vishay", "6981.T": "村田製作所",
    "009150.KS": "三星電機",
    "2313.TW": "華通", "3044.TW": "健鼎", "002463.SZ": "滬電股份", "TTMI": "TTM Technologies",
    "2392.TW": "正崴", "APH": "安費諾",
    "2409.TW": "友達", "3481.TW": "群創", "000725.SZ": "京東方", "6753.T": "夏普",
    "034220.KS": "LG Display",
    "3081.TWO": "全新",
    "3363.TWO": "上詮", "AAOI": "Applied Optoelectronics", "COHR": "Coherent",
    "3017.TW": "奇鋐", "3324.TWO": "雙鴻", "002050.SZ": "三花智控", "VRT": "Vertiv",
    "6504.T": "富士電機",
    "2308.TW": "台達電", "6412.TW": "群電", "MPWR": "Monolithic Power",
    "2345.TW": "智邦", "6285.TW": "啟碁", "CSCO": "思科", "ANET": "Arista Networks",

    # --- 系統組裝與終端應用 ---
    "2317.TW": "鴻海", "2382.TW": "廣達", "3231.TW": "緯創", "SMCI": "美超微", "DELL": "戴爾",
    "6702.T": "富士通",
    "3008.TW": "大立光", "002475.SZ": "立訊精密", "AAPL": "蘋果",
    "2356.TW": "英業達", "HPQ": "惠普",
    "2395.TW": "研華", "6414.TW": "樺漢",
    "6180.TWO": "橘子", "3293.TWO": "鈊象", "TTWO": "Take-Two Interactive", "7974.T": "任天堂",
    "036570.KS": "NCsoft",

    # --- 電動車、車用電子與能源 ---
    "3665.TW": "貿聯-KY", "2231.TW": "為升", "002594.SZ": "比亞迪", "TSLA": "特斯拉",
    "6752.T": "Panasonic", "006400.KS": "三星SDI",
    "NXPI": "恩智浦", "6902.T": "電裝", "012330.KS": "現代摩比斯",
    "1519.TW": "華城", "1503.TW": "士電", "GEV": "GE Vernova", "6501.T": "日立製作所",
    "267260.KS": "HD現代電機",
    "3576.TW": "聯合再生", "601012.SS": "隆基綠能", "FSLR": "First Solar",
    "9958.TW": "世紀鋼",
    "300750.SZ": "寧德時代", "FLNC": "Fluence Energy",
    "2412.TW": "中華電", "3045.TW": "台灣大", "VZ": "Verizon", "9432.T": "NTT",
    "017670.KS": "SK Telecom",

    # --- 生醫、金融與傳產 ---
    "4174.TWO": "浩鼎", "1795.TW": "美時", "XBI": "標普生技ETF", "4502.T": "武田藥品",
    "207940.KS": "三星生物製劑",
    "4106.TW": "雃博", "1786.TW": "科妍", "MDT": "美敦力", "4543.T": "Terumo",
    "2881.TW": "富邦金", "2882.TW": "國泰金", "601398.SS": "中國工商銀行", "XLF": "金融類股ETF",
    "8306.T": "三菱UFJ金融集團", "105560.KS": "KB金融",
    "2603.TW": "長榮", "2609.TW": "陽明", "ZIM": "ZIM以星航運", "9101.T": "日本郵船",
    "011200.KS": "HMM",
    "2606.TW": "裕民", "2615.TW": "萬海", "BOAT": "全球航運ETF",
    "2610.TW": "華航", "2618.TW": "長榮航", "DAL": "達美航空", "9201.T": "日本航空",
    "003490.KS": "大韓航空",
    "2002.TW": "中鋼", "2027.TW": "大成鋼", "600019.SS": "寶山鋼鐵", "NUE": "紐克鋼鐵",
    "5401.T": "日本製鐵", "005490.KS": "POSCO控股",
    "1301.TW": "台塑", "1303.TW": "南亞", "600028.SS": "中國石化", "DOW": "陶氏化學",
    "051910.KS": "LG化學",
    "1101.TW": "台泥", "1102.TW": "亞泥", "600585.SS": "海螺水泥",

    # --- 民生消費 ---
    "1440.TW": "南紡", "1477.TW": "聚陽",
    "1216.TW": "統一", "1201.TW": "味全",
    "2912.TW": "統一超", "5903.TWO": "全家", "XRT": "零售類股ETF",
}

# 各市場計價幣別 → 對美元匯率的 yfinance 代碼 (格式為 1 USD 兌換多少當地幣別)
MARKET_CURRENCY = {"TW": "TWD", "CN": "CNY", "US": "USD", "JP": "JPY", "KR": "KRW"}
FX_TICKERS = {"TWD": "TWD=X", "CNY": "CNY=X", "JPY": "JPY=X", "KRW": "KRW=X"}

MARKET_LABEL = {"TW": "台股", "CN": "中股", "US": "美股", "JP": "日股", "KR": "韓股"}


# ---------------------------------------------------------------------------
# 2. 批次下載歷史股價
# ---------------------------------------------------------------------------
def collect_all_tickers():
    tickers = set()
    for markets in SECTOR_MAP.values():
        for market_tickers in markets.values():
            tickers.update(market_tickers)
    tickers.update(FX_TICKERS.values())
    return sorted(tickers)


def download_history(tickers, period="30d"):
    print(f"[資訊] 開始下載 {len(tickers)} 檔標的近 {period} 歷史資料...")
    raw = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )
    return raw


def extract_ticker_df(raw, ticker, tickers_count):
    """從 yf.download 的結果中取出單一標的的 DataFrame，並丟棄缺值列。"""
    try:
        if tickers_count == 1:
            df = raw
        else:
            df = raw[ticker]
        df = df.dropna(subset=["Close"])
        return df
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 3. 匯率換算
# ---------------------------------------------------------------------------
def get_fx_rates(raw, tickers_count):
    """回傳 {幣別: 1美元兌當地幣別匯率}，USD 固定為 1。"""
    rates = {"USD": 1.0}
    for currency, fx_ticker in FX_TICKERS.items():
        df = extract_ticker_df(raw, fx_ticker, tickers_count)
        if df is not None and len(df) > 0:
            rates[currency] = float(df["Close"].iloc[-1])
        else:
            print(f"[警告] 匯率 {fx_ticker} 下載失敗，暫以 1.0 代替（金額換算可能不準確）")
            rates[currency] = 1.0
    return rates


def to_usd(amount_local, currency, fx_rates):
    rate = fx_rates.get(currency, 1.0)
    if rate <= 0:
        return 0.0
    return amount_local / rate


# ---------------------------------------------------------------------------
# 4. 單一標的指標計算（含美股 T-1 對齊邏輯）
# ---------------------------------------------------------------------------
def compute_ticker_metrics(df, market, asia_t_date=None):
    """
    回傳單一標的的指標 dict，或 None（資料不足時）。

    market == "US" 時，依 CLAUDE.md 規則使用「美股 T-1」收盤價對齊亞股 T 日：
    美股收盤時間換算為台北時間為凌晨，晚於亞股（台/日/韓/中）當日收盤，
    因此亞股 T 日交易當下，市場能看到的只有「日期早於亞股 T 日」的美股收盤。
    這裡直接用日期比較（而非固定往回推移筆數）找出正確的一筆，
    避免抓取時間點不同（例如美股當日已收盤才執行本程式）造成對齊多推一天或少推一天的誤差。
    """
    min_rows = 3
    if df is None or len(df) < min_rows:
        return None

    if market == "US":
        if asia_t_date is not None:
            eligible = df[df.index.normalize() < pd.Timestamp(asia_t_date).normalize()]
        else:
            eligible = df.iloc[:-1]  # 無亞股基準日可比對時，保守捨棄最新一筆

        if len(eligible) < 2:
            return None

        ref_row = eligible.iloc[-1]
        prev_row = eligible.iloc[-2]
        as_of_date = eligible.index[-1]
        as_of_note = "美股 T-1 收盤（對齊亞股 T 日資訊集）"

        ref_pos = df.index.get_loc(eligible.index[-1])
        start = max(0, ref_pos - 20)
        avg_volume_window = df["Volume"].iloc[start:ref_pos]
    else:
        ref_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        as_of_date = df.index[-1]
        as_of_note = f"{MARKET_LABEL.get(market, market)} T 日收盤"
        avg_volume_window = df["Volume"].iloc[-21:-1] if len(df) >= 21 else df["Volume"].iloc[:-1]

    close = float(ref_row["Close"])
    prev_close = float(prev_row["Close"])
    volume = float(ref_row["Volume"])
    avg_volume = float(avg_volume_window.mean()) if len(avg_volume_window) > 0 else volume

    if prev_close == 0:
        pct_change = 0.0
    else:
        pct_change = (close - prev_close) / prev_close * 100.0

    turnover_local = close * volume
    volume_ratio = (volume / avg_volume) if avg_volume > 0 else 1.0

    return {
        "close": close,
        "prev_close": prev_close,
        "pct_change": pct_change,
        "volume": volume,
        "avg_volume_20d": avg_volume,
        "volume_ratio": volume_ratio,
        "turnover_local": turnover_local,
        "as_of_date": as_of_date.strftime("%Y-%m-%d"),
        "as_of_note": as_of_note,
    }


def compute_ticker_metrics_series(df, market, asia_t_date, days=5):
    """
    回傳最近 `days` 個交易日的指標序列（由舊到新），供動能分數歷史（Sparkline）使用。
    US 市場沿用與 compute_ticker_metrics 相同的「T-1 對齊亞股 T 日」篩選基準，
    確保序列中每一筆美股資料都仍是「亞股 T 日當下已實際發生」的收盤，不含跨時區未來資訊。
    """
    min_rows = 3
    if df is None or len(df) < min_rows:
        return []

    if market == "US":
        if asia_t_date is not None:
            base_df = df[df.index.normalize() < pd.Timestamp(asia_t_date).normalize()]
        else:
            base_df = df.iloc[:-1]
    else:
        base_df = df

    if len(base_df) < 2:
        return []

    latest_pos = len(base_df) - 1
    start_pos = max(1, latest_pos - days + 1)

    series = []
    for pos in range(start_pos, latest_pos + 1):
        ref_row = base_df.iloc[pos]
        prev_row = base_df.iloc[pos - 1]
        close = float(ref_row["Close"])
        prev_close = float(prev_row["Close"])
        volume = float(ref_row["Volume"])
        vol_start = max(0, pos - 20)
        avg_volume_window = base_df["Volume"].iloc[vol_start:pos]
        avg_volume = float(avg_volume_window.mean()) if len(avg_volume_window) > 0 else volume
        pct_change = (close - prev_close) / prev_close * 100.0 if prev_close != 0 else 0.0
        volume_ratio = (volume / avg_volume) if avg_volume > 0 else 1.0
        series.append({
            "pct_change": pct_change,
            "volume_ratio": volume_ratio,
            "turnover_local": close * volume,
        })
    return series


# ---------------------------------------------------------------------------
# 5. 板塊層級彙總：加權漲跌幅 / 動能分數 / 成交金額(USD)
# ---------------------------------------------------------------------------
def normalize_0_100(values):
    """min-max 正規化到 0~100，避免除以 0。"""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [50.0 for _ in values]
    return [(v - lo) / (hi - lo) * 100.0 for v in values]


def build_sector_data():
    all_tickers = collect_all_tickers()
    raw = download_history(all_tickers)
    tickers_count = len(all_tickers)
    fx_rates = get_fx_rates(raw, tickers_count)

    # 決定「亞股 T 日」基準日期：以台積電（高流動性、幾乎每日皆有交易）為代表，
    # 供美股「T-1 對齊」邏輯比對使用（見 compute_ticker_metrics 說明）。
    asia_ref_df = extract_ticker_df(raw, "2330.TW", tickers_count)
    if asia_ref_df is not None and len(asia_ref_df) > 0:
        asia_t_date = asia_ref_df.index[-1]
    else:
        asia_t_date = None
        print("[警告] 無法取得台積電資料以判定亞股 T 日基準，美股將改用保守作法（捨棄最新一筆收盤）")

    HISTORY_DAYS = 5

    cross_market_table = []
    sector_raw_scores = []  # 暫存供動能分數正規化使用
    market_sector_raw = {m: [] for m in MARKET_CURRENCY.keys()}  # 暫存供「單一市場」動能排行正規化使用

    # 暫存供「動能分數歷史」（Sparkline）正規化使用：
    # sector_daily_scores_raw[offset]（offset: 0=最舊…HISTORY_DAYS-1=最新）為當日跨市場各板塊原始數據
    sector_daily_scores_raw = [[] for _ in range(HISTORY_DAYS)]
    # market_daily_sector_raw[market][offset] 為該市場當日各板塊原始數據
    market_daily_sector_raw = {m: [[] for _ in range(HISTORY_DAYS)] for m in MARKET_CURRENCY.keys()}

    for sector_name, markets in SECTOR_MAP.items():
        market_blocks = {}
        sector_total_turnover_usd = 0.0
        sector_total_volume_ratio = []
        sector_weighted_pct_all_markets = []
        sector_weight_all_markets = []

        sector_daily_weighted_pct = [0.0] * HISTORY_DAYS
        sector_daily_weight = [0.0] * HISTORY_DAYS
        sector_daily_vol_ratio_lists = [[] for _ in range(HISTORY_DAYS)]

        for market, tickers in markets.items():
            currency = MARKET_CURRENCY[market]
            ticker_infos = []
            weighted_pct_sum = 0.0
            weight_sum = 0.0
            market_volume_ratios = []  # 暫存供該市場單獨計算動能分數使用

            market_daily_weighted_pct = [0.0] * HISTORY_DAYS
            market_daily_weight = [0.0] * HISTORY_DAYS
            market_daily_vol_ratio_lists = [[] for _ in range(HISTORY_DAYS)]

            for ticker in tickers:
                df = extract_ticker_df(raw, ticker, tickers_count)
                metrics = compute_ticker_metrics(df, market, asia_t_date)
                if metrics is None:
                    print(f"[警告] {ticker}（{MARKET_LABEL.get(market, market)}）資料不足，已略過")
                    continue

                turnover_usd = to_usd(metrics["turnover_local"], currency, fx_rates)
                ticker_infos.append({
                    "symbol": ticker,
                    "name": NAME_MAP.get(ticker, ticker),
                    "close": round(metrics["close"], 2),
                    "pct_change": round(metrics["pct_change"], 2),
                    "volume": int(metrics["volume"]),
                    "turnover_usd": round(turnover_usd, 2),
                    "as_of_date": metrics["as_of_date"],
                })

                weight = metrics["turnover_local"] if metrics["turnover_local"] > 0 else 1e-6
                weighted_pct_sum += metrics["pct_change"] * weight
                weight_sum += weight

                sector_total_turnover_usd += turnover_usd
                sector_total_volume_ratio.append(metrics["volume_ratio"])
                market_volume_ratios.append(metrics["volume_ratio"])

                # 近 HISTORY_DAYS 日歷史序列，供動能分數歷史（Sparkline）使用
                history_series = compute_ticker_metrics_series(df, market, asia_t_date, days=HISTORY_DAYS)
                for offset, h in enumerate(history_series):
                    h_weight = h["turnover_local"] if h["turnover_local"] > 0 else 1e-6
                    market_daily_weighted_pct[offset] += h["pct_change"] * h_weight
                    market_daily_weight[offset] += h_weight
                    market_daily_vol_ratio_lists[offset].append(h["volume_ratio"])

            if weight_sum > 0:
                weighted_change_pct = weighted_pct_sum / weight_sum
                sector_weighted_pct_all_markets.append(weighted_change_pct * weight_sum)
                sector_weight_all_markets.append(weight_sum)
            else:
                weighted_change_pct = 0.0

            as_of_note = ticker_infos[0]["as_of_date"] if ticker_infos else None
            market_blocks[market] = {
                "market_label": MARKET_LABEL[market],
                "tickers": ticker_infos,
                "weighted_change_pct": round(weighted_change_pct, 2),
                "as_of": as_of_note,
            }

            # 供「單一市場」動能排行使用：僅彙總該市場自身的漲跌幅與量能，
            # 與跨市場動能分數（sector_raw_scores）分開計算，避免不同市場互相干擾排序。
            if ticker_infos:
                market_turnover_usd = sum(t["turnover_usd"] for t in ticker_infos)
                market_avg_volume_ratio = (
                    float(np.mean(market_volume_ratios)) if market_volume_ratios else 1.0
                )
                market_sector_raw[market].append({
                    "sector": sector_name,
                    "weighted_change_pct": round(weighted_change_pct, 2),
                    "turnover_usd": round(market_turnover_usd, 2),
                    "abs_change": abs(weighted_change_pct),
                    "volume_ratio": market_avg_volume_ratio,
                })

            for offset in range(HISTORY_DAYS):
                if market_daily_weight[offset] > 0:
                    m_wpct = market_daily_weighted_pct[offset] / market_daily_weight[offset]
                    m_vol = (
                        float(np.mean(market_daily_vol_ratio_lists[offset]))
                        if market_daily_vol_ratio_lists[offset]
                        else 1.0
                    )
                    market_daily_sector_raw[market][offset].append({
                        "sector": sector_name,
                        "weighted_change_pct": m_wpct,
                        "volume_ratio": m_vol,
                    })
                    sector_daily_weighted_pct[offset] += m_wpct * market_daily_weight[offset]
                    sector_daily_weight[offset] += market_daily_weight[offset]
                    sector_daily_vol_ratio_lists[offset].extend(market_daily_vol_ratio_lists[offset])

        total_weight = sum(sector_weight_all_markets)
        sector_weighted_pct = (
            sum(sector_weighted_pct_all_markets) / total_weight if total_weight > 0 else 0.0
        )
        avg_volume_ratio = (
            float(np.mean(sector_total_volume_ratio)) if sector_total_volume_ratio else 1.0
        )

        cross_market_table.append({
            "sector": sector_name,
            "markets": market_blocks,
        })

        sector_raw_scores.append({
            "sector": sector_name,
            "weighted_change_pct": round(sector_weighted_pct, 2),
            "turnover_usd": round(sector_total_turnover_usd, 2),
            "abs_change": abs(sector_weighted_pct),
            "volume_ratio": avg_volume_ratio,
        })

        for offset in range(HISTORY_DAYS):
            if sector_daily_weight[offset] > 0:
                s_wpct = sector_daily_weighted_pct[offset] / sector_daily_weight[offset]
                s_vol = (
                    float(np.mean(sector_daily_vol_ratio_lists[offset]))
                    if sector_daily_vol_ratio_lists[offset]
                    else 1.0
                )
                sector_daily_scores_raw[offset].append({
                    "sector": sector_name,
                    "weighted_change_pct": s_wpct,
                    "volume_ratio": s_vol,
                })

    # --- 動能分數歷史（近 HISTORY_DAYS 日，供前端 Sparkline 使用）---
    # 每一天分別對「當天有資料的板塊」做 0~100 正規化，與當日動能分數計算邏輯一致。
    sector_history_scores = {s["sector"]: [] for s in sector_raw_scores}
    for offset in range(HISTORY_DAYS):
        day_raw = sector_daily_scores_raw[offset]
        if not day_raw:
            continue
        day_abs_scores = normalize_0_100([abs(r["weighted_change_pct"]) for r in day_raw])
        day_vol_scores = normalize_0_100([r["volume_ratio"] for r in day_raw])
        for i, r in enumerate(day_raw):
            composite = 0.5 * day_abs_scores[i] + 0.5 * day_vol_scores[i]
            sector_history_scores[r["sector"]].append(round(composite, 1))

    market_history_scores = {
        m: {r["sector"]: [] for r in market_sector_raw[m]} for m in market_sector_raw
    }
    for market, daily_lists in market_daily_sector_raw.items():
        for offset in range(HISTORY_DAYS):
            day_raw = daily_lists[offset]
            if not day_raw:
                continue
            day_abs_scores = normalize_0_100([abs(r["weighted_change_pct"]) for r in day_raw])
            day_vol_scores = normalize_0_100([r["volume_ratio"] for r in day_raw])
            for i, r in enumerate(day_raw):
                composite = 0.5 * day_abs_scores[i] + 0.5 * day_vol_scores[i]
                market_history_scores[market][r["sector"]].append(round(composite, 1))

    # --- 動能分數：漲跌幅強度(50%) + 量能比(50%)，各自正規化後加總，再整體正規化到 0~100 ---
    abs_change_scores = normalize_0_100([s["abs_change"] for s in sector_raw_scores])
    volume_ratio_scores = normalize_0_100([s["volume_ratio"] for s in sector_raw_scores])
    total_turnover_all = sum(s["turnover_usd"] for s in sector_raw_scores) or 1.0

    momentum_ranking = []
    for i, s in enumerate(sector_raw_scores):
        composite = 0.5 * abs_change_scores[i] + 0.5 * volume_ratio_scores[i]
        momentum_ranking.append({
            "sector": s["sector"],
            "momentum_score": round(composite, 1),
            "weighted_change_pct": s["weighted_change_pct"],
            "turnover_usd": s["turnover_usd"],
            # 成交量放大倍率（近 20 日均量的倍數）
            "vol_surge": round(s["volume_ratio"], 2),
            # 價格動能（加權漲跌幅，與 weighted_change_pct 相同，供 Tooltip 獨立取用）
            "price_mom": s["weighted_change_pct"],
            # 該板塊成交金額佔本次排行總成交金額的比重
            "weight_pct": round(s["turnover_usd"] / total_turnover_all * 100, 1),
            # 近 5 日動能分數，供前端 Sparkline 迷你趨勢線使用
            "history_scores": sector_history_scores.get(s["sector"], []),
        })

    momentum_ranking.sort(key=lambda x: x["momentum_score"], reverse=True)

    # --- 單一市場動能排行：各市場內部依「漲跌幅強度(50%) + 量能比(50%)」單獨正規化 ---
    market_momentum = {}
    for market, raw_list in market_sector_raw.items():
        if not raw_list:
            market_momentum[market] = []
            continue
        m_abs_scores = normalize_0_100([r["abs_change"] for r in raw_list])
        m_vol_scores = normalize_0_100([r["volume_ratio"] for r in raw_list])
        total_market_turnover = sum(r["turnover_usd"] for r in raw_list) or 1.0
        items = []
        for i, r in enumerate(raw_list):
            composite = 0.5 * m_abs_scores[i] + 0.5 * m_vol_scores[i]
            items.append({
                "sector": r["sector"],
                "momentum_score": round(composite, 1),
                "weighted_change_pct": r["weighted_change_pct"],
                "turnover_usd": r["turnover_usd"],
                "vol_surge": round(r["volume_ratio"], 2),
                "price_mom": r["weighted_change_pct"],
                "weight_pct": round(r["turnover_usd"] / total_market_turnover * 100, 1),
                "history_scores": market_history_scores.get(market, {}).get(r["sector"], []),
            })
        items.sort(key=lambda x: x["momentum_score"], reverse=True)
        market_momentum[market] = items

    result = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fx_rates_usd_base": fx_rates,
        "cross_market_table": cross_market_table,
        "momentum_ranking": momentum_ranking,
        "market_momentum": market_momentum,
    }
    return result


# ---------------------------------------------------------------------------
# 6. 主程式
# ---------------------------------------------------------------------------
def main():
    start = time.time()
    data = build_sector_data()

    output_path = "sector_data.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start
    print(f"[完成] 已輸出 {output_path}（耗時 {elapsed:.1f} 秒）")


if __name__ == "__main__":
    main()
