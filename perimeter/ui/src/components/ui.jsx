import { ACCESS, RISK } from "../constants.js"

export function Tag({ children, color }) {
    return (
        <span style={{
            display: "inline-block", padding: "1px 8px", borderRadius: 3,
            background: "var(--surface3)", border: "1px solid var(--border2)",
            fontSize: 11, fontWeight: 500, color: color || "var(--text3)",
            fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.02em",
        }}>{children}</span>
    )
}

export function RiskBadge({ risk }) {
    if (!risk) return null
    const r = RISK[risk] || RISK.low
    return (
        <span style={{
            padding: "1px 8px", borderRadius: 3, fontSize: 10, fontWeight: 500,
            letterSpacing: "0.1em", textTransform: "uppercase",
            background: r.bg, border: `1px solid ${r.border}`, color: r.color,
            fontFamily: "Menlo, Consolas, monospace",
        }}>{risk}</span>
    )
}

export function AccessBadge({ access }) {
    const a = ACCESS[access] || ACCESS.unknown
    return (
        <span style={{
            display: "inline-flex", alignItems: "center", gap: 5,
            padding: "2px 10px", borderRadius: 3, fontSize: 11, fontWeight: 500,
            background: a.bg, border: `1px solid ${a.border}`, color: a.color,
            fontFamily: "Menlo, Consolas, monospace",
        }}>
            <span>{a.symbol}</span><span>{a.label}</span>
        </span>
    )
}

export function Dot({ on }) {
    return (
        <span style={{
            display: "inline-block", width: 7, height: 7, borderRadius: "50%", flexShrink: 0,
            background: on ? "var(--lime)" : "var(--red)",
            animation: on ? "glow-pulse 2.5s ease-in-out infinite" : "red-pulse 2s ease-in-out infinite",
        }} />
    )
}

export function Card({ children, style, highlight }) {
    return (
        <div style={{
            background: "var(--surface)",
            border: `1px solid ${highlight ? "var(--accent-border)" : "var(--border)"}`,
            borderRadius: "var(--radius-lg)",
            boxShadow: highlight ? "var(--shadow-accent)" : "var(--shadow)",
            overflow: "hidden", ...style,
        }}>{children}</div>
    )
}

export function CardHead({ children, right }) {
    return (
        <div style={{
            padding: "10px 18px", borderBottom: "1px solid var(--border)",
            background: "var(--surface2)",
            display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
            <span style={{
                fontFamily: "var(--font-body)", fontWeight: 600, fontSize: 12,
                letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text2)",
            }}>{children}</span>
            {right}
        </div>
    )
}

export function Empty({ msg }) {
    return (
        <div style={{ padding: 36, textAlign: "center", color: "var(--text3)", fontSize: 12, fontFamily: "Menlo, Consolas, monospace" }}>
            {msg}
        </div>
    )
}

export function Spinner() {
    return (
        <div style={{ padding: 48, textAlign: "center", color: "var(--text3)", fontSize: 12, fontFamily: "Menlo, Consolas, monospace" }}>
            loading…
        </div>
    )
}

export function Err({ msg }) {
    return (
        <div style={{
            padding: 14, color: "var(--red)", fontSize: 11, fontFamily: "Menlo, Consolas, monospace",
            background: "var(--red-bg)", border: "1px solid var(--red-border)",
            borderRadius: "var(--radius)",
        }}>error: {msg}</div>
    )
}

export function Wrap({ children }) {
    return (
        <div style={{ maxWidth: 1240, margin: "0 auto", padding: "0 32px", width: "100%" }}>
            {children}
        </div>
    )
}

export function SidebarBtn({ active, onClick, children }) {
    return (
        <button onClick={onClick} style={{
            display: "block", width: "100%", padding: "10px 13px",
            borderRadius: "var(--radius)", border: "1px solid",
            borderColor: active ? "var(--accent-border)" : "var(--border)",
            background: active ? "var(--accent-bg)" : "transparent",
            textAlign: "left", transition: "all 0.12s",
            borderLeft: active ? "2px solid var(--accent-mid)" : "1px solid var(--border)",
        }}>{children}</button>
    )
}

export function StatCard({ label, value, sub }) {
    return (
        <div style={{
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: "var(--radius-lg)", padding: "22px 24px", boxShadow: "var(--shadow)",
        }}>
            <div style={{
                fontSize: 10, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase",
                color: "var(--text5)", fontFamily: "Menlo, Consolas, monospace", marginBottom: 14,
            }}>{label}</div>
            <div style={{
                fontFamily: "Georgia, serif", fontSize: 52, fontWeight: 300,
                lineHeight: 1, marginBottom: 8, color: "var(--cream)", fontStyle: "italic",
            }}>{value}</div>
            <div style={{ fontSize: 12, color: "var(--yellow-muted)", fontFamily: "Menlo, Consolas, monospace" }}>{sub}</div>
        </div>
    )
}