import { Dot, Wrap } from "./ui.jsx"

export function Topbar({ tab, setTab, health }) {
    const tabs = ["Dashboard", "Servers"]
    return (
        <div style={{
            background: "var(--surface)", borderBottom: "1px solid var(--border)",
            position: "sticky", top: 0, zIndex: 100,
        }}>
            <Wrap>
                <div style={{ display: "flex", alignItems: "center", height: 56, gap: 8 }}>

                    {/* Logo */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginRight: 36 }}>
                        <img src="/tooldex.svg" alt="Tooldex" width={26} height={26} style={{ flexShrink: 0 }} />
                        <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
                            <span style={{ fontFamily: "Georgia, serif", fontWeight: 500, fontSize: 18, color: "var(--cream)", letterSpacing: "-0.01em" }}>Tooldex</span>
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
                    {/* {health && (
                        <div style={{
                            display: "flex", alignItems: "center", gap: 8,
                            padding: "5px 13px", borderRadius: "var(--radius)",
                            border: "1px solid var(--border)", background: "var(--surface2)",
                            fontSize: 12, fontFamily: "Menlo, Consolas, monospace", color: "var(--text2)",
                        }}>
                            <Dot on={health.status === "ok"} />
                            {health.config?.name}
                        </div>
                    )} */}
                </div>
            </Wrap>
        </div>
    )
}