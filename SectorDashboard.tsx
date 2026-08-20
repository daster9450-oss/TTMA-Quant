import { useState, useEffect, CSSProperties } from "react"
import { addPropertyControls, ControlType } from "framer"

/**
 * TTMA-Quant「產業金流與跨市場連動」儀表板
 * Framer Code Component — 讀取 main.py 產出的 sector_data.json
 *
 * 不依賴 Tailwind 或任何外部 UI 函式庫，純內聯樣式 (Inline CSS)。
 */

// -----------------------------------------------------------------------
// 型別定義
// -----------------------------------------------------------------------
type TickerInfo = {
    symbol: string
    name: string
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
    sector: string
    markets: Record<string, MarketBlock>
}

type MomentumItem = {
    sector: string
    momentum_score: number
    weighted_change_pct: number
    turnover_usd: number
}

type SectorData = {
    generated_at_utc: string
    fx_rates_usd_base: Record<string, number>
    cross_market_table: SectorRow[]
    momentum_ranking: MomentumItem[]
    market_momentum: Record<string, MomentumItem[]>
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
const MARKET_LABEL_FALLBACK: Record<string, string> = {
    TW: "台股",
    CN: "中股",
    US: "美股",
    JP: "日股",
    KR: "韓股",
}

// 市場切換頁籤：全部市場 + 使用者指定的四個市場（不含中股，中股僅保留於跨市場對比表欄位）
const MARKET_TABS: { key: string; label: string }[] = [
    { key: "ALL", label: "全部市場" },
    { key: "TW", label: "台股" },
    { key: "CN", label: "中股" },
    { key: "US", label: "美股" },
    { key: "JP", label: "日股" },
    { key: "KR", label: "韓股" },
]

const MARKET_RESEARCH_NOTE: Record<string, string> = {
    TW: "日成交資料 · 上市與上櫃",
    CN: "日成交資料 · 滬深兩市",
    US: "美股 T-1 收盤對齊亞股 T 日",
    JP: "日成交資料",
    KR: "日成交資料",
}

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

function LoadingState() {
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
            <div style={{ fontSize: 13, letterSpacing: 0.5 }}>
                資料載入中，正在同步跨市場金流數據...
            </div>
            <style>{`@keyframes ttma-spin { to { transform: rotate(360deg); } }`}</style>
        </div>
    )
}

function ErrorState({ message }: { message: string }) {
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
            <div style={{ fontSize: 15, fontWeight: 600 }}>資料載入失敗</div>
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
                        {tab.label}
                    </button>
                )
            })}
        </div>
    )
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
    return (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
            <StatTile label="涵蓋板塊數" value={`${sectorCount}`} sub={`${marketLabel}目前追蹤板塊`} />
            <StatTile label="最高成交動能" value={topSector || "—"} sub="動能分數排名第一" />
            <StatTile label="板塊成交金額合計" value={formatUsd(totalTurnoverUsd)} sub="換算美元 (USD)" />
            <StatTile
                label="研究基準"
                value={asOfDate || "—"}
                sub={MARKET_RESEARCH_NOTE[marketKey] || "日成交資料"}
            />
        </div>
    )
}

// -----------------------------------------------------------------------
// 成分股清單（灰色小字，公司名稱 + 股價漲跌）
// -----------------------------------------------------------------------
function ConstituentList({ tickers }: { tickers: TickerInfo[] }) {
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
                    {t.name}
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
function CrossMarketTable({ rows }: { rows: SectorRow[] }) {
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
                    fontSize: 14,
                    fontWeight: 700,
                    color: COLOR_ACCENT,
                    letterSpacing: 0.5,
                }}
            >
                跨市場連動表
            </div>

            <div style={{ overflowX: "auto" }}>
                <table
                    style={{
                        width: "100%",
                        borderCollapse: "collapse",
                        minWidth: 760,
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
                                板塊
                            </th>
                            {MARKET_ORDER.map((m) => (
                                <th key={m} style={thStyle}>
                                    {MARKET_LABEL_FALLBACK[m]}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row, idx) => (
                            <tr
                                key={row.sector}
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
                                    {row.sector}
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
                                                            title={`${t.name} (${t.symbol}) ${t.pct_change > 0 ? "+" : ""}${t.pct_change.toFixed(2)}%`}
                                                        >
                                                            {t.name}
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
    const widthPct = maxScore > 0 ? (item.momentum_score / maxScore) * 100 : 0
    const barColor = item.weighted_change_pct >= 0 ? COLOR_UP : COLOR_DOWN
    return (
        <div
            style={{
                display: "flex",
                alignItems: "center",
                gap: 16,
                padding: "14px 4px",
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
                        {item.sector}
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
                        height: 10,
                        borderRadius: 6,
                        background: "rgba(255,255,255,0.05)",
                        border: `1px solid ${COLOR_BORDER}`,
                        overflow: "hidden",
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
                <div style={{ fontSize: 10, color: COLOR_TEXT_SECONDARY, textAlign: "right" }}>
                    動能分數 {item.momentum_score.toFixed(1)} / 100
                </div>
            </div>
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
function AllMarketsView({ data, topN }: { data: SectorData; topN: number }) {
    const sliced = data.momentum_ranking.slice(0, topN)
    const maxScore = Math.max(100, ...data.momentum_ranking.map((i) => i.momentum_score))
    const sectorByName: Record<string, SectorRow> = {}
    data.cross_market_table.forEach((row) => {
        sectorByName[row.sector] = row
    })

    return (
        <>
            <CrossMarketTable rows={data.cross_market_table} />

            <div
                style={{
                    border: `1px solid ${COLOR_BORDER}`,
                    borderRadius: 10,
                    background: COLOR_PANEL,
                }}
            >
                <PanelHeader title="動能排行榜（跨市場綜合）" badge={`前 ${sliced.length} 大板塊`} />
                <div style={{ padding: "0 18px 6px" }}>
                    {sliced.map((item, i) => (
                        <MomentumBarRow
                            key={item.sector}
                            rank={i + 1}
                            item={item}
                            maxScore={maxScore}
                            tickers={getRepresentativeTickers(sectorByName[item.sector])}
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
}: {
    data: SectorData
    marketKey: string
}) {
    const marketLabel = MARKET_LABEL_FALLBACK[marketKey] || marketKey
    const items = data.market_momentum[marketKey] || []
    const maxScore = Math.max(100, ...items.map((i) => i.momentum_score))

    const sectorByName: Record<string, SectorRow> = {}
    data.cross_market_table.forEach((row) => {
        sectorByName[row.sector] = row
    })

    const totalTurnoverUsd = items.reduce((sum, i) => sum + i.turnover_usd, 0)
    const topSector = items.length > 0 ? items[0].sector : ""
    const asOfDate =
        items.length > 0 ? sectorByName[items[0].sector]?.markets[marketKey]?.as_of || "" : ""

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
                目前尚無{marketLabel}板塊資料。
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
                <PanelHeader title={`${marketLabel}細分板塊動能排行`} badge={`${items.length} 個板塊`} />
                <div style={{ padding: "0 18px 6px" }}>
                    {items.map((item, i) => (
                        <MomentumBarRow
                            key={item.sector}
                            rank={i + 1}
                            item={item}
                            maxScore={maxScore}
                            tickers={sectorByName[item.sector]?.markets[marketKey]?.tickers || []}
                        />
                    ))}
                </div>
            </div>
        </>
    )
}

// -----------------------------------------------------------------------
// 主元件
// -----------------------------------------------------------------------
export default function SectorDashboard(props) {
    const { dataUrl, topN, refreshIntervalSec } = props
    const [data, setData] = useState<SectorData | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)
    const [selectedMarket, setSelectedMarket] = useState<string>("ALL")

    useEffect(() => {
        let cancelled = false

        async function load() {
            try {
                setLoading(true)
                setError(null)
                const res = await fetch(dataUrl, { cache: "no-store" })
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
                    setError(err instanceof Error ? err.message : "未知錯誤")
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
            <div
                style={{
                    display: "flex",
                    flexWrap: "wrap",
                    justifyContent: "space-between",
                    alignItems: "flex-end",
                    gap: 14,
                }}
            >
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <div
                        style={{
                            fontSize: 18,
                            fontWeight: 800,
                            color: COLOR_ACCENT,
                            letterSpacing: 0.5,
                        }}
                    >
                        產業金流與跨市場連動
                    </div>
                    {data && (
                        <div style={{ fontSize: 11, color: COLOR_TEXT_SECONDARY }}>
                            資料更新時間（UTC）：{data.generated_at_utc}
                        </div>
                    )}
                </div>

                {!loading && !error && data && (
                    <MarketTabs selected={selectedMarket} onSelect={setSelectedMarket} />
                )}
            </div>

            {loading && <LoadingState />}
            {!loading && error && <ErrorState message={error} />}
            {!loading && !error && data && (
                <>
                    {selectedMarket === "ALL" ? (
                        <AllMarketsView data={data} topN={topN} />
                    ) : (
                        <SingleMarketView data={data} marketKey={selectedMarket} />
                    )}
                </>
            )}
        </div>
    )
}

SectorDashboard.defaultProps = {
    dataUrl: "/sector_data.json",
    topN: 5,
    refreshIntervalSec: 0,
}

addPropertyControls(SectorDashboard, {
    dataUrl: {
        type: ControlType.String,
        title: "資料來源網址",
        defaultValue: "/sector_data.json",
    },
    topN: {
        type: ControlType.Number,
        title: "顯示前N大板塊",
        defaultValue: 5,
        min: 1,
        max: 20,
        step: 1,
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
