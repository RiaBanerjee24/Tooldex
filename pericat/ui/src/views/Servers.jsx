import { useState, useEffect } from "react"
import { api } from "../api.js"
import { useFetch } from "../hooks/useFetch.js"
import {
    Tag, RiskBadge, AccessBadge, Card, CardHead, Empty, Spinner, Err, SidebarBtn,
    ProvenanceTag, ProvenanceDot, ProvenanceIcon,
} from "../components/ui.jsx"

export function Servers() {
    const { data: list, loading, error } = useFetch(api.servers)
    const [sel, setSel] = useState(null)
    const { data: detail, loading: dLoading } = useFetch(
        () => sel ? api.server(sel) : Promise.resolve(null), [sel]
    )
    useEffect(() => { if (list?.servers?.length && !sel) setSel(list.servers[0].id) }, [list])

    if (loading) return <Spinner />
    if (error) return <Err msg={error} />

    return (
        <div className="fade" style={{ padding: "32px 0" }}>
            <h1 style={{ fontFamily: "Calibri, Arial, sans-serif", fontWeight: 400, fontSize: 36, color: "var(--cream)", marginBottom: 24 }}>
                MCP Servers
            </h1>
            <div style={{ display: "grid", gridTemplateColumns: "210px 1fr", gap: 14, alignItems: "start" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    {list.servers?.map(s => (
                        <SidebarBtn key={s.id} active={sel === s.id} onClick={() => setSel(s.id)}>
                            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                                <ProvenanceDot server={s} />
                                <div style={{ fontWeight: 500, fontSize: 13, color: sel === s.id ? "var(--cream)" : "var(--text2)" }}>{s.name}</div>
                            </div>
                            <div style={{ fontSize: 10, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", marginTop: 2 }}>{s.agent_count}a · {s.transport}</div>
                        </SidebarBtn>
                    ))}
                </div>

                {dLoading ? <Spinner /> : detail && (
                    <div className="fade" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                        <Card highlight>
                            <div style={{ padding: "20px 22px" }}>
                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6, gap: 12 }}>
                                    <h2 style={{ fontFamily: "Calibri, Arial, sans-serif", fontWeight: 400, fontSize: 24, color: "var(--cream)", margin: 0, display: "flex", alignItems: "center" }}>
                                        {detail.name}
                                        <ProvenanceIcon server={detail} />
                                    </h2>
                                    <ProvenanceTag server={detail} />
                                </div>
                                <p style={{ fontSize: 13, color: "var(--text2)", marginBottom: 16 }}>{detail.description}</p>
                                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
                                    {[
                                        ["Transport", detail.transport],
                                        ["Package", detail.package],
                                        ["Command", detail.command ? `${detail.command} ${(detail.args || []).join(" ")}` : "—"],
                                    ].map(([k, v]) => (
                                        <div key={k} style={{ padding: "11px 14px", background: "var(--surface2)", borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
                                            <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text3)", marginBottom: 5, fontFamily: "Menlo, Consolas, monospace" }}>{k}</div>
                                            <div style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 11, color: "var(--cream)", wordBreak: "break-all" }}>{v || "—"}</div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </Card>

                        <Card>
                            <CardHead>Connected Agents</CardHead>
                            {!detail.agents_connected?.length
                                ? <Empty msg="no agents connected" />
                                : detail.agents_connected?.map((agent, ai) => (
                                    <div key={ai} style={{ borderBottom: ai < detail.agents_connected.length - 1 ? "1px solid var(--border)" : "none" }}>
                                        <div style={{ padding: "9px 18px", background: "var(--surface2)", borderBottom: "1px solid var(--border)", fontWeight: 500, fontSize: 13, color: "var(--cream)" }}>
                                            {agent.name}
                                        </div>
                                        <table style={{ width: "100%", borderCollapse: "collapse" }}>
                                            <tbody>
                                                {agent.tools?.map((tool, ti) => (
                                                    <tr key={ti} style={{ borderBottom: "1px solid var(--border)" }}>
                                                        <td style={{ padding: "10px 18px", width: 220 }}>
                                                            <span style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 12, color: "var(--cream)" }}>{tool.name}</span>
                                                        </td>
                                                        <td style={{ padding: "10px 18px", width: 100 }}><RiskBadge risk={tool.risk} /></td>
                                                        <td style={{ padding: "10px 18px" }}><AccessBadge access={tool.effective_access} /></td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                ))
                            }
                        </Card>
                    </div>
                )}
            </div>
        </div>
    )
}