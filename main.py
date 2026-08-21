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

# ---------------------------------------------------------------------------
# 板塊 ID 對照（英文 slug，供前端 sectorDict 依 sector_id 查詢四語系板塊名稱）
# ---------------------------------------------------------------------------
SECTOR_ID_MAP = {
    "晶圓代工": "wafer_foundry",
    "IC設計": "ic_design",
    "記憶體": "memory",
    "先進封裝": "advanced_packaging",
    "IC載板": "ic_substrate",
    "半導體設備": "semiconductor_equipment",
    "半導體材料": "semiconductor_materials",
    "被動元件": "passive_components",
    "PCB印刷電路板": "pcb",
    "連接器": "connectors",
    "面板顯示器": "display_panel",
    "LED": "led",
    "光通訊與光模組": "optical_communication",
    "散熱液冷": "thermal_cooling",
    "電源供應器": "power_supply",
    "網通設備": "networking_equipment",
    "AI伺服器與雲端基建": "ai_server_cloud_infra",
    "手機組裝/蘋果供應鏈": "smartphone_apple_supply_chain",
    "筆電代工": "notebook_odm",
    "工業電腦": "industrial_pc",
    "遊戲與數位內容": "gaming_digital_content",
    "電動車供應鏈": "ev_supply_chain",
    "車用電子": "automotive_electronics",
    "重電與電網": "heavy_electric_grid",
    "太陽能": "solar",
    "風電": "wind_power",
    "儲能": "energy_storage",
    "電信": "telecom",
    "生技新藥": "biotech_pharma",
    "醫療器材": "medical_devices",
    "金融": "financials",
    "貨櫃航運": "container_shipping",
    "散裝航運": "dry_bulk_shipping",
    "航空": "airlines",
    "鋼鐵": "steel",
    "塑化": "petrochemicals",
    "水泥": "cement",
    "紡織": "textiles",
    "食品": "food",
    "零售通路": "retail",
}


# ---------------------------------------------------------------------------
# 個股多語系名稱對照（zh-TW / zh-CN / en-US / ja）
# 靜態表為主（避免逐檔呼叫 yfinance .info 造成速度緩慢 / 速率限制）；
# 英文與日文一律採國際金融市場／日本財經媒體通用代稱或縮寫（如 TSMC、AAPL、Hon Hai），
# 不做生硬拼音或全名直翻。若代碼未收錄於此表，才由 get_ticker_name_i18n() 以
# yfinance .info.get('shortName') 自動 fallback（見下方函式）。
# ---------------------------------------------------------------------------
NAME_I18N_MAP = {
    # --- 半導體與電子零組件 ---
    "2330.TW": {"zh-TW": "台積電", "zh-CN": "台积电", "en-US": "TSMC", "ja": "TSMC"},
    "2303.TW": {"zh-TW": "聯電", "zh-CN": "联电", "en-US": "UMC", "ja": "UMC"},
    "6770.TW": {"zh-TW": "力積電", "zh-CN": "力积电", "en-US": "PSMC", "ja": "PSMC"},
    "688981.SS": {"zh-TW": "中芯國際", "zh-CN": "中芯国际", "en-US": "SMIC", "ja": "SMIC"},
    "INTC": {"zh-TW": "Intel", "zh-CN": "英特尔", "en-US": "Intel", "ja": "インテル"},
    "005930.KS": {"zh-TW": "三星電子", "zh-CN": "三星电子", "en-US": "Samsung Electronics", "ja": "サムスン電子"},
    "2454.TW": {"zh-TW": "聯發科", "zh-CN": "联发科", "en-US": "MediaTek", "ja": "MediaTek"},
    "3034.TW": {"zh-TW": "聯詠", "zh-CN": "联咏", "en-US": "Novatek", "ja": "Novatek"},
    "NVDA": {"zh-TW": "NVIDIA", "zh-CN": "英伟达", "en-US": "NVIDIA", "ja": "NVIDIA"},
    "AVGO": {"zh-TW": "博通", "zh-CN": "博通", "en-US": "Broadcom", "ja": "ブロードコム"},
    "6723.T": {"zh-TW": "瑞薩電子", "zh-CN": "瑞萨电子", "en-US": "Renesas", "ja": "ルネサス"},
    "2408.TW": {"zh-TW": "南亞科", "zh-CN": "南亚科", "en-US": "Nanya Tech", "ja": "Nanya Tech"},
    "3260.TWO": {"zh-TW": "威剛", "zh-CN": "威刚", "en-US": "ADATA", "ja": "ADATA"},
    "MU": {"zh-TW": "美光科技", "zh-CN": "美光科技", "en-US": "Micron", "ja": "マイクロン"},
    "000660.KS": {"zh-TW": "SK海力士", "zh-CN": "SK海力士", "en-US": "SK Hynix", "ja": "SKハイニックス"},
    "3711.TW": {"zh-TW": "日月光投控", "zh-CN": "日月光投控", "en-US": "ASE Technology", "ja": "ASEテクノロジー"},
    "6239.TW": {"zh-TW": "力成", "zh-CN": "力成", "en-US": "Powertech", "ja": "Powertech"},
    "600584.SS": {"zh-TW": "長電科技", "zh-CN": "长电科技", "en-US": "JCET", "ja": "JCET"},
    "AMKR": {"zh-TW": "Amkor", "zh-CN": "安靠科技", "en-US": "Amkor", "ja": "アムコー"},
    "3037.TW": {"zh-TW": "欣興", "zh-CN": "欣兴", "en-US": "Unimicron", "ja": "Unimicron"},
    "8046.TW": {"zh-TW": "南電", "zh-CN": "南电", "en-US": "Nan Ya PCB", "ja": "Nan Ya PCB"},
    "3583.TW": {"zh-TW": "辛耘", "zh-CN": "辛耘", "en-US": "Gallant Micro", "ja": "Gallant Micro"},
    "AMAT": {"zh-TW": "應用材料", "zh-CN": "应用材料", "en-US": "Applied Materials", "ja": "アプライドマテリアルズ"},
    "LRCX": {"zh-TW": "科林研發", "zh-CN": "泛林集团", "en-US": "Lam Research", "ja": "ラムリサーチ"},
    "8035.T": {"zh-TW": "東京威力科創", "zh-CN": "东京电子", "en-US": "Tokyo Electron", "ja": "東京エレクトロン"},
    "6146.T": {"zh-TW": "Disco", "zh-CN": "Disco", "en-US": "Disco Corp", "ja": "ディスコ"},
    "3532.TW": {"zh-TW": "台勝科", "zh-CN": "台胜科", "en-US": "FormosaSumco", "ja": "FormosaSumco"},
    "ENTG": {"zh-TW": "Entegris", "zh-CN": "恩特格里斯", "en-US": "Entegris", "ja": "エンテグリス"},
    "4063.T": {"zh-TW": "信越化學", "zh-CN": "信越化学", "en-US": "Shin-Etsu Chemical", "ja": "信越化学"},
    "2327.TW": {"zh-TW": "國巨", "zh-CN": "国巨", "en-US": "Yageo", "ja": "Yageo"},
    "2492.TW": {"zh-TW": "華新科", "zh-CN": "华新科", "en-US": "Walsin Technology", "ja": "Walsin Technology"},
    "VSH": {"zh-TW": "Vishay", "zh-CN": "威世", "en-US": "Vishay", "ja": "ヴィシェイ"},
    "6981.T": {"zh-TW": "村田製作所", "zh-CN": "村田制作所", "en-US": "Murata", "ja": "村田製作所"},
    "009150.KS": {"zh-TW": "三星電機", "zh-CN": "三星电机", "en-US": "Samsung Electro-Mechanics", "ja": "サムスン電機"},
    "2313.TW": {"zh-TW": "華通", "zh-CN": "华通", "en-US": "Compeq", "ja": "Compeq"},
    "3044.TW": {"zh-TW": "健鼎", "zh-CN": "健鼎", "en-US": "Tripod Technology", "ja": "Tripod Technology"},
    "002463.SZ": {"zh-TW": "滬電股份", "zh-CN": "沪电股份", "en-US": "Hudian (WUS)", "ja": "滬電股份"},
    "TTMI": {"zh-TW": "TTM Technologies", "zh-CN": "TTM Technologies", "en-US": "TTM Technologies", "ja": "TTMテクノロジーズ"},
    "2392.TW": {"zh-TW": "正崴", "zh-CN": "正崴", "en-US": "Foxlink", "ja": "Foxlink"},
    "APH": {"zh-TW": "安費諾", "zh-CN": "安费诺", "en-US": "Amphenol", "ja": "アンフェノール"},
    "2409.TW": {"zh-TW": "友達", "zh-CN": "友达", "en-US": "AUO", "ja": "AUO"},
    "3481.TW": {"zh-TW": "群創", "zh-CN": "群创", "en-US": "Innolux", "ja": "Innolux"},
    "000725.SZ": {"zh-TW": "京東方", "zh-CN": "京东方", "en-US": "BOE", "ja": "BOE"},
    "6753.T": {"zh-TW": "夏普", "zh-CN": "夏普", "en-US": "Sharp", "ja": "シャープ"},
    "034220.KS": {"zh-TW": "LG Display", "zh-CN": "LG Display", "en-US": "LG Display", "ja": "LGディスプレイ"},
    "3081.TWO": {"zh-TW": "全新", "zh-CN": "全新", "en-US": "Epistar", "ja": "Epistar"},
    "3363.TWO": {"zh-TW": "上詮", "zh-CN": "上诠", "en-US": "Solteam Opto", "ja": "Solteam Opto"},
    "AAOI": {"zh-TW": "Applied Optoelectronics", "zh-CN": "应用光电", "en-US": "AOI", "ja": "AOI"},
    "COHR": {"zh-TW": "Coherent", "zh-CN": "相干公司", "en-US": "Coherent", "ja": "コヒレント"},
    "3017.TW": {"zh-TW": "奇鋐", "zh-CN": "奇鋐", "en-US": "Auras", "ja": "Auras"},
    "3324.TWO": {"zh-TW": "雙鴻", "zh-CN": "双鸿", "en-US": "AVC", "ja": "AVC"},
    "002050.SZ": {"zh-TW": "三花智控", "zh-CN": "三花智控", "en-US": "Sanhua Intelligent Controls", "ja": "三花智控"},
    "VRT": {"zh-TW": "Vertiv", "zh-CN": "维谛技术", "en-US": "Vertiv", "ja": "バーティブ"},
    "6504.T": {"zh-TW": "富士電機", "zh-CN": "富士电机", "en-US": "Fuji Electric", "ja": "富士電機"},
    "2308.TW": {"zh-TW": "台達電", "zh-CN": "台达电", "en-US": "Delta Electronics", "ja": "デルタ電子"},
    "6412.TW": {"zh-TW": "群電", "zh-CN": "群电", "en-US": "Chicony Power", "ja": "Chicony Power"},
    "MPWR": {"zh-TW": "Monolithic Power", "zh-CN": "芯源系统", "en-US": "MPS", "ja": "MPS"},
    "2345.TW": {"zh-TW": "智邦", "zh-CN": "智邦", "en-US": "Accton", "ja": "Accton"},
    "6285.TW": {"zh-TW": "啟碁", "zh-CN": "启碁", "en-US": "Wistron NeWeb", "ja": "Wistron NeWeb"},
    "CSCO": {"zh-TW": "思科", "zh-CN": "思科", "en-US": "Cisco", "ja": "シスコ"},
    "ANET": {"zh-TW": "Arista Networks", "zh-CN": "Arista Networks", "en-US": "Arista Networks", "ja": "アリスタネットワークス"},

    # --- 系統組裝與終端應用 ---
    "2317.TW": {"zh-TW": "鴻海", "zh-CN": "富士康", "en-US": "Foxconn (Hon Hai)", "ja": "鴻海（ホンハイ）"},
    "2382.TW": {"zh-TW": "廣達", "zh-CN": "广达", "en-US": "Quanta Computer", "ja": "クアンタ・コンピュータ"},
    "3231.TW": {"zh-TW": "緯創", "zh-CN": "纬创", "en-US": "Wistron", "ja": "Wistron"},
    "SMCI": {"zh-TW": "美超微", "zh-CN": "美超微", "en-US": "Super Micro", "ja": "スーパーマイクロ"},
    "DELL": {"zh-TW": "戴爾", "zh-CN": "戴尔", "en-US": "Dell", "ja": "デル"},
    "6702.T": {"zh-TW": "富士通", "zh-CN": "富士通", "en-US": "Fujitsu", "ja": "富士通"},
    "3008.TW": {"zh-TW": "大立光", "zh-CN": "大立光", "en-US": "Largan Precision", "ja": "Largan"},
    "002475.SZ": {"zh-TW": "立訊精密", "zh-CN": "立讯精密", "en-US": "Luxshare", "ja": "Luxshare"},
    "AAPL": {"zh-TW": "蘋果", "zh-CN": "苹果", "en-US": "Apple", "ja": "アップル"},
    "2356.TW": {"zh-TW": "英業達", "zh-CN": "英业达", "en-US": "Inventec", "ja": "Inventec"},
    "HPQ": {"zh-TW": "惠普", "zh-CN": "惠普", "en-US": "HP Inc.", "ja": "HP"},
    "2395.TW": {"zh-TW": "研華", "zh-CN": "研华", "en-US": "Advantech", "ja": "Advantech"},
    "6414.TW": {"zh-TW": "樺漢", "zh-CN": "桦汉", "en-US": "Ennoconn", "ja": "Ennoconn"},
    "6180.TWO": {"zh-TW": "橘子", "zh-CN": "橘子", "en-US": "Gamania", "ja": "Gamania"},
    "3293.TWO": {"zh-TW": "鈊象", "zh-CN": "铱象", "en-US": "IGS", "ja": "IGS"},
    "TTWO": {"zh-TW": "Take-Two Interactive", "zh-CN": "Take-Two Interactive", "en-US": "Take-Two Interactive", "ja": "テイクツー・インタラクティブ"},
    "7974.T": {"zh-TW": "任天堂", "zh-CN": "任天堂", "en-US": "Nintendo", "ja": "任天堂"},
    "036570.KS": {"zh-TW": "NCsoft", "zh-CN": "NCsoft", "en-US": "NCsoft", "ja": "NCソフト"},

    # --- 電動車、車用電子與能源 ---
    "3665.TW": {"zh-TW": "貿聯-KY", "zh-CN": "贸联", "en-US": "Bizlink", "ja": "Bizlink"},
    "2231.TW": {"zh-TW": "為升", "zh-CN": "为升", "en-US": "Weup", "ja": "Weup"},
    "002594.SZ": {"zh-TW": "比亞迪", "zh-CN": "比亚迪", "en-US": "BYD", "ja": "BYD"},
    "TSLA": {"zh-TW": "特斯拉", "zh-CN": "特斯拉", "en-US": "Tesla", "ja": "テスラ"},
    "6752.T": {"zh-TW": "Panasonic", "zh-CN": "松下", "en-US": "Panasonic", "ja": "パナソニック"},
    "006400.KS": {"zh-TW": "三星SDI", "zh-CN": "三星SDI", "en-US": "Samsung SDI", "ja": "サムスンSDI"},
    "NXPI": {"zh-TW": "恩智浦", "zh-CN": "恩智浦", "en-US": "NXP Semiconductors", "ja": "NXPセミコンダクターズ"},
    "6902.T": {"zh-TW": "電裝", "zh-CN": "电装", "en-US": "Denso", "ja": "デンソー"},
    "012330.KS": {"zh-TW": "現代摩比斯", "zh-CN": "现代摩比斯", "en-US": "Hyundai Mobis", "ja": "現代モービス"},
    "1519.TW": {"zh-TW": "華城", "zh-CN": "华城", "en-US": "Hua Cheng Electric", "ja": "Hua Cheng Electric"},
    "1503.TW": {"zh-TW": "士電", "zh-CN": "士电", "en-US": "Shihlin Electric", "ja": "Shihlin Electric"},
    "GEV": {"zh-TW": "GE Vernova", "zh-CN": "GE Vernova", "en-US": "GE Vernova", "ja": "GEバーノバ"},
    "6501.T": {"zh-TW": "日立製作所", "zh-CN": "日立制作所", "en-US": "Hitachi", "ja": "日立製作所"},
    "267260.KS": {"zh-TW": "HD現代電機", "zh-CN": "HD现代电机", "en-US": "HD Hyundai Electric", "ja": "HD現代電機"},
    "3576.TW": {"zh-TW": "聯合再生", "zh-CN": "联合再生", "en-US": "United Renewable Energy", "ja": "United Renewable Energy"},
    "601012.SS": {"zh-TW": "隆基綠能", "zh-CN": "隆基绿能", "en-US": "LONGi", "ja": "LONGi"},
    "FSLR": {"zh-TW": "First Solar", "zh-CN": "第一太阳能", "en-US": "First Solar", "ja": "ファーストソーラー"},
    "9958.TW": {"zh-TW": "世紀鋼", "zh-CN": "世纪钢", "en-US": "Century Iron & Steel", "ja": "Century Iron & Steel"},
    "300750.SZ": {"zh-TW": "寧德時代", "zh-CN": "宁德时代", "en-US": "CATL", "ja": "CATL"},
    "FLNC": {"zh-TW": "Fluence Energy", "zh-CN": "Fluence Energy", "en-US": "Fluence Energy", "ja": "フルエンスエナジー"},
    "2412.TW": {"zh-TW": "中華電", "zh-CN": "中华电信", "en-US": "Chunghwa Telecom", "ja": "中華電信"},
    "3045.TW": {"zh-TW": "台灣大", "zh-CN": "台湾大哥大", "en-US": "Taiwan Mobile", "ja": "台湾大哥大"},
    "VZ": {"zh-TW": "Verizon", "zh-CN": "Verizon", "en-US": "Verizon", "ja": "ベライゾン"},
    "9432.T": {"zh-TW": "NTT", "zh-CN": "日本电信电话", "en-US": "NTT", "ja": "NTT"},
    "017670.KS": {"zh-TW": "SK Telecom", "zh-CN": "SK Telecom", "en-US": "SK Telecom", "ja": "SKテレコム"},

    # --- 生醫、金融與傳產 ---
    "4174.TWO": {"zh-TW": "浩鼎", "zh-CN": "浩鼎", "en-US": "OBI Pharma", "ja": "OBI Pharma"},
    "1795.TW": {"zh-TW": "美時", "zh-CN": "美时", "en-US": "Lotus Pharmaceutical", "ja": "Lotus Pharmaceutical"},
    "XBI": {"zh-TW": "標普生技ETF", "zh-CN": "标普生技ETF", "en-US": "SPDR S&P Biotech ETF (XBI)", "ja": "XBI"},
    "4502.T": {"zh-TW": "武田藥品", "zh-CN": "武田药品", "en-US": "Takeda", "ja": "武田薬品"},
    "207940.KS": {"zh-TW": "三星生物製劑", "zh-CN": "三星生物制剂", "en-US": "Samsung Biologics", "ja": "サムスンバイオロジクス"},
    "4106.TW": {"zh-TW": "雃博", "zh-CN": "雃博", "en-US": "Apex Medical", "ja": "Apex Medical"},
    "1786.TW": {"zh-TW": "科妍", "zh-CN": "科妍", "en-US": "Scivision Biotech", "ja": "Scivision Biotech"},
    "MDT": {"zh-TW": "美敦力", "zh-CN": "美敦力", "en-US": "Medtronic", "ja": "メドトロニック"},
    "4543.T": {"zh-TW": "Terumo", "zh-CN": "泰尔茂", "en-US": "Terumo", "ja": "テルモ"},
    "2881.TW": {"zh-TW": "富邦金", "zh-CN": "富邦金控", "en-US": "Fubon Financial", "ja": "富邦金融ホールディングス"},
    "2882.TW": {"zh-TW": "國泰金", "zh-CN": "国泰金控", "en-US": "Cathay Financial", "ja": "国泰金融ホールディングス"},
    "601398.SS": {"zh-TW": "中國工商銀行", "zh-CN": "中国工商银行", "en-US": "ICBC", "ja": "中国工商銀行"},
    "XLF": {"zh-TW": "金融類股ETF", "zh-CN": "金融ETF", "en-US": "Financial Select Sector SPDR (XLF)", "ja": "XLF"},
    "8306.T": {"zh-TW": "三菱UFJ金融集團", "zh-CN": "三菱UFJ金融集团", "en-US": "MUFG", "ja": "三菱UFJフィナンシャル・グループ"},
    "105560.KS": {"zh-TW": "KB金融", "zh-CN": "KB金融", "en-US": "KB Financial", "ja": "KB金融"},
    "2603.TW": {"zh-TW": "長榮", "zh-CN": "长荣海运", "en-US": "Evergreen Marine", "ja": "エバーグリーン海運"},
    "2609.TW": {"zh-TW": "陽明", "zh-CN": "阳明海运", "en-US": "Yang Ming Marine", "ja": "陽明海運"},
    "ZIM": {"zh-TW": "ZIM以星航運", "zh-CN": "ZIM以星航运", "en-US": "ZIM Integrated Shipping", "ja": "ZIM"},
    "9101.T": {"zh-TW": "日本郵船", "zh-CN": "日本邮船", "en-US": "NYK Line", "ja": "日本郵船"},
    "011200.KS": {"zh-TW": "HMM", "zh-CN": "HMM", "en-US": "HMM", "ja": "HMM"},
    "2606.TW": {"zh-TW": "裕民", "zh-CN": "裕民", "en-US": "U-Ming Marine", "ja": "U-Ming Marine"},
    "2615.TW": {"zh-TW": "萬海", "zh-CN": "万海航运", "en-US": "Wan Hai Lines", "ja": "萬海航運"},
    "BOAT": {"zh-TW": "全球航運ETF", "zh-CN": "全球航运ETF", "en-US": "Breakwave Dry Bulk ETF (BOAT)", "ja": "BOAT"},
    "2610.TW": {"zh-TW": "華航", "zh-CN": "中华航空", "en-US": "China Airlines", "ja": "チャイナエアライン"},
    "2618.TW": {"zh-TW": "長榮航", "zh-CN": "长荣航空", "en-US": "EVA Air", "ja": "エバー航空"},
    "DAL": {"zh-TW": "達美航空", "zh-CN": "达美航空", "en-US": "Delta Air Lines", "ja": "デルタ航空"},
    "9201.T": {"zh-TW": "日本航空", "zh-CN": "日本航空", "en-US": "JAL", "ja": "日本航空"},
    "003490.KS": {"zh-TW": "大韓航空", "zh-CN": "大韩航空", "en-US": "Korean Air", "ja": "大韓航空"},
    "2002.TW": {"zh-TW": "中鋼", "zh-CN": "中钢", "en-US": "China Steel", "ja": "中国鋼鉄"},
    "2027.TW": {"zh-TW": "大成鋼", "zh-CN": "大成钢", "en-US": "Ta Chen Stainless Pipe", "ja": "Ta Chen"},
    "600019.SS": {"zh-TW": "寶山鋼鐵", "zh-CN": "宝山钢铁", "en-US": "Baosteel", "ja": "宝山鋼鉄"},
    "NUE": {"zh-TW": "紐克鋼鐵", "zh-CN": "纽克钢铁", "en-US": "Nucor", "ja": "ニューコア"},
    "5401.T": {"zh-TW": "日本製鐵", "zh-CN": "日本制铁", "en-US": "Nippon Steel", "ja": "日本製鉄"},
    "005490.KS": {"zh-TW": "POSCO控股", "zh-CN": "POSCO控股", "en-US": "POSCO Holdings", "ja": "POSCOホールディングス"},
    "1301.TW": {"zh-TW": "台塑", "zh-CN": "台塑", "en-US": "Formosa Plastics", "ja": "台湾プラスチック"},
    "1303.TW": {"zh-TW": "南亞", "zh-CN": "南亚塑胶", "en-US": "Nan Ya Plastics", "ja": "南亜プラスチック"},
    "600028.SS": {"zh-TW": "中國石化", "zh-CN": "中国石化", "en-US": "Sinopec", "ja": "中国石油化工"},
    "DOW": {"zh-TW": "陶氏化學", "zh-CN": "陶氏化学", "en-US": "Dow Inc.", "ja": "ダウ・ケミカル"},
    "051910.KS": {"zh-TW": "LG化學", "zh-CN": "LG化学", "en-US": "LG Chem", "ja": "LG化学"},
    "1101.TW": {"zh-TW": "台泥", "zh-CN": "台泥", "en-US": "Taiwan Cement", "ja": "台湾セメント"},
    "1102.TW": {"zh-TW": "亞泥", "zh-CN": "亚泥", "en-US": "Asia Cement", "ja": "アジアセメント"},
    "600585.SS": {"zh-TW": "海螺水泥", "zh-CN": "海螺水泥", "en-US": "Conch Cement", "ja": "海螺セメント"},

    # --- 民生消費 ---
    "1440.TW": {"zh-TW": "南紡", "zh-CN": "南纺", "en-US": "Nan Fang Textile", "ja": "Nan Fang Textile"},
    "1477.TW": {"zh-TW": "聚陽", "zh-CN": "聚阳", "en-US": "Makalot Industrial", "ja": "Makalot"},
    "1216.TW": {"zh-TW": "統一", "zh-CN": "统一企业", "en-US": "Uni-President", "ja": "統一企業"},
    "1201.TW": {"zh-TW": "味全", "zh-CN": "味全", "en-US": "Wei Chuan", "ja": "味全"},
    "2912.TW": {"zh-TW": "統一超", "zh-CN": "统一超商", "en-US": "President Chain Store (7-Eleven TW)", "ja": "統一超商"},
    "5903.TWO": {"zh-TW": "全家", "zh-CN": "全家便利店", "en-US": "FamilyMart Taiwan", "ja": "ファミリーマート台湾"},
    "XRT": {"zh-TW": "零售類股ETF", "zh-CN": "零售ETF", "en-US": "SPDR S&P Retail ETF (XRT)", "ja": "XRT"},
}

# 未收錄於 NAME_I18N_MAP 的代碼，以 yfinance .info 自動查詢英文簡稱的快取（避免重複查詢）
_shortname_fallback_cache = {}


def _fetch_fallback_english_name(ticker: str) -> str:
    """
    未收錄於靜態多語系對照表時的自動 fallback：
    以 yfinance 取得 info.get('shortName')，並簡單清理常見公司後綴。
    僅在真的缺表時才會呼叫（正常情況下 40 個板塊的既有標的皆已收錄，不會觸發）。
    """
    if ticker in _shortname_fallback_cache:
        return _shortname_fallback_cache[ticker]

    print(f"[提示] 代碼 {ticker} 未收錄於多語系名稱對照表，嘗試以 yfinance 自動取得英文名稱...")
    try:
        info = yf.Ticker(ticker).info
        short_name = info.get("shortName") or info.get("longName") or ticker
        for suffix in [", Ltd.", " Ltd.", " Co., Ltd.", " Corporation", " Corp.", " Inc.", " Co."]:
            if short_name.endswith(suffix):
                short_name = short_name[: -len(suffix)]
                break
    except Exception:
        print(f"[警告] {ticker} 自動取得英文名稱失敗，改以代碼本身代替")
        short_name = ticker

    _shortname_fallback_cache[ticker] = short_name
    return short_name


def get_ticker_name_i18n(ticker: str) -> dict:
    """回傳單一標的的四語系名稱 dict：{"zh-TW":..., "zh-CN":..., "en-US":..., "ja":...}"""
    if ticker in NAME_I18N_MAP:
        return NAME_I18N_MAP[ticker]
    fallback_name = _fetch_fallback_english_name(ticker)
    return {"zh-TW": fallback_name, "zh-CN": fallback_name, "en-US": fallback_name, "ja": fallback_name}

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
        sector_id = SECTOR_ID_MAP[sector_name]
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
                    "name": get_ticker_name_i18n(ticker),
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
                    "sector_id": sector_id,
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
            "sector_id": sector_id,
            "markets": market_blocks,
        })

        sector_raw_scores.append({
            "sector": sector_name,
            "sector_id": sector_id,
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
            "sector_id": s["sector_id"],
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
                "sector_id": r["sector_id"],
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
