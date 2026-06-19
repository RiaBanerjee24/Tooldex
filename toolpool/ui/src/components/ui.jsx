import { ACCESS, RISK } from "../constants.js"

// ---------------------------------------------------------------------------
// Server provenance — where did this server record come from, and is the
// probe actually working?
//
// We derive one of three visual states from the backend's `source` and
// `discovery_status` fields:
//
//   declared       lime green   — in YAML + seen by discovery (the good case)
//   discovered     yellow       — found by discovery but not declared in YAML
//   not-discovered red          — declared in YAML but absent from every
//                                 MCP-client config we checked
//
// If the probe itself failed (timeout / protocol error), the tag color gets
// DOWNGRADED to yellow regardless of what the source says, because "we
// know about it but can't talk to it" is the yellow story — not green.
// A separate ⚠ icon next to the card title carries the specific reason.
//
// If the probe succeeded but the server reports zero tools, the tag stays
// green (valid state) and an ℹ icon appears instead. This isn't a warning,
// it's a heads-up.
// ---------------------------------------------------------------------------

export function classifyServerProvenance(server) {
    const source = server.source || "yaml"
    const status = server.discovery_status || "not_attempted"

    // Probe-level issues override tag color
    const probeFailed = status === "failed"
    const toolsEmpty =
        status === "ok" &&
        (server.discovered_tools?.length || 0) === 0

    let state, color
    if (source === "discovered") {
        state = "discovered"
        color = "yellow"
    } else if (source === "both") {
        state = "declared"
        color = probeFailed ? "yellow" : "lime"
    } else {
        // source === "yaml" — declared but not in any client config
        state = status === "not_found_in_clients" ? "not-discovered" : "declared"
        color = status === "not_found_in_clients" ? "red"
            : probeFailed ? "yellow"
                : "lime"
    }

    // Icon + tooltip — only rendered when there's something to surface
    let icon = null, iconMessage = null
    if (probeFailed) {
        icon = "warning"
        iconMessage = server.discovery_error || "Probe failed"
    } else if (toolsEmpty) {
        icon = "info"
        iconMessage = "Server reports no tools"
    }

    return { state, color, icon, iconMessage }
}

const PROVENANCE_COLOR_VARS = {
    lime: { color: "var(--lime)", bg: "var(--lime-bg)", border: "var(--lime-border)" },
    yellow: { color: "var(--yellow-muted)", bg: "var(--orange-bg)", border: "var(--orange-border)" },
    red: { color: "var(--red)", bg: "var(--red-bg)", border: "var(--red-border)" },
}

export function ProvenanceTag({ server }) {
    const { state, color, icon, iconMessage } = classifyServerProvenance(server)
    const c = PROVENANCE_COLOR_VARS[color]
    const symbol = icon === "warning" ? "⚠" : icon === "info" ? "ℹ" : null
    return (
        <span
            title={iconMessage || undefined}
            aria-label={iconMessage || undefined}
            style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "2px 9px", borderRadius: 3,
                background: c.bg, border: `1px solid ${c.border}`, color: c.color,
                fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase",
                fontFamily: "Menlo, Consolas, monospace",
                cursor: iconMessage ? "help" : "default",
            }}
        >
            {symbol && (
                <span style={{
                    fontSize: 12, lineHeight: 1, fontWeight: 700,
                    letterSpacing: "0",
                }}>{symbol}</span>
            )}
            <span>{state}</span>
        </span>
    )
}

export function ProvenanceDot({ server }) {
    const { color } = classifyServerProvenance(server)
    const c = PROVENANCE_COLOR_VARS[color]
    return (
        <span style={{
            display: "inline-block", width: 7, height: 7, borderRadius: "50%",
            flexShrink: 0, background: c.color,
        }} />
    )
}

export function ProvenanceIcon({ server }) {
    const { icon, iconMessage } = classifyServerProvenance(server)
    if (!icon) return null
    const symbol = icon === "warning" ? "⚠" : "ℹ"
    const isWarning = icon === "warning"
    const fg = isWarning ? "var(--yellow-muted)" : "var(--cream-dim)"
    const bg = isWarning ? "var(--orange-bg)" : "var(--surface3)"
    const border = isWarning ? "var(--orange-border)" : "var(--border2)"
    return (
        <span
            title={iconMessage}
            aria-label={iconMessage}
            style={{
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                width: 22, height: 22, borderRadius: "50%",
                fontSize: 13, fontWeight: 700,
                color: fg, background: bg, border: `1px solid ${border}`,
                cursor: "help", marginLeft: 10,
                fontFamily: "Menlo, Consolas, monospace",
                lineHeight: 1, flexShrink: 0,
            }}
        >{symbol}</span>
    )
}


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
            border: `1px solid ${highlight ? "var(--yellow-muted)" : "var(--border)"}`,
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
        <div style={{ maxWidth: 1600, margin: "0 auto", padding: "0 40px", width: "100%" }}>
            {children}
        </div>
    )
}

export function SidebarBtn({ active, onClick, children }) {
    return (
        <button onClick={onClick} style={{
            display: "block", width: "100%", padding: "10px 13px",
            borderRadius: "var(--radius)", border: "1px solid",
            borderColor: active ? "var(--border2)" : "var(--border)",
            background: active ? "var(--surface3)" : "transparent",
            textAlign: "left", transition: "all 0.12s",
            borderLeft: active ? "3px solid var(--border3)" : "1px solid var(--border)",
        }}>{children}</button>
    )
}

export function StatCard({ label, value, sub, onClick }) {
    return (
        <div onClick={onClick} style={{
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: "var(--radius-lg)", padding: "22px 24px", boxShadow: "var(--shadow)",
            cursor: onClick ? "pointer" : "default",
            transition: "border-color 0.12s",
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