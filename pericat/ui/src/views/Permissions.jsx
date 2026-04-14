import { useState } from "react"
import { api } from "../api.js"
import { useFetch } from "../hooks/useFetch.js"
import { ACCESS } from "../constants.js"
import { Card, Spinner, Err } from "../components/ui.jsx"

export function Permissions() {
    const { data, loading, error } = useFetch(api.matrix)
    const [filter, setFilter] = useState("all")

    if (loading) return <Spinner />
    if (error) return <Err msg={error} />
    if (!data) return null

    const { matrix, tools, agents } = data

    return (
        <div className="fade" style={{ padding: "32px 0" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 24 }}>
                <h1 style={{ fontFamily: "Calibri, Arial, sans-serif", fontWeight: 400, fontSize: 36, color: "var(--cream)" }}>
                    Permission Matrix
                </h1>
                <div style={{ display: "flex", gap: 5 }}>
                    {["all", "allowed", "denied", "partial"].map(f => (
                        <button key={f} onClick={() => setFilter(f)} style={{
                            padding: "5px 14px", borderRadius: "var(--radius)", border: "1px solid",
                            borderColor: filter === f ? "var(--accent-border)" : "var(--border)",
                            background: filter === f ? "var(--accent-bg)" : "transparent",
                            color: filter === f ? "var(--cream)" : "var(--text3)",
                            fontWeight: filter === f ? 600 : 400, fontSize: 11,
                            textTransform: "capitalize", fontFamily: "Menlo, Consolas, monospace", transition: "all 0.12s",
                        }}>{f}</button>
                    ))}
                </div>
            </div>

            <Card style={{ overflowX: "auto" }}>
                <table style={{ borderCollapse: "collapse", width: "100%" }}>
                    <thead>
                        <tr>
                            <th style={{ padding: "12px 18px", background: "var(--surface2)", borderBottom: "2px solid var(--border2)", borderRight: "2px solid var(--border2)", minWidth: 160, position: "sticky", left: 0, zIndex: 2, textAlign: "left", fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace" }}>
                                agent · tool →
                            </th>
                            {tools.map(tool => (
                                <th key={tool} style={{ background: "var(--surface2)", borderBottom: "2px solid var(--border2)", borderRight: "1px solid var(--border)", height: 120, verticalAlign: "bottom", padding: "8px 10px" }}>
                                    <div style={{ writingMode: "vertical-lr", transform: "rotate(180deg)", fontFamily: "Menlo, Consolas, monospace", fontSize: 11, fontWeight: 400, color: "var(--text2)", whiteSpace: "nowrap", paddingBottom: 4 }}>{tool}</div>
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {agents.map((agentRef, ai) => {
                            const id = agentRef.id ?? agentRef
                            const row = matrix[id]
                            if (!row) return null
                            return (
                                <tr key={id} style={{ background: ai % 2 === 0 ? "var(--surface)" : "var(--surface2)" }}>
                                    <td style={{ padding: "11px 18px", borderBottom: "1px solid var(--border)", borderRight: "2px solid var(--border2)", position: "sticky", left: 0, zIndex: 1, background: ai % 2 === 0 ? "var(--surface)" : "var(--surface2)" }}>
                                        <div style={{ fontWeight: 500, fontSize: 13, color: "var(--cream)" }}>{row.agent_name}</div>
                                        {row.policy_engine && <div style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 10, color: "var(--lime-dim)", marginTop: 2 }}>{row.policy_engine}</div>}
                                    </td>
                                    {tools.map(tool => {
                                        const cell = row.tools?.[tool]
                                        const ea = cell?.effective_access ?? "not_configured"
                                        const a = ACCESS[ea] || ACCESS.not_configured
                                        const show = filter === "all" || ea === filter
                                        return (
                                            <td key={tool} style={{ borderBottom: "1px solid var(--border)", borderRight: "1px solid var(--border)", textAlign: "center", padding: "8px 6px" }}>
                                                {show && ea !== "not_configured"
                                                    ? <span title={`${row.agent_name} / ${tool}: ${ea}`} style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 28, height: 28, borderRadius: "var(--radius)", background: a.bg, border: `1px solid ${a.border}`, color: a.color, fontWeight: 700, fontSize: 13 }}>{a.symbol}</span>
                                                    : <span style={{ color: "var(--border2)" }}>—</span>
                                                }
                                            </td>
                                        )
                                    })}
                                </tr>
                            )
                        })}
                    </tbody>
                </table>
            </Card>

            <div style={{ display: "flex", gap: 18, marginTop: 14, flexWrap: "wrap" }}>
                {Object.entries(ACCESS).filter(([k]) => !["not_configured", "unknown"].includes(k)).map(([k, a]) => (
                    <div key={k} style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, color: "var(--text2)" }}>
                        <div style={{ width: 22, height: 22, borderRadius: "var(--radius)", background: a.bg, border: `1px solid ${a.border}`, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 12, color: a.color }}>{a.symbol}</div>
                        <span style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 11 }}>{a.label}</span>
                    </div>
                ))}
            </div>
        </div>
    )
}