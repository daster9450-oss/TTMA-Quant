import { useState, useEffect, useContext, createContext, CSSProperties } from "react"
import { addPropertyControls, ControlType } from "framer"

/**
 * TTMA-Quant「跨市場資金動能與板塊輪動」儀表板
 * Framer Code Component — 讀取 main.py 產出的 sector_data.json
 *
 * 不依賴 Tailwind 或任何外部 UI 函式庫，純內聯樣式 (Inline CSS)。
 */

// -----------------------------------------------------------------------
// 型別定義
// -----------------------------------------------------------------------
type TickerInfo = {
    symbol: string
    // 理論上由後端直接產生多語系物件（鍵值與 Lang 一致），但正式環境資料來源
    // 若尚未同步到新版後端，仍可能是舊版純中文字串，故型別放寬並由
    // getTranslatedText() 統一攔截處理，兩種格式都能正確顯示。
    name: Record<string, string> | string
    close: number
    pct_change: number
    volume: number
    turnover_usd: number
    as_of_date: string
}

type MarketBlock = {
    market_label: string
    tickers: TickerInfo[]
    weighted_change_pct: number
    as_of: string | null
}

type SectorRow = {
    sector: string // 後端 zh-TW 板塊名稱，僅作 sectorDict 缺值時的顯示 fallback
    sector_id: string // 板塊 ID，對應 sectorDict 查詢四語系板塊名稱
    markets: Record<string, MarketBlock>
}

type MomentumItem = {
    sector: string
    sector_id: string
    momentum_score: number
    weighted_change_pct: number
    turnover_usd: number
    vol_surge: number // 成交量放大倍率
    price_mom: number // 價格動能（%）
    weight_pct: number // 權重佔比（%）
    history_scores: number[] // 近 5 日動能分數，供 Sparkline 使用
}

type SectorData = {
    generated_at_utc: string
    fx_rates_usd_base: Record<string, number>
    cross_market_table: SectorRow[]
    momentum_ranking: MomentumItem[]
    market_momentum: Record<string, MomentumItem[]>
}

// -----------------------------------------------------------------------
// 多語系 (i18n)：自動偵測預設 ＋ 強制手動覆寫
// -----------------------------------------------------------------------
type Lang = "zh-TW" | "zh-CN" | "ja" | "en-US"

// 翻譯字典：所有靜態 UI 文字。術語一律採用全球金流／量化交易慣用語
// （動能 Momentum、板塊 Sector、資金流向 Capital Flow、權重 Weighting），
// 避免生硬直翻（例如中文避免「動力」「部門」）。
const TRANSLATIONS: Record<Lang, Record<string, string>> = {
    "zh-TW": {
        title: "跨市場資金動能與板塊輪動",
        updatedAt: "資料更新時間（UTC）：",
        tabAll: "全部市場",
        tabTW: "台股",
        tabCN: "中股",
        tabUS: "美股",
        tabJP: "日股",
        tabKR: "韓股",
        flowFilterLabel: "資金流向篩選",
        flowTop: "前 10 大熱門資金板塊",
        flowBottom: "後 10 大冷門資金板塊",
        crossMarketTableTitle: "跨市場連動表",
        sectorColumn: "板塊",
        momentumRankingTitle: "動能排行榜（跨市場綜合）",
        statSectorCount: "涵蓋板塊數",
        statSectorCountSub: "{market}目前追蹤板塊",
        statTopSector: "最高成交動能",
        statTopSectorSub: "動能分數排名第一",
        statTurnover: "板塊成交金額合計",
        statTurnoverSub: "換算美元 (USD)",
        statBenchmark: "研究基準",
        marketNoteTW: "日成交資料 · 上市與上櫃",
        marketNoteCN: "日成交資料 · 滬深兩市",
        marketNoteUS: "美股 T-1 收盤對齊亞股 T 日",
        marketNoteJP: "日成交資料",
        marketNoteKR: "日成交資料",
        singleMarketRankingTitle: "{market}細分板塊動能排行",
        badgeTop: "前 10 大熱門",
        badgeBottom: "後 10 大冷門",
        sectorCountUnit: "{count} 個板塊",
        constituentCountTitle: "成分股明細（{count} 檔）",
        constituentCountLine: "{count} 檔成分股 · 點擊{action}明細",
        actionExpand: "展開",
        actionCollapse: "收合",
        noDataForMarket: "目前尚無{market}板塊資料。",
        loadingText: "資料載入中，正在同步跨市場金流數據...",
        errorTitle: "資料載入失敗",
        unknownError: "未知錯誤",
        momentumScoreLabel: "動能分數",
        tooltipVolSurge: "成交量放大",
        tooltipPriceMom: "價格動能",
        tooltipWeight: "權重佔比",
        unitTimes: "倍",
    },
    "zh-CN": {
        title: "跨市场资金动能与板块轮动",
        updatedAt: "数据更新时间（UTC）：",
        tabAll: "全部市场",
        tabTW: "台股",
        tabCN: "中股",
        tabUS: "美股",
        tabJP: "日股",
        tabKR: "韩股",
        flowFilterLabel: "资金流向筛选",
        flowTop: "前 10 大热门资金板块",
        flowBottom: "后 10 大冷门资金板块",
        crossMarketTableTitle: "跨市场联动表",
        sectorColumn: "板块",
        momentumRankingTitle: "动能排行榜（跨市场综合）",
        statSectorCount: "涵盖板块数",
        statSectorCountSub: "{market}目前追踪板块",
        statTopSector: "最高成交动能",
        statTopSectorSub: "动能分数排名第一",
        statTurnover: "板块成交金额合计",
        statTurnoverSub: "折算美元 (USD)",
        statBenchmark: "研究基准",
        marketNoteTW: "日成交数据 · 上市与上柜",
        marketNoteCN: "日成交数据 · 沪深两市",
        marketNoteUS: "美股 T-1 收盘对齐亚股 T 日",
        marketNoteJP: "日成交数据",
        marketNoteKR: "日成交数据",
        singleMarketRankingTitle: "{market}细分板块动能排行",
        badgeTop: "前 10 大热门",
        badgeBottom: "后 10 大冷门",
        sectorCountUnit: "{count} 个板块",
        constituentCountTitle: "成分股明细（{count} 只）",
        constituentCountLine: "{count} 只成分股 · 点击{action}明细",
        actionExpand: "展开",
        actionCollapse: "收起",
        noDataForMarket: "目前尚无{market}板块数据。",
        loadingText: "数据载入中，正在同步跨市场资金流数据...",
        errorTitle: "数据载入失败",
        unknownError: "未知错误",
        momentumScoreLabel: "动能分数",
        tooltipVolSurge: "成交量放大",
        tooltipPriceMom: "价格动能",
        tooltipWeight: "权重占比",
        unitTimes: "倍",
    },
    ja: {
        title: "クロスマーケット資金モメンタム＆セクターローテーション",
        updatedAt: "データ更新時刻（UTC）：",
        tabAll: "全市場",
        tabTW: "台湾株",
        tabCN: "中国株",
        tabUS: "米国株",
        tabJP: "日本株",
        tabKR: "韓国株",
        flowFilterLabel: "資金フロー絞り込み",
        flowTop: "資金流入上位10セクター",
        flowBottom: "資金流出下位10セクター",
        crossMarketTableTitle: "クロスマーケット連動表",
        sectorColumn: "セクター",
        momentumRankingTitle: "モメンタムランキング（クロスマーケット総合）",
        statSectorCount: "対象セクター数",
        statSectorCountSub: "{market}の追跡対象セクター",
        statTopSector: "最高モメンタムセクター",
        statTopSectorSub: "モメンタムスコア第1位",
        statTurnover: "セクター合計売買代金",
        statTurnoverSub: "米ドル換算 (USD)",
        statBenchmark: "基準日",
        marketNoteTW: "日次売買データ・上場及び店頭",
        marketNoteCN: "日次売買データ・上海深セン両市場",
        marketNoteUS: "米国株T-1終値をアジア株T日に整合",
        marketNoteJP: "日次売買データ",
        marketNoteKR: "日次売買データ",
        singleMarketRankingTitle: "{market}セクター別モメンタムランキング",
        badgeTop: "資金流入上位10",
        badgeBottom: "資金流出下位10",
        sectorCountUnit: "{count} セクター",
        constituentCountTitle: "構成銘柄詳細（{count} 銘柄）",
        constituentCountLine: "構成銘柄 {count} 件 · クリックで{action}",
        actionExpand: "詳細を表示",
        actionCollapse: "折りたたむ",
        noDataForMarket: "現在{market}のセクターデータはありません。",
        loadingText: "データ読み込み中、クロスマーケット資金フローを同期しています...",
        errorTitle: "データの読み込みに失敗しました",
        unknownError: "不明なエラー",
        momentumScoreLabel: "モメンタムスコア",
        tooltipVolSurge: "出来高倍率",
        tooltipPriceMom: "価格モメンタム",
        tooltipWeight: "ウェイト比率",
        unitTimes: "倍",
    },
    "en-US": {
        title: "Cross-Market Capital Momentum & Sector Rotation",
        updatedAt: "Data Updated (UTC): ",
        tabAll: "All Markets",
        tabTW: "Taiwan",
        tabCN: "China",
        tabUS: "US",
        tabJP: "Japan",
        tabKR: "Korea",
        flowFilterLabel: "Capital Flow Filter",
        flowTop: "Top 10 Capital Inflow Sectors",
        flowBottom: "Bottom 10 Capital Outflow Sectors",
        crossMarketTableTitle: "Cross-Market Correlation Table",
        sectorColumn: "Sector",
        momentumRankingTitle: "Momentum Ranking (Cross-Market)",
        statSectorCount: "Sectors Covered",
        statSectorCountSub: "Sectors tracked in {market}",
        statTopSector: "Top Momentum Sector",
        statTopSectorSub: "#1 by Momentum Score",
        statTurnover: "Total Sector Turnover",
        statTurnoverSub: "Converted to USD",
        statBenchmark: "Benchmark Date",
        marketNoteTW: "Daily Data · Listed & OTC",
        marketNoteCN: "Daily Data · Shanghai & Shenzhen",
        marketNoteUS: "US T-1 Close Aligned to Asia T-Day",
        marketNoteJP: "Daily Data",
        marketNoteKR: "Daily Data",
        singleMarketRankingTitle: "{market} Sector Momentum Ranking",
        badgeTop: "Top 10 Inflow",
        badgeBottom: "Bottom 10 Outflow",
        sectorCountUnit: "{count} Sectors",
        constituentCountTitle: "Constituent Details ({count})",
        constituentCountLine: "{count} Constituents · Click to {action}",
        actionExpand: "expand",
        actionCollapse: "collapse",
        noDataForMarket: "No sector data available for {market} yet.",
        loadingText: "Loading data, syncing cross-market capital flows...",
        errorTitle: "Failed to Load Data",
        unknownError: "Unknown error",
        momentumScoreLabel: "Momentum Score",
        tooltipVolSurge: "Volume Surge",
        tooltipPriceMom: "Price Momentum",
        tooltipWeight: "Weighting",
        unitTimes: "x",
    },
}

// 依 key 取翻譯字串，並以 {placeholder} 語法代入動態變數；若當前語系缺字則退回英文，仍缺則回傳 key 本身
function translate(lang: Lang, key: string, vars?: Record<string, string | number>): string {
    const dict = TRANSLATIONS[lang] || TRANSLATIONS["en-US"]
    let template = dict[key] ?? TRANSLATIONS["en-US"][key] ?? key
    if (vars) {
        for (const k of Object.keys(vars)) {
            template = template.split(`{${k}}`).join(String(vars[k]))
        }
    }
    return template
}

// 自動偵測：讀取 navigator.language，日文 → ja／簡體中文 → zh-CN／繁體中文 → zh-TW，其餘一律退回 en-US
function detectInitialLang(): Lang {
    if (typeof navigator === "undefined") return "en-US"
    const raw = (navigator.language || (navigator as any).userLanguage || "").toLowerCase()
    if (raw.startsWith("ja")) return "ja"
    if (raw.startsWith("zh")) {
        if (raw.includes("cn") || raw.includes("hans") || raw.includes("sg")) return "zh-CN"
        return "zh-TW"
    }
    return "en-US"
}

const LangContext = createContext<Lang>("en-US")

// 供子元件使用：回傳綁定當前語系 Context 的翻譯函式 t(key, vars)
function useT() {
    const lang = useContext(LangContext)
    return (key: string, vars?: Record<string, string | number>) => translate(lang, key, vars)
}

// -----------------------------------------------------------------------
// 視覺樣式常數
// -----------------------------------------------------------------------
const COLOR_BG = "#0B0F17"
const COLOR_PANEL = "#0F141F"
const COLOR_PANEL_RAISED = "#131A28"
const COLOR_BORDER = "#1C2333"
const COLOR_ACCENT = "#00F2FE"
const COLOR_TEXT_PRIMARY = "#E6EDF7"
const COLOR_TEXT_SECONDARY = "#7C8AA5"
const COLOR_UP = "#FF4D4F" // 上漲：紅色
const COLOR_DOWN = "#00E396" // 下跌：綠色
const COLOR_FLAT = "#7C8AA5"

const FONT_STACK =
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang TC', 'Microsoft JhengHei', Roboto, Arial, sans-serif"

// 跨市場欄位顯示順序：台、中、美、日、韓
const MARKET_ORDER = ["TW", "CN", "US", "JP", "KR"]

// 市場代碼 → 語系字典鍵值對照（市場名稱與研究基準備註皆透過字典翻譯，而非寫死中文）
const MARKET_LABEL_KEYS: Record<string, string> = {
    TW: "tabTW",
    CN: "tabCN",
    US: "tabUS",
    JP: "tabJP",
    KR: "tabKR",
}

const MARKET_NOTE_KEYS: Record<string, string> = {
    TW: "marketNoteTW",
    CN: "marketNoteCN",
    US: "marketNoteUS",
    JP: "marketNoteJP",
    KR: "marketNoteKR",
}

// -----------------------------------------------------------------------
// 板塊 (Sector) 專用精簡字典：個股名稱已由後端多語系化，前端只需依
// 後端傳來的 sector_id 對應四語系板塊名稱。術語一律採全球金融市場／
// 量化交易慣用語（中文：晶圓代工／貨櫃航運；日文採日本券商慣用語；
// 英文採華爾街慣用語），絕不機器直翻。
// -----------------------------------------------------------------------
const SECTOR_DICT: Record<string, Record<Lang, string>> = {
    wafer_foundry: { "zh-TW": "晶圓代工", "zh-CN": "晶圆代工", ja: "半導体ファウンドリ", "en-US": "Semiconductor Foundry" },
    ic_design: { "zh-TW": "IC設計", "zh-CN": "IC设计", ja: "ファブレス半導体設計", "en-US": "Fabless IC Design" },
    memory: { "zh-TW": "記憶體", "zh-CN": "存储器", ja: "メモリ半導体", "en-US": "Memory Semiconductors" },
    advanced_packaging: { "zh-TW": "先進封裝", "zh-CN": "先进封装", ja: "先端パッケージング", "en-US": "Advanced Packaging" },
    ic_substrate: { "zh-TW": "IC載板", "zh-CN": "IC载板", ja: "ICサブストレート", "en-US": "IC Substrate" },
    semiconductor_equipment: { "zh-TW": "半導體設備", "zh-CN": "半导体设备", ja: "半導体製造装置", "en-US": "Semiconductor Equipment" },
    semiconductor_materials: { "zh-TW": "半導體材料", "zh-CN": "半导体材料", ja: "半導体材料", "en-US": "Semiconductor Materials" },
    passive_components: { "zh-TW": "被動元件", "zh-CN": "被动元件", ja: "受動部品", "en-US": "Passive Components" },
    pcb: { "zh-TW": "PCB印刷電路板", "zh-CN": "PCB印制电路板", ja: "プリント基板(PCB)", "en-US": "Printed Circuit Boards (PCB)" },
    connectors: { "zh-TW": "連接器", "zh-CN": "连接器", ja: "コネクタ", "en-US": "Connectors" },
    display_panel: { "zh-TW": "面板顯示器", "zh-CN": "面板显示器", ja: "ディスプレイパネル", "en-US": "Display Panels" },
    led: { "zh-TW": "LED", "zh-CN": "LED", ja: "LED", "en-US": "LED" },
    optical_communication: { "zh-TW": "光通訊與光模組", "zh-CN": "光通信与光模块", ja: "光通信および光モジュール", "en-US": "Optical Communication & Modules" },
    thermal_cooling: { "zh-TW": "散熱液冷", "zh-CN": "散热液冷", ja: "熱対策・液冷", "en-US": "Thermal Management & Liquid Cooling" },
    power_supply: { "zh-TW": "電源供應器", "zh-CN": "电源供应器", ja: "電源装置", "en-US": "Power Supplies" },
    networking_equipment: { "zh-TW": "網通設備", "zh-CN": "网通设备", ja: "ネットワーク機器", "en-US": "Networking Equipment" },
    ai_server_cloud_infra: { "zh-TW": "AI伺服器與雲端基建", "zh-CN": "AI服务器与云端基建", ja: "AIサーバー及びクラウドインフラ", "en-US": "AI Servers & Cloud Infrastructure" },
    smartphone_apple_supply_chain: { "zh-TW": "手機組裝/蘋果供應鏈", "zh-CN": "手机组装/苹果供应链", ja: "スマートフォン組立・アップル関連銘柄", "en-US": "Smartphone Assembly / Apple Supply Chain" },
    notebook_odm: { "zh-TW": "筆電代工", "zh-CN": "笔记本代工", ja: "ノートPC受託生産(ODM)", "en-US": "Notebook ODM" },
    industrial_pc: { "zh-TW": "工業電腦", "zh-CN": "工业电脑", ja: "産業用PC", "en-US": "Industrial PC" },
    gaming_digital_content: { "zh-TW": "遊戲與數位內容", "zh-CN": "游戏与数字内容", ja: "ゲーム・デジタルコンテンツ", "en-US": "Gaming & Digital Content" },
    ev_supply_chain: { "zh-TW": "電動車供應鏈", "zh-CN": "电动车供应链", ja: "EVサプライチェーン", "en-US": "EV Supply Chain" },
    automotive_electronics: { "zh-TW": "車用電子", "zh-CN": "车用电子", ja: "車載エレクトロニクス", "en-US": "Automotive Electronics" },
    heavy_electric_grid: { "zh-TW": "重電與電網", "zh-CN": "重型电机与电网", ja: "重電・電力インフラ", "en-US": "Heavy Electric & Grid Infrastructure" },
    solar: { "zh-TW": "太陽能", "zh-CN": "太阳能", ja: "太陽光発電", "en-US": "Solar" },
    wind_power: { "zh-TW": "風電", "zh-CN": "风电", ja: "風力発電", "en-US": "Wind Power" },
    energy_storage: { "zh-TW": "儲能", "zh-CN": "储能", ja: "蓄電池・エネルギー貯蔵", "en-US": "Energy Storage" },
    telecom: { "zh-TW": "電信", "zh-CN": "电信", ja: "通信キャリア", "en-US": "Telecom" },
    biotech_pharma: { "zh-TW": "生技新藥", "zh-CN": "生物科技新药", ja: "バイオ・新薬", "en-US": "Biotech & Pharmaceuticals" },
    medical_devices: { "zh-TW": "醫療器材", "zh-CN": "医疗器材", ja: "医療機器", "en-US": "Medical Devices" },
    financials: { "zh-TW": "金融", "zh-CN": "金融", ja: "金融", "en-US": "Financials" },
    container_shipping: { "zh-TW": "貨櫃航運", "zh-CN": "集装箱航运", ja: "コンテナ船", "en-US": "Container Shipping" },
    dry_bulk_shipping: { "zh-TW": "散裝航運", "zh-CN": "散货航运", ja: "バラ積み船(ドライバルク)", "en-US": "Dry Bulk Shipping" },
    airlines: { "zh-TW": "航空", "zh-CN": "航空", ja: "航空", "en-US": "Airlines" },
    steel: { "zh-TW": "鋼鐵", "zh-CN": "钢铁", ja: "鉄鋼", "en-US": "Steel" },
    petrochemicals: { "zh-TW": "塑化", "zh-CN": "石化", ja: "石油化学", "en-US": "Petrochemicals" },
    cement: { "zh-TW": "水泥", "zh-CN": "水泥", ja: "セメント", "en-US": "Cement" },
    textiles: { "zh-TW": "紡織", "zh-CN": "纺织", ja: "繊維", "en-US": "Textiles" },
    food: { "zh-TW": "食品", "zh-CN": "食品", ja: "食品", "en-US": "Food" },
    retail: { "zh-TW": "零售通路", "zh-CN": "零售通路", ja: "小売", "en-US": "Retail" },
}

// 讀取當前語系 Context（不透過 useT，因為這裡需要 lang 本身而非翻譯後字串）
function useLang(): Lang {
    return useContext(LangContext)
}

// -----------------------------------------------------------------------
// 動態資料翻譯攔截層：後端理論上會直接送出多語系物件（見 main.py 的
// NAME_I18N_MAP／sector_id），但正式環境的資料來源（例如自動排程尚未
// 同步到最新版本）仍可能傳回舊版純中文字串。此處建立一個以「原始繁中
// 字串」為鍵的字典，作為前端最後一道安全網：無論後端送來的是新版物件
// 或舊版字串，畫面上一律能顯示正確語系，且絕不因未知詞彙而報錯。
//
// ⚠️ 所有語言（en-US／ja／zh-CN／zh-TW）一律採全球金融市場與量化交易
// 標準專業慣用語：英文採華爾街投行慣用語、日文採日本券商與財經媒體
// 慣用詞彙、簡體中文嚴格採 A 股市場與主流券商（如申萬行業分類）慣用
// 術語，並特別區分兩岸金融／半導體用語差異，不以繁轉簡敷衍帶過。
// -----------------------------------------------------------------------
const dynamicDict: Record<string, Partial<Record<Lang, string>>> = {
    // --- 板塊類：與 SECTOR_DICT（依 sector_id 查詢）完全同步，
    //     此處自動衍生，確保兩套字典的專業術語永遠一致、不會分岔 ---
    ...Object.fromEntries(Object.values(SECTOR_DICT).map((entry) => [entry["zh-TW"], entry])),

    // --- 個股類：後端多語系物件尚未涵蓋、或資料來源為舊版純字串時的
    //     專用對照。台股個股一律採國際金融市場通用英文縮寫／拼音，
    //     簡體中文採該公司於中國大陸市場的官方或慣用簡稱 ---
    "裕民": { "zh-TW": "裕民", "zh-CN": "裕民海运", "en-US": "U-Ming Marine", ja: "U-Ming Marine" },
    "萬海": { "zh-TW": "萬海", "zh-CN": "万海航运", "en-US": "Wan Hai Lines", ja: "Wan Hai Lines" },
    "長榮": { "zh-TW": "長榮", "zh-CN": "长荣海运", "en-US": "Evergreen Marine", ja: "Evergreen Marine" },
    "陽明": { "zh-TW": "陽明", "zh-CN": "阳明海运", "en-US": "Yang Ming Marine", ja: "Yang Ming Marine" },
    "全新": { "zh-TW": "全新", "zh-CN": "全新光电", "en-US": "Epistar", ja: "Epistar" },
    "欣興": { "zh-TW": "欣興", "zh-CN": "欣兴电子", "en-US": "Unimicron", ja: "Unimicron" },
    "南電": { "zh-TW": "南電", "zh-CN": "南亚电路板", "en-US": "Nan Ya PCB", ja: "Nan Ya PCB" },
    "中華電": { "zh-TW": "中華電", "zh-CN": "中华电信", "en-US": "Chunghwa Telecom", ja: "Chunghwa Telecom" },
    "台灣大": { "zh-TW": "台灣大", "zh-CN": "台湾大哥大", "en-US": "Taiwan Mobile", ja: "Taiwan Mobile" },
    "奇鋐": { "zh-TW": "奇鋐", "zh-CN": "奇鋐科技", "en-US": "Auras Technology", ja: "Auras Technology" },
    "雙鴻": { "zh-TW": "雙鴻", "zh-CN": "双鸿科技", "en-US": "AVC (Asia Vital Components)", ja: "AVC" },
    "國巨": { "zh-TW": "國巨", "zh-CN": "国巨股份", "en-US": "Yageo Corporation", ja: "Yageo" },
    "華新科": { "zh-TW": "華新科", "zh-CN": "华新科技", "en-US": "Walsin Technology", ja: "Walsin Technology" },
    "全球航運ETF": { "zh-TW": "全球航運ETF", "zh-CN": "全球航运ETF", "en-US": "Global Shipping ETF", ja: "グローバル海運ETF" },
    "ZIM以星航運": { "zh-TW": "ZIM以星航運", "zh-CN": "以星航运", "en-US": "ZIM Integrated Shipping", ja: "ZIM" },
}

// 強健的動態資料翻譯攔截函數：
// 1) text 已是多語系物件（後端新版 API、或下方 resolveSectorInput 解析出的 SECTOR_DICT 項目）→ 依語系取值。
// 2) text 是純字串（後端舊版資料格式）→ 查 dynamicDict 取得專業翻譯。
// 3) 上述皆查無資料 → 原樣回傳輸入字串，確保任何未知詞彙都不會讓畫面壞掉或拋出例外。
function getTranslatedText(text: any, lang: string): string {
    if (text && typeof text === "object") {
        return text[lang] || text["en-US"] || text["zh-TW"] || ""
    }
    if (typeof text === "string") {
        const entry = dynamicDict[text]
        if (entry) {
            return entry[lang as Lang] || entry["en-US"] || text
        }
        return text
    }
    return text ?? ""
}

// 板塊顯示前的輸入解析：sector_id 存在時優先回傳 SECTOR_DICT 的完整多語系物件
// （較權威、四語系保證齊全）；否則回傳後端傳來的原始字串，交給 getTranslatedText
// 走 dynamicDict 查表這條路徑。呼叫端一律透過 getTranslatedText 輸出，見下方 return 區塊。
function resolveSectorInput(sectorId: string | undefined, fallbackText: string): any {
    return sectorId && SECTOR_DICT[sectorId] ? SECTOR_DICT[sectorId] : fallbackText
}

// 市場切換頁籤：全部市場 + 使用者指定的四個市場（不含中股，中股僅保留於跨市場對比表欄位）
const MARKET_TABS: { key: string; labelKey: string }[] = [
    { key: "ALL", labelKey: "tabAll" },
    { key: "TW", labelKey: "tabTW" },
    { key: "CN", labelKey: "tabCN" },
    { key: "US", labelKey: "tabUS" },
    { key: "JP", labelKey: "tabJP" },
    { key: "KR", labelKey: "tabKR" },
]

// -----------------------------------------------------------------------
// 共用小元件
// -----------------------------------------------------------------------
function formatUsd(value: number): string {
    if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(2)}B`
    if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
    if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`
    return `$${value.toFixed(0)}`
}

function PctChangeTag({ value, size = 13 }: { value: number; size?: number }) {
    const isUp = value > 0
    const isDown = value < 0
    const color = isUp ? COLOR_UP : isDown ? COLOR_DOWN : COLOR_FLAT
    const sign = isUp ? "+" : isDown ? "-" : ""
    const display = `${sign}${Math.abs(value).toFixed(2)}%`
    return (
        <span
            style={{
                color,
                fontWeight: 600,
                fontVariantNumeric: "tabular-nums",
                fontSize: size,
                whiteSpace: "nowrap",
            }}
        >
            {display}
        </span>
    )
}

// 迷你趨勢線（Sparkline）：不含座標軸，僅呈現近 5 日動能分數走勢
function Sparkline({
    values,
    color = COLOR_ACCENT,
    width = 60,
    height = 20,
}: {
    values: number[]
    color?: string
    width?: number
    height?: number
}) {
    if (!values || values.length < 2) return null

    const min = Math.min(...values)
    const max = Math.max(...values)
    const range = max - min
    const stepX = width / (values.length - 1)
    const points = values
        .map((v, i) => {
            const x = i * stepX
            const y = range < 1e-9 ? height / 2 : height - ((v - min) / range) * height
            return `${x.toFixed(1)},${y.toFixed(1)}`
        })
        .join(" ")

    return (
        <svg
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            style={{ display: "block", flexShrink: 0, overflow: "visible" }}
        >
            <polyline
                points={points}
                fill="none"
                stroke={color}
                strokeWidth={1.5}
                strokeLinejoin="round"
                strokeLinecap="round"
                opacity={0.9}
            />
        </svg>
    )
}

// 動能分數 + 懸浮提示（成交量放大 / 價格動能 / 權重佔比）+ 迷你趨勢線
function MomentumScoreDisplay({ item }: { item: MomentumItem }) {
    const t = useT()
    const [hovered, setHovered] = useState(false)
    const volSurge = item.vol_surge ?? 0
    const priceMom = item.price_mom ?? item.weighted_change_pct ?? 0
    const weightPct = item.weight_pct ?? 0
    const tooltipText = `${t("tooltipVolSurge")}：${volSurge.toFixed(1)}${t("unitTimes")} | ${t(
        "tooltipPriceMom"
    )}：${priceMom > 0 ? "+" : ""}${priceMom.toFixed(2)}% | ${t("tooltipWeight")}：${weightPct.toFixed(0)}%`

    return (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8 }}>
            {item.history_scores && item.history_scores.length >= 2 && (
                <Sparkline values={item.history_scores} />
            )}
            <div
                style={{ position: "relative", cursor: "default" }}
                onMouseEnter={() => setHovered(true)}
                onMouseLeave={() => setHovered(false)}
            >
                <span style={{ fontSize: 10, color: COLOR_TEXT_SECONDARY, whiteSpace: "nowrap" }}>
                    {t("momentumScoreLabel")} {item.momentum_score.toFixed(1)} / 100
                </span>
                {hovered && (
                    <div
                        style={{
                            position: "absolute",
                            bottom: "calc(100% + 6px)",
                            right: 0,
                            padding: "6px 10px",
                            borderRadius: 6,
                            background: COLOR_PANEL_RAISED,
                            border: `1px solid ${COLOR_ACCENT}`,
                            color: COLOR_TEXT_PRIMARY,
                            fontSize: 10,
                            whiteSpace: "nowrap",
                            zIndex: 20,
                            boxShadow: "0 4px 14px rgba(0,0,0,0.4)",
                            pointerEvents: "none",
                        }}
                    >
                        {tooltipText}
                    </div>
                )}
            </div>
        </div>
    )
}

function LoadingState() {
    const t = useT()
    return (
        <div
            style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                minHeight: 320,
                gap: 12,
                color: COLOR_TEXT_SECONDARY,
                fontFamily: FONT_STACK,
            }}
        >
            <div
                style={{
                    width: 28,
                    height: 28,
                    borderRadius: "50%",
                    border: `3px solid ${COLOR_BORDER}`,
                    borderTopColor: COLOR_ACCENT,
                    animation: "ttma-spin 0.9s linear infinite",
                }}
            />
            <div style={{ fontSize: 13, letterSpacing: 0.5 }}>{t("loadingText")}</div>
            <style>{`@keyframes ttma-spin { to { transform: rotate(360deg); } }`}</style>
        </div>
    )
}

function ErrorState({ message }: { message: string }) {
    const t = useT()
    return (
        <div
            style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                minHeight: 320,
                gap: 8,
                color: COLOR_UP,
                fontFamily: FONT_STACK,
                textAlign: "center",
                padding: 24,
            }}
        >
            <div style={{ fontSize: 15, fontWeight: 600 }}>{t("errorTitle")}</div>
            <div style={{ fontSize: 12, color: COLOR_TEXT_SECONDARY }}>{message}</div>
        </div>
    )
}

// -----------------------------------------------------------------------
// 市場切換頁籤
// -----------------------------------------------------------------------
function MarketTabs({
    selected,
    onSelect,
}: {
    selected: string
    onSelect: (key: string) => void
}) {
    const t = useT()
    return (
        <div
            style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
            }}
        >
            {MARKET_TABS.map((tab) => {
                const isActive = tab.key === selected
                return (
                    <button
                        key={tab.key}
                        onClick={() => onSelect(tab.key)}
                        style={{
                            padding: "8px 18px",
                            borderRadius: 8,
                            fontSize: 13,
                            fontWeight: 700,
                            letterSpacing: 0.3,
                            cursor: "pointer",
                            border: isActive
                                ? `1px solid ${COLOR_ACCENT}`
                                : `1px solid ${COLOR_BORDER}`,
                            background: isActive ? "rgba(0,242,254,0.12)" : COLOR_PANEL,
                            color: isActive ? COLOR_ACCENT : COLOR_TEXT_SECONDARY,
                            transition: "all 0.15s ease",
                            fontFamily: FONT_STACK,
                        }}
                    >
                        {t(tab.labelKey)}
                    </button>
                )
            })}
        </div>
    )
}

// -----------------------------------------------------------------------
// 資金流向篩選（Top 10 / Bottom 10）— 膠囊切換按鈕，視覺層級略小於國家頁籤
// -----------------------------------------------------------------------
const FLOW_FILTER_OPTIONS: { key: "top" | "bottom"; labelKey: string }[] = [
    { key: "top", labelKey: "flowTop" },
    { key: "bottom", labelKey: "flowBottom" },
]

function FlowFilterToggle({
    selected,
    onSelect,
}: {
    selected: "top" | "bottom"
    onSelect: (key: "top" | "bottom") => void
}) {
    const t = useT()
    return (
        <div
            style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 8,
            }}
        >
            <span
                style={{
                    fontSize: 11,
                    color: COLOR_TEXT_SECONDARY,
                    letterSpacing: 0.3,
                }}
            >
                {t("flowFilterLabel")}
            </span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {FLOW_FILTER_OPTIONS.map((opt) => {
                    const isActive = opt.key === selected
                    return (
                        <button
                            key={opt.key}
                            onClick={() => onSelect(opt.key)}
                            style={{
                                padding: "5px 14px",
                                borderRadius: 999,
                                fontSize: 11,
                                fontWeight: 600,
                                letterSpacing: 0.2,
                                cursor: "pointer",
                                border: isActive
                                    ? `1px solid ${COLOR_ACCENT}`
                                    : `1px solid ${COLOR_BORDER}`,
                                background: isActive ? "rgba(0,242,254,0.10)" : "transparent",
                                color: isActive ? COLOR_ACCENT : COLOR_TEXT_SECONDARY,
                                transition: "all 0.15s ease",
                                fontFamily: FONT_STACK,
                            }}
                        >
                            {t(opt.labelKey)}
                        </button>
                    )
                })}
            </div>
        </div>
    )
}

// -----------------------------------------------------------------------
// 語言切換器（右上角，極簡樣式，強制手動覆寫語系）
// -----------------------------------------------------------------------
const LANG_TOGGLE_OPTIONS: { key: Lang; label: string }[] = [
    { key: "en-US", label: "EN" },
    { key: "zh-TW", label: "繁" },
    { key: "zh-CN", label: "簡" },
    { key: "ja", label: "JP" },
]

function LangSwitcher({ lang, onSelect }: { lang: Lang; onSelect: (l: Lang) => void }) {
    return (
        <div
            style={{
                display: "flex",
                alignItems: "center",
                gap: 2,
                border: `1px solid ${COLOR_BORDER}`,
                borderRadius: 8,
                padding: "3px 6px",
                background: COLOR_PANEL,
            }}
        >
            <span style={{ fontSize: 12, marginRight: 2 }}>🌍</span>
            {LANG_TOGGLE_OPTIONS.map((opt, i) => {
                const isActive = opt.key === lang
                return (
                    <button
                        key={opt.key}
                        onClick={() => onSelect(opt.key)}
                        style={{
                            border: "none",
                            borderLeft: i > 0 ? `1px solid ${COLOR_BORDER}` : "none",
                            background: "transparent",
                            cursor: "pointer",
                            fontSize: 11,
                            fontWeight: isActive ? 800 : 500,
                            color: isActive ? COLOR_ACCENT : COLOR_TEXT_SECONDARY,
                            padding: "2px 8px",
                            fontFamily: FONT_STACK,
                        }}
                    >
                        {opt.label}
                    </button>
                )
            })}
        </div>
    )
}

// 依「動能分數」排序並截斷為前/後 10 筆（單一市場板塊列表用）
function sortMomentumItems(
    items: MomentumItem[],
    filter: "top" | "bottom"
): MomentumItem[] {
    const sorted = [...items].sort((a, b) =>
        filter === "top"
            ? b.momentum_score - a.momentum_score
            : a.momentum_score - b.momentum_score
    )
    return sorted.slice(0, 10)
}

// 依「動能分數」排序並截斷為前/後 10 筆（跨市場連動表用：以 momentum_ranking 對照分數）
function sortSectorRowsByFlow(
    rows: SectorRow[],
    momentumRanking: MomentumItem[],
    filter: "top" | "bottom"
): SectorRow[] {
    const scoreBySector: Record<string, number> = {}
    momentumRanking.forEach((m) => {
        scoreBySector[m.sector_id] = m.momentum_score
    })
    const sorted = [...rows].sort((a, b) => {
        const scoreA = scoreBySector[a.sector_id] ?? 0
        const scoreB = scoreBySector[b.sector_id] ?? 0
        return filter === "top" ? scoreB - scoreA : scoreA - scoreB
    })
    return sorted.slice(0, 10)
}

// -----------------------------------------------------------------------
// 統計卡片列（單一市場檢視用）
// -----------------------------------------------------------------------
function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
    return (
        <div
            style={{
                flex: "1 1 160px",
                minWidth: 140,
                border: `1px solid ${COLOR_BORDER}`,
                borderRadius: 10,
                background: COLOR_PANEL,
                padding: "14px 16px",
                display: "flex",
                flexDirection: "column",
                gap: 6,
            }}
        >
            <div
                style={{
                    fontSize: 10,
                    color: COLOR_TEXT_SECONDARY,
                    letterSpacing: 0.5,
                }}
            >
                {label}
            </div>
            <div
                style={{
                    fontSize: 18,
                    fontWeight: 800,
                    color: COLOR_TEXT_PRIMARY,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                }}
            >
                {value}
            </div>
            {sub && (
                <div style={{ fontSize: 10, color: COLOR_TEXT_SECONDARY }}>{sub}</div>
            )}
        </div>
    )
}

function MarketStatsRow({
    marketKey,
    marketLabel,
    sectorCount,
    topSector,
    totalTurnoverUsd,
    asOfDate,
}: {
    marketKey: string
    marketLabel: string
    sectorCount: number
    topSector: string
    totalTurnoverUsd: number
    asOfDate: string
}) {
    const t = useT()
    return (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
            <StatTile
                label={t("statSectorCount")}
                value={`${sectorCount}`}
                sub={t("statSectorCountSub", { market: marketLabel })}
            />
            <StatTile label={t("statTopSector")} value={topSector || "—"} sub={t("statTopSectorSub")} />
            <StatTile
                label={t("statTurnover")}
                value={formatUsd(totalTurnoverUsd)}
                sub={t("statTurnoverSub")}
            />
            <StatTile
                label={t("statBenchmark")}
                value={asOfDate || "—"}
                sub={t(MARKET_NOTE_KEYS[marketKey] || "marketNoteJP")}
            />
        </div>
    )
}

// -----------------------------------------------------------------------
// 成分股清單（灰色小字，公司名稱 + 股價漲跌）
// -----------------------------------------------------------------------
function ConstituentList({ tickers }: { tickers: TickerInfo[] }) {
    const lang = useLang()
    if (!tickers || tickers.length === 0) return null
    return (
        <div
            style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "2px 8px",
                fontSize: 11,
                color: COLOR_TEXT_SECONDARY,
            }}
        >
            {tickers.map((t, i) => (
                <span key={t.symbol} style={{ whiteSpace: "nowrap" }}>
                    {getTranslatedText(t.name, lang) || t.symbol}
                    <span
                        style={{
                            marginLeft: 4,
                            color:
                                t.pct_change > 0
                                    ? COLOR_UP
                                    : t.pct_change < 0
                                    ? COLOR_DOWN
                                    : COLOR_FLAT,
                        }}
                    >
                        {t.pct_change > 0 ? "+" : ""}
                        {t.pct_change.toFixed(2)}%
                    </span>
                    {i < tickers.length - 1 && <span style={{ marginLeft: 8, opacity: 0.4 }}>·</span>}
                </span>
            ))}
        </div>
    )
}

// -----------------------------------------------------------------------
// 全部市場：跨市場連動表格
// -----------------------------------------------------------------------
function CrossMarketTable({ rows, badge }: { rows: SectorRow[]; badge?: string }) {
    const t = useT()
    const lang = useLang()
    return (
        <div
            style={{
                border: `1px solid ${COLOR_BORDER}`,
                borderRadius: 10,
                overflow: "hidden",
                background: COLOR_PANEL,
            }}
        >
            <div
                style={{
                    padding: "14px 18px",
                    borderBottom: `1px solid ${COLOR_BORDER}`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 12,
                }}
            >
                <div
                    style={{
                        fontSize: 14,
                        fontWeight: 700,
                        color: COLOR_ACCENT,
                        letterSpacing: 0.5,
                    }}
                >
                    {t("crossMarketTableTitle")}
                </div>
                {badge && (
                    <div style={{ fontSize: 11, color: COLOR_TEXT_SECONDARY }}>{badge}</div>
                )}
            </div>

            {/* 手機版可左右滑動 (Swipe) 查看美股／日股／韓股欄位，表格本身設 minWidth 避免文字擠成一坨 */}
            <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
                <table
                    style={{
                        width: "100%",
                        borderCollapse: "collapse",
                        minWidth: 800,
                    }}
                >
                    <thead>
                        <tr>
                            <th
                                style={{
                                    ...thStyle,
                                    textAlign: "left",
                                    color: COLOR_TEXT_SECONDARY,
                                }}
                            >
                                {t("sectorColumn")}
                            </th>
                            {MARKET_ORDER.map((m) => (
                                <th key={m} style={thStyle}>
                                    {t(MARKET_LABEL_KEYS[m])}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row, idx) => (
                            <tr
                                key={row.sector_id}
                                style={{
                                    borderTop: `1px solid ${COLOR_BORDER}`,
                                    background: idx % 2 === 1 ? "rgba(255,255,255,0.015)" : "transparent",
                                }}
                            >
                                <td
                                    style={{
                                        ...tdStyle,
                                        textAlign: "left",
                                        fontWeight: 600,
                                        color: COLOR_TEXT_PRIMARY,
                                        whiteSpace: "nowrap",
                                    }}
                                >
                                    {getTranslatedText(resolveSectorInput(row.sector_id, row.sector), lang)}
                                </td>
                                {MARKET_ORDER.map((m) => {
                                    const block = row.markets[m]
                                    if (!block || block.tickers.length === 0) {
                                        return (
                                            <td key={m} style={{ ...tdStyle, color: COLOR_TEXT_SECONDARY }}>
                                                —
                                            </td>
                                        )
                                    }
                                    return (
                                        <td key={m} style={tdStyle}>
                                            <div
                                                style={{
                                                    display: "flex",
                                                    flexDirection: "column",
                                                    alignItems: "center",
                                                    gap: 3,
                                                }}
                                            >
                                                <PctChangeTag value={block.weighted_change_pct} />
                                                <div
                                                    style={{
                                                        display: "flex",
                                                        flexDirection: "column",
                                                        gap: 1,
                                                        maxWidth: 150,
                                                    }}
                                                >
                                                    {block.tickers.map((t) => (
                                                        <div
                                                            key={t.symbol}
                                                            style={{
                                                                fontSize: 10,
                                                                color: COLOR_TEXT_SECONDARY,
                                                                overflow: "hidden",
                                                                textOverflow: "ellipsis",
                                                                whiteSpace: "nowrap",
                                                            }}
                                                            title={`${getTranslatedText(t.name, lang) || t.symbol} (${t.symbol}) ${t.pct_change > 0 ? "+" : ""}${t.pct_change.toFixed(2)}%`}
                                                        >
                                                            {getTranslatedText(t.name, lang) || t.symbol}
                                                            <span
                                                                style={{
                                                                    marginLeft: 4,
                                                                    color:
                                                                        t.pct_change > 0
                                                                            ? COLOR_UP
                                                                            : t.pct_change < 0
                                                                            ? COLOR_DOWN
                                                                            : COLOR_FLAT,
                                                                }}
                                                            >
                                                                {t.pct_change > 0 ? "+" : ""}
                                                                {t.pct_change.toFixed(2)}%
                                                            </span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        </td>
                                    )
                                })}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    )
}

const thStyle: CSSProperties = {
    padding: "10px 14px",
    fontSize: 11,
    fontWeight: 600,
    color: COLOR_TEXT_SECONDARY,
    textAlign: "center",
    letterSpacing: 0.5,
}

const tdStyle: CSSProperties = {
    padding: "10px 14px",
    fontSize: 12,
    textAlign: "center",
    color: COLOR_TEXT_PRIMARY,
}

// -----------------------------------------------------------------------
// 動能排行 — 水平條狀列（全部市場 / 單一市場共用）
// -----------------------------------------------------------------------
function MomentumBarRow({
    rank,
    item,
    maxScore,
    tickers,
}: {
    rank: number
    item: MomentumItem
    maxScore: number
    tickers: TickerInfo[]
}) {
    const lang = useLang()
    const widthPct = maxScore > 0 ? (item.momentum_score / maxScore) * 100 : 0
    const barColor = item.weighted_change_pct >= 0 ? COLOR_UP : COLOR_DOWN
    return (
        <div
            style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                rowGap: 10,
                columnGap: 16,
                padding: "14px 8px",
                borderTop: `1px solid ${COLOR_BORDER}`,
            }}
        >
            {/* 左側：排名 + 板塊名稱 + 成分股 */}
            <div
                style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 12,
                    flex: "1 1 260px",
                    minWidth: 0,
                }}
            >
                <div
                    style={{
                        flexShrink: 0,
                        width: 26,
                        height: 26,
                        borderRadius: 6,
                        background: COLOR_PANEL_RAISED,
                        border: `1px solid ${COLOR_BORDER}`,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 11,
                        fontWeight: 700,
                        color: rank <= 3 ? COLOR_ACCENT : COLOR_TEXT_SECONDARY,
                    }}
                >
                    {String(rank).padStart(2, "0")}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: COLOR_TEXT_PRIMARY }}>
                        {getTranslatedText(resolveSectorInput(item.sector_id, item.sector), lang)}
                    </div>
                    <ConstituentList tickers={tickers} />
                </div>
            </div>

            {/* 右側：漲跌幅 + 動能長條圖 + 分數 */}
            <div
                style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                    flex: "1 1 240px",
                    minWidth: 180,
                }}
            >
                <div
                    style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                        fontSize: 11,
                    }}
                >
                    <PctChangeTag value={item.weighted_change_pct} />
                    <span style={{ color: COLOR_TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>
                        {formatUsd(item.turnover_usd)}
                    </span>
                </div>
                <div
                    style={{
                        position: "relative",
                        width: "100%",
                        height: 10,
                        borderRadius: 6,
                        background: "rgba(255,255,255,0.05)",
                        border: `1px solid ${COLOR_BORDER}`,
                        overflow: "hidden",
                        boxSizing: "border-box",
                    }}
                >
                    <div
                        style={{
                            width: `${widthPct}%`,
                            height: "100%",
                            borderRadius: 6,
                            background: `linear-gradient(90deg, ${barColor}55 0%, ${barColor} 100%)`,
                            transition: "width 0.5s ease",
                        }}
                    />
                </div>
                <MomentumScoreDisplay item={item} />
            </div>
        </div>
    )
}

// -----------------------------------------------------------------------
// 單一市場：成分股細項卡片（點擊展開後顯示）
// -----------------------------------------------------------------------
function TickerDetailCard({ ticker }: { ticker: TickerInfo }) {
    const lang = useLang()
    const displayName = getTranslatedText(ticker.name, lang) || ticker.symbol
    return (
        <div
            style={{
                display: "flex",
                flexDirection: "column",
                gap: 4,
                padding: "10px 12px",
                borderRadius: 8,
                background: "rgba(255,255,255,0.03)",
                border: `1px solid ${COLOR_BORDER}`,
            }}
        >
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 8,
                }}
            >
                <span
                    style={{
                        fontSize: 13,
                        fontWeight: 700,
                        color: COLOR_TEXT_PRIMARY,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                    }}
                    title={displayName}
                >
                    {displayName}
                </span>
                <PctChangeTag value={ticker.pct_change} size={12} />
            </div>
            <div style={{ fontSize: 11, color: COLOR_TEXT_SECONDARY }}>
                {ticker.symbol} · 收盤 {ticker.close.toLocaleString()}
            </div>
            <div style={{ fontSize: 11, color: COLOR_TEXT_SECONDARY }}>
                成交額 {formatUsd(ticker.turnover_usd)} · {ticker.as_of_date}
            </div>
        </div>
    )
}

// 展開區塊：深色微透明容器，內部以卡片格線排列成分股，避免全部擠在同一行
function ExpandedSectorPanel({ tickers }: { tickers: TickerInfo[] }) {
    const t = useT()
    if (!tickers || tickers.length === 0) return null
    return (
        <div
            style={{
                margin: "0 4px 14px",
                padding: 14,
                borderRadius: 10,
                background: "rgba(0,242,254,0.05)",
                border: "1px solid rgba(0,242,254,0.25)",
            }}
        >
            <div
                style={{
                    fontSize: 11,
                    color: COLOR_ACCENT,
                    letterSpacing: 0.5,
                    marginBottom: 10,
                    fontWeight: 700,
                }}
            >
                {t("constituentCountTitle", { count: tickers.length })}
            </div>
            <div
                style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
                    gap: 10,
                }}
            >
                {tickers.map((t) => (
                    <TickerDetailCard key={t.symbol} ticker={t} />
                ))}
            </div>
        </div>
    )
}

// 單一市場列表用：可點擊展開/收合的板塊列（Accordion）
function SectorAccordionRow({
    rank,
    item,
    maxScore,
    tickers,
    isExpanded,
    onToggle,
}: {
    rank: number
    item: MomentumItem
    maxScore: number
    tickers: TickerInfo[]
    isExpanded: boolean
    onToggle: () => void
}) {
    const t = useT()
    const lang = useLang()
    const widthPct = maxScore > 0 ? (item.momentum_score / maxScore) * 100 : 0
    const barColor = item.weighted_change_pct >= 0 ? COLOR_UP : COLOR_DOWN
    return (
        <div>
            <button
                onClick={onToggle}
                style={{
                    width: "100%",
                    boxSizing: "border-box",
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "center",
                    rowGap: 10,
                    columnGap: 16,
                    padding: "14px 8px",
                    border: "none",
                    borderTop: `1px solid ${COLOR_BORDER}`,
                    borderRadius: 8,
                    background: isExpanded ? "rgba(0,242,254,0.06)" : "transparent",
                    cursor: "pointer",
                    textAlign: "left",
                    fontFamily: FONT_STACK,
                    transition: "background 0.15s ease",
                }}
            >
                {/* 左側：展開箭頭 + 排名 + 板塊名稱 */}
                <div
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 12,
                        flex: "1 1 260px",
                        minWidth: 0,
                    }}
                >
                    <span
                        style={{
                            fontSize: 11,
                            color: isExpanded ? COLOR_ACCENT : COLOR_TEXT_SECONDARY,
                            flexShrink: 0,
                            transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)",
                            transition: "transform 0.15s ease",
                            display: "inline-block",
                        }}
                    >
                        ▸
                    </span>
                    <div
                        style={{
                            flexShrink: 0,
                            width: 26,
                            height: 26,
                            borderRadius: 6,
                            background: COLOR_PANEL_RAISED,
                            border: `1px solid ${COLOR_BORDER}`,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: 11,
                            fontWeight: 700,
                            color: rank <= 3 ? COLOR_ACCENT : COLOR_TEXT_SECONDARY,
                        }}
                    >
                        {String(rank).padStart(2, "0")}
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: COLOR_TEXT_PRIMARY }}>
                            {getTranslatedText(resolveSectorInput(item.sector_id, item.sector), lang)}
                        </div>
                        <div style={{ fontSize: 10, color: COLOR_TEXT_SECONDARY }}>
                            {t("constituentCountLine", {
                                count: tickers.length,
                                action: t(isExpanded ? "actionCollapse" : "actionExpand"),
                            })}
                        </div>
                    </div>
                </div>

                {/* 右側：漲跌幅 + 動能長條圖 + 分數 */}
                <div
                    style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: 6,
                        flex: "1 1 240px",
                        minWidth: 180,
                    }}
                >
                    <div
                        style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "baseline",
                            fontSize: 11,
                        }}
                    >
                        <PctChangeTag value={item.weighted_change_pct} />
                        <span style={{ color: COLOR_TEXT_SECONDARY, fontVariantNumeric: "tabular-nums" }}>
                            {formatUsd(item.turnover_usd)}
                        </span>
                    </div>
                    <div
                        style={{
                            position: "relative",
                            width: "100%",
                            height: 10,
                            borderRadius: 6,
                            background: "rgba(255,255,255,0.05)",
                            border: `1px solid ${COLOR_BORDER}`,
                            overflow: "hidden",
                            boxSizing: "border-box",
                        }}
                    >
                        <div
                            style={{
                                width: `${widthPct}%`,
                                height: "100%",
                                borderRadius: 6,
                                background: `linear-gradient(90deg, ${barColor}55 0%, ${barColor} 100%)`,
                                transition: "width 0.5s ease",
                            }}
                        />
                    </div>
                    <MomentumScoreDisplay item={item} />
                </div>
            </button>

            {isExpanded && <ExpandedSectorPanel tickers={tickers} />}
        </div>
    )
}

function PanelHeader({ title, badge }: { title: string; badge?: string }) {
    return (
        <div
            style={{
                padding: "14px 18px",
                borderBottom: `1px solid ${COLOR_BORDER}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
            }}
        >
            <div
                style={{
                    fontSize: 14,
                    fontWeight: 700,
                    color: COLOR_ACCENT,
                    letterSpacing: 0.5,
                }}
            >
                {title}
            </div>
            {badge && (
                <div style={{ fontSize: 11, color: COLOR_TEXT_SECONDARY }}>{badge}</div>
            )}
        </div>
    )
}

// 取得板塊在跨市場資料中「代表性成分股」清單：優先取台股，其次取第一個有資料的市場
function getRepresentativeTickers(row: SectorRow | undefined): TickerInfo[] {
    if (!row) return []
    const tw = row.markets["TW"]
    if (tw && tw.tickers.length > 0) return tw.tickers
    for (const m of MARKET_ORDER) {
        const block = row.markets[m]
        if (block && block.tickers.length > 0) return block.tickers
    }
    return []
}

// -----------------------------------------------------------------------
// 全部市場檢視
// -----------------------------------------------------------------------
function AllMarketsView({
    data,
    flowFilter,
}: {
    data: SectorData
    flowFilter: "top" | "bottom"
}) {
    const t = useT()
    // 3. 資料排序與截斷：依動能分數排序（top=由大到小 / bottom=由小到大），固定只取 10 筆
    const sortedRows = sortSectorRowsByFlow(data.cross_market_table, data.momentum_ranking, flowFilter)
    const sortedMomentum = sortMomentumItems(data.momentum_ranking, flowFilter)
    const maxScore = Math.max(100, ...sortedMomentum.map((i) => i.momentum_score))
    const sectorById: Record<string, SectorRow> = {}
    data.cross_market_table.forEach((row) => {
        sectorById[row.sector_id] = row
    })
    const badgeText = t(flowFilter === "top" ? "flowTop" : "flowBottom")

    return (
        <>
            <CrossMarketTable rows={sortedRows} badge={badgeText} />

            <div
                style={{
                    border: `1px solid ${COLOR_BORDER}`,
                    borderRadius: 10,
                    background: COLOR_PANEL,
                }}
            >
                <PanelHeader title={t("momentumRankingTitle")} badge={badgeText} />
                <div style={{ padding: "0 18px 6px" }}>
                    {sortedMomentum.map((item, i) => (
                        <MomentumBarRow
                            key={item.sector_id}
                            rank={i + 1}
                            item={item}
                            maxScore={maxScore}
                            tickers={getRepresentativeTickers(sectorById[item.sector_id])}
                        />
                    ))}
                </div>
            </div>
        </>
    )
}

// -----------------------------------------------------------------------
// 單一市場檢視
// -----------------------------------------------------------------------
function SingleMarketView({
    data,
    marketKey,
    flowFilter,
}: {
    data: SectorData
    marketKey: string
    flowFilter: "top" | "bottom"
}) {
    const t = useT()
    const lang = useLang()
    const marketLabel = MARKET_LABEL_KEYS[marketKey] ? t(MARKET_LABEL_KEYS[marketKey]) : marketKey
    const [expandedSector, setExpandedSector] = useState<string | null>(null)

    const sectorById: Record<string, SectorRow> = {}
    data.cross_market_table.forEach((row) => {
        sectorById[row.sector_id] = row
    })

    // 2. 自動隱藏空白資料：只保留該市場「確實有成分股資料」的板塊，
    //    不顯示任何 — 或空白區塊。
    const nonEmptyItems = (data.market_momentum[marketKey] || []).filter((item) => {
        const block = sectorById[item.sector_id]?.markets[marketKey]
        return !!block && block.tickers && block.tickers.length > 0
    })

    // 3. 資料排序與截斷：依動能分數排序（top=由大到小 / bottom=由小到大），固定只取 10 筆
    const items = sortMomentumItems(nonEmptyItems, flowFilter)

    const maxScore = Math.max(100, ...items.map((i) => i.momentum_score))

    const totalTurnoverUsd = items.reduce((sum, i) => sum + i.turnover_usd, 0)
    const topSector =
        items.length > 0 ? getTranslatedText(resolveSectorInput(items[0].sector_id, items[0].sector), lang) : ""
    const asOfDate =
        items.length > 0 ? sectorById[items[0].sector_id]?.markets[marketKey]?.as_of || "" : ""

    if (items.length === 0) {
        return (
            <div
                style={{
                    border: `1px solid ${COLOR_BORDER}`,
                    borderRadius: 10,
                    background: COLOR_PANEL,
                    padding: 32,
                    textAlign: "center",
                    color: COLOR_TEXT_SECONDARY,
                    fontSize: 13,
                }}
            >
                {t("noDataForMarket", { market: marketLabel })}
            </div>
        )
    }

    return (
        <>
            <MarketStatsRow
                marketKey={marketKey}
                marketLabel={marketLabel}
                sectorCount={items.length}
                topSector={topSector}
                totalTurnoverUsd={totalTurnoverUsd}
                asOfDate={asOfDate}
            />

            <div
                style={{
                    border: `1px solid ${COLOR_BORDER}`,
                    borderRadius: 10,
                    background: COLOR_PANEL,
                }}
            >
                <PanelHeader
                    title={t("singleMarketRankingTitle", { market: marketLabel })}
                    badge={`${t(flowFilter === "top" ? "badgeTop" : "badgeBottom")} · ${t("sectorCountUnit", {
                        count: items.length,
                    })}`}
                />
                <div style={{ padding: "0 18px 6px" }}>
                    {items.map((item, i) => {
                        const tickers = sectorById[item.sector_id]?.markets[marketKey]?.tickers || []
                        return (
                            <SectorAccordionRow
                                key={item.sector_id}
                                rank={i + 1}
                                item={item}
                                maxScore={maxScore}
                                tickers={tickers}
                                isExpanded={expandedSector === item.sector_id}
                                onToggle={() =>
                                    setExpandedSector((prev) =>
                                        prev === item.sector_id ? null : item.sector_id
                                    )
                                }
                            />
                        )
                    })}
                </div>
            </div>
        </>
    )
}

// -----------------------------------------------------------------------
// 主元件
// -----------------------------------------------------------------------
export default function SectorDashboard(props) {
    const { dataUrl, refreshIntervalSec } = props
    const [data, setData] = useState<SectorData | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)
    const [selectedMarket, setSelectedMarket] = useState<string>("ALL")
    const [flowFilter, setFlowFilter] = useState<"top" | "bottom">("top")

    // 多語系：1) useState 管理目前語系（預設 en-US）
    //         2) useEffect 於掛載時讀取 navigator.language 自動偵測一次
    //         3) 之後使用者透過 LangSwitcher 手動點擊可隨時強制覆寫，不受自動偵測影響
    const [currentLang, setCurrentLang] = useState<Lang>("en-US")
    // 本元件本身是 LangContext 的提供者，無法用 useContext 讀取自己提供的值，
    // 故直接以 currentLang 呼叫 translate()；子元件一律改用 useT()（見上方定義）。
    const t = (key: string, vars?: Record<string, string | number>) => translate(currentLang, key, vars)

    useEffect(() => {
        setCurrentLang(detectInitialLang())
    }, [])

    useEffect(() => {
        let cancelled = false

        async function load() {
            try {
                setLoading(true)
                setError(null)
                const res = await fetch("https://raw.githubusercontent.com/daster9450-oss/TTMA-Quant/refs/heads/master/sector_data.json", { cache: "no-store" })
                if (!res.ok) {
                    throw new Error(`HTTP ${res.status}`)
                }
                const json = (await res.json()) as SectorData
                if (!cancelled) {
                    setData(json)
                    setLoading(false)
                }
            } catch (err) {
                if (!cancelled) {
                    setError(err instanceof Error ? err.message : t("unknownError"))
                    setLoading(false)
                }
            }
        }

        load()

        let timer: ReturnType<typeof setInterval> | undefined
        if (refreshIntervalSec && refreshIntervalSec > 0) {
            timer = setInterval(load, refreshIntervalSec * 1000)
        }

        return () => {
            cancelled = true
            if (timer) clearInterval(timer)
        }
    }, [dataUrl, refreshIntervalSec])

    return (
        <LangContext.Provider value={currentLang}>
            <div
                style={{
                    width: "100%",
                    height: "100%",
                    minHeight: 480,
                    background: COLOR_BG,
                    fontFamily: FONT_STACK,
                    color: COLOR_TEXT_PRIMARY,
                    padding: 20,
                    boxSizing: "border-box",
                    display: "flex",
                    flexDirection: "column",
                    gap: 18,
                    borderRadius: 12,
                }}
            >
                {/* 頂部控制區：標題、市場頁籤、語言切換器。外層與內層皆設 flexWrap，
                    手機螢幕空間不足時自動往下折行，rowGap/columnGap 分開設定讓折行後的
                    上下間距更寬鬆好看，不會和左右間距擠在一起。 */}
                <div
                    style={{
                        display: "flex",
                        flexWrap: "wrap",
                        justifyContent: "space-between",
                        alignItems: "center",
                        rowGap: 14,
                        columnGap: 14,
                    }}
                >
                    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                        <div
                            style={{
                                fontSize: 18,
                                fontWeight: 800,
                                color: COLOR_ACCENT,
                                letterSpacing: 0.5,
                            }}
                        >
                            {t("title")}
                        </div>
                        {data && (
                            <div style={{ fontSize: 11, color: COLOR_TEXT_SECONDARY }}>
                                {t("updatedAt")}
                                {data.generated_at_utc}
                            </div>
                        )}
                    </div>

                    <div
                        style={{
                            display: "flex",
                            flexWrap: "wrap",
                            alignItems: "center",
                            rowGap: 8,
                            columnGap: 10,
                        }}
                    >
                        {!loading && !error && data && (
                            <MarketTabs selected={selectedMarket} onSelect={setSelectedMarket} />
                        )}
                        <LangSwitcher lang={currentLang} onSelect={setCurrentLang} />
                    </div>
                </div>

                {!loading && !error && data && (
                    <FlowFilterToggle selected={flowFilter} onSelect={setFlowFilter} />
                )}

                {loading && <LoadingState />}
                {!loading && error && <ErrorState message={error} />}
                {!loading && !error && data && (
                    <>
                        {selectedMarket === "ALL" ? (
                            <AllMarketsView data={data} flowFilter={flowFilter} />
                        ) : (
                            <SingleMarketView
                                key={selectedMarket}
                                data={data}
                                marketKey={selectedMarket}
                                flowFilter={flowFilter}
                            />
                        )}
                    </>
                )}
            </div>
        </LangContext.Provider>
    )
}

SectorDashboard.defaultProps = {
    dataUrl: "/sector_data.json",
    refreshIntervalSec: 0,
}

addPropertyControls(SectorDashboard, {
    dataUrl: {
        type: ControlType.String,
        title: "資料來源網址",
        defaultValue: "/sector_data.json",
    },
    refreshIntervalSec: {
        type: ControlType.Number,
        title: "自動刷新秒數(0=不刷新)",
        defaultValue: 0,
        min: 0,
        max: 3600,
        step: 5,
    },
})
