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
                        <svg width="30" height="30" viewBox="0 0 100 125" style={{ flexShrink: 0, color: "#BED754" }} fill="currentColor" enable-background="new 0 0 100 100" xml:space="preserve">
                            <path d="M92.005,11.624C91.97,5.992,70.66,24.483,68.359,26.493c-12.232-5.868-26.149-5.828-38.404,0.048l-0.01,0.003  C27.555,24.456,6.359,6.077,6.324,11.695C6.095,19.478,5.792,27.261,6.11,35.046L6.099,35.05c0.427,10.36,1.702,20.69,4.244,30.75  c10.869,33.9,66.774,33.82,77.63-0.048c2.527-10.025,3.815-20.402,4.244-30.751C92.538,27.208,92.233,19.416,92.005,11.624z   M23.388,55.393c1.037,0.895,2.385,1.44,3.862,1.44c3.268,0,5.917-2.648,5.917-5.916c0-3.269-2.649-5.917-5.917-5.917  c-0.759,0-1.482,0.148-2.149,0.409c1.55-1.506,3.661-2.436,5.993-2.436c4.752,0,8.605,3.854,8.605,8.606s-3.854,8.605-8.605,8.605  C27.712,60.186,24.794,58.229,23.388,55.393z M57.235,83.292c-3.227,0-6.014-1.888-7.336-4.61c-1.232,2.944-4.142,5.018-7.528,5.018  c-3.519,0-6.516-2.242-7.66-5.373l1.457-0.26c1.002,2.447,3.4,4.181,6.203,4.181c3.697,0,6.705-3.011,6.705-6.706  c0-2.396-1.273-4.484-3.168-5.674c0.113-0.486,0.173-0.982,0.181-1.492h7.065c-0.048,0.485-0.055,0.973,0.023,1.457  c-1.598,1.229-2.646,3.137-2.646,5.303c0,3.696,3.009,6.705,6.706,6.705c2.594,0,4.822-1.494,5.938-3.656l1.529,0.229  C63.438,81.279,60.569,83.292,57.235,83.292z M68.669,60.186c-3.11,0-5.825-1.655-7.337-4.128c0.862,0.491,1.857,0.775,2.921,0.775  c3.268,0,5.917-2.648,5.917-5.916c0-3.269-2.649-5.917-5.917-5.917c-0.439,0-0.866,0.051-1.278,0.142  c1.518-1.344,3.508-2.167,5.694-2.167c4.752,0,8.606,3.854,8.606,8.606C77.275,56.331,73.423,60.186,68.669,60.186z" />
                        </svg>

                        {/* <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
                            <polygon points="13,2 23,7.5 23,18.5 13,24 3,18.5 3,7.5" stroke="#BED754" strokeWidth="1.2" fill="none" opacity="0.9" />
                            <polygon points="13,6 19.5,9.75 19.5,17.25 13,21 6.5,17.25 6.5,9.75" stroke="#BED754" strokeWidth="0.6" fill="none" opacity="0.3" />
                            <circle cx="13" cy="13" r="2.8" fill="#BED754" opacity="0.95" />
                            <line x1="13" y1="6.5" x2="13" y2="10.2" stroke="#BED754" strokeWidth="0.7" opacity="0.4" />
                            <line x1="13" y1="15.8" x2="13" y2="19.5" stroke="#BED754" strokeWidth="0.7" opacity="0.4" />
                            <line x1="6.8" y1="9.8" x2="10" y2="11.5" stroke="#BED754" strokeWidth="0.7" opacity="0.4" />
                            <line x1="16" y1="14.5" x2="19.2" y2="16.2" stroke="#BED754" strokeWidth="0.7" opacity="0.4" />
                            <line x1="19.2" y1="9.8" x2="16" y2="11.5" stroke="#BED754" strokeWidth="0.7" opacity="0.4" />
                            <line x1="10" y1="14.5" x2="6.8" y2="16.2" stroke="#BED754" strokeWidth="0.7" opacity="0.4" />
                        </svg> */}
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