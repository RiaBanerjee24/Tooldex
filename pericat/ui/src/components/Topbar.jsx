import { Dot, Wrap } from "./ui.jsx"

export function Topbar({ tab, setTab, health }) {
    const tabs = ["Dashboard", "Agents", "Servers", "Permissions"]
    return (
        <div style={{
            background: "var(--surface)", borderBottom: "1px solid var(--border)",
            position: "sticky", top: 0, zIndex: 100,
        }}>
            <Wrap>
                <div style={{ display: "flex", alignItems: "center", height: 56, gap: 8 }}>

                    {/* Logo */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginRight: 36 }}>
                        <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
                            <polygon points="13,2 23,7.5 23,18.5 13,24 3,18.5 3,7.5" stroke="#BED754" strokeWidth="1.2" fill="none" opacity="0.9" />
                            <polygon points="13,6 19.5,9.75 19.5,17.25 13,21 6.5,17.25 6.5,9.75" stroke="#BED754" strokeWidth="0.6" fill="none" opacity="0.3" />
                            <circle cx="13" cy="13" r="2.8" fill="#BED754" opacity="0.95" />
                            <line x1="13" y1="6.5" x2="13" y2="10.2" stroke="#BED754" strokeWidth="0.7" opacity="0.4" />
                            <line x1="13" y1="15.8" x2="13" y2="19.5" stroke="#BED754" strokeWidth="0.7" opacity="0.4" />
                            <line x1="6.8" y1="9.8" x2="10" y2="11.5" stroke="#BED754" strokeWidth="0.7" opacity="0.4" />
                            <line x1="16" y1="14.5" x2="19.2" y2="16.2" stroke="#BED754" strokeWidth="0.7" opacity="0.4" />
                            <line x1="19.2" y1="9.8" x2="16" y2="11.5" stroke="#BED754" strokeWidth="0.7" opacity="0.4" />
                            <line x1="10" y1="14.5" x2="6.8" y2="16.2" stroke="#BED754" strokeWidth="0.7" opacity="0.4" />
                        </svg>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
                            <span style={{ fontFamily: "Georgia, serif", fontWeight: 500, fontSize: 18, color: "var(--cream)", letterSpacing: "-0.01em" }}>Pericat</span>
                            <span style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 10, color: "var(--lime-dim)", letterSpacing: "0.04em" }}>v0.1.0</span>
                        </div>
                    </div>

                    {/* Tabs */}
                    <div style={{ display: "flex", gap: 1, flex: 1 }}>
                        {tabs.map(t => (
                            <button key={t} onClick={() => setTab(t)} style={{
                                padding: "6px 16px", borderRadius: "var(--radius)", border: "none",
                                background: tab === t ? "var(--surface3)" : "transparent",
                                color: tab === t ? "var(--cream)" : "var(--text3)",
                                fontWeight: tab === t ? 600 : 400, fontSize: 13,
                                fontFamily: "var(--font-body)",
                                borderBottom: tab === t ? "2px solid var(--border2)" : "2px solid transparent",
                                transition: "all 0.12s",
                            }}>{t}</button>
                        ))}
                    </div>

                    {/* Status pill */}
                    {health && (
                        <div style={{
                            display: "flex", alignItems: "center", gap: 8,
                            padding: "5px 13px", borderRadius: "var(--radius)",
                            border: "1px solid var(--border)", background: "var(--surface2)",
                            fontSize: 12, fontFamily: "Menlo, Consolas, monospace", color: "var(--text2)",
                        }}>
                            <Dot on={health.status === "ok"} />
                            {health.config?.name}
                        </div>
                    )}
                </div>
            </Wrap>
        </div>
    )
}