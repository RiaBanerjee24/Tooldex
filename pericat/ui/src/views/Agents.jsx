import { useState, useEffect } from "react"
import { api } from "../api.js"
import { useFetch } from "../hooks/useFetch.js"
import { ACCESS } from "../constants.js"
import { Tag, RiskBadge, AccessBadge, Dot, Card, CardHead, Empty, Spinner, Err, SidebarBtn } from "../components/ui.jsx"

export function Agents() {
    const { data: list, loading, error } = useFetch(api.agents)
    const [sel, setSel] = useState(null)
    const { data: detail, loading: dLoading } = useFetch(
        () => sel ? api.agent(sel) : Promise.resolve(null), [sel]
    )
    useEffect(() => { if (list?.agents?.length && !sel) setSel(list.agents[0].id) }, [list])

    if (loading) return <Spinner />
    if (error) return <Err msg={error} />

    return (
        <div className="fade" style={{ padding: "32px 0" }}>
            <h1 style={{ fontFamily: "Calibri, Arial, sans-serif", fontWeight: 400, fontSize: 36, color: "var(--cream)", marginBottom: 24 }}>
                Agents
            </h1>
            <div style={{ display: "grid", gridTemplateColumns: "210px 1fr", gap: 14, alignItems: "start" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    {list.agents?.map(a => (
                        <SidebarBtn key={a.id} active={sel === a.id} onClick={() => setSel(a.id)}>
                            <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                                <Dot on={a.status === "active"} />
                                <div>
                                    <div style={{ fontWeight: 500, fontSize: 13, color: sel === a.id ? "var(--cream)" : "var(--text2)" }}>{a.name}</div>
                                    <div style={{ fontSize: 10, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", marginTop: 1 }}>{a.total_tools}t · {a.servers?.length || 0}s</div>
                                </div>
                            </div>
                        </SidebarBtn>
                    ))}
                </div>
                {dLoading ? <Spinner /> : detail && <AgentDetail agent={detail} />}
            </div>
        </div>
    )
}

function AgentDetail({ agent }) {
    return (
        <div className="fade" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Card highlight>
                <div style={{ padding: "20px 22px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                        <div>
                            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                                <Dot on={agent.status === "active"} />
                                <h2 style={{ fontFamily: "Calibri, Arial, sans-serif", fontWeight: 400, fontSize: 26, color: "var(--cream)" }}>{agent.name}</h2>
                                {agent.background && <Tag color="var(--orange)">background worker</Tag>}
                            </div>
                            <p style={{ fontSize: 13, color: "var(--text2)", marginBottom: 12 }}>{agent.description}</p>
                            <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>{agent.tags?.map(t => <Tag key={t}>{t}</Tag>)}</div>
                        </div>
                        <div style={{ textAlign: "right", fontSize: 11, fontFamily: "Menlo, Consolas, monospace", color: "var(--text3)", lineHeight: 2.2, flexShrink: 0, marginLeft: 24 }}>
                            <div><span>id </span><span style={{ color: "var(--text2)" }}>{agent.id}</span></div>
                            <div><span>fw </span><span style={{ color: "var(--text2)" }}>{agent.framework}</span></div>
                            <div><span>owner </span><span style={{ color: "var(--text2)" }}>{agent.owner}</span></div>
                        </div>
                    </div>
                </div>
            </Card>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <Card>
                    <CardHead>Identity</CardHead>
                    <div style={{ padding: "14px 18px" }}>
                        {[["Type", agent.identity?.type], ["Token Lifetime", agent.identity?.token_lifetime]].map(([k, v]) => (
                            <div key={k} style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                                <span style={{ fontSize: 11, color: "var(--text3)", letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "Menlo, Consolas, monospace" }}>{k}</span>
                                <span style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 12, color: "var(--cream)" }}>{v || "—"}</span>
                            </div>
                        ))}
                    </div>
                </Card>
                <Card>
                    <CardHead>Policy Engine</CardHead>
                    <div style={{ padding: "14px 18px" }}>
                        {agent.policy_engine
                            ? [["ID", agent.policy_engine.id], ["Engine", agent.policy_engine.engine], ["Type", agent.policy_engine.type], ["Source", agent.policy_engine.source]].map(([k, v]) => (
                                <div key={k} style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                                    <span style={{ fontSize: 11, color: "var(--text3)", letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "Menlo, Consolas, monospace" }}>{k}</span>
                                    <span style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 12, color: "var(--cream)" }}>{v || "—"}</span>
                                </div>
                            ))
                            : <Empty msg="no policy engine" />
                        }
                    </div>
                </Card>
            </div>

            {agent.servers?.map((srv, si) => (
                <Card key={si}>
                    <CardHead right={<Tag>{srv.transport}</Tag>}>{srv.name}</CardHead>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                        <thead>
                            <tr style={{ background: "var(--surface2)" }}>
                                {["Tool", "Risk", "Access", "Permissions"].map(h => (
                                    <th key={h} style={{ padding: "8px 18px", textAlign: "left", fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text3)", borderBottom: "1px solid var(--border)", fontFamily: "Menlo, Consolas, monospace" }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {srv.tools?.map((tool, ti) => (
                                <tr key={ti} style={{ borderBottom: "1px solid var(--border)" }}>
                                    <td style={{ padding: "11px 18px" }}>
                                        <span style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 12, color: "var(--cream)", fontWeight: 500 }}>{tool.name}</span>
                                    </td>
                                    <td style={{ padding: "11px 18px" }}><RiskBadge risk={tool.risk} /></td>
                                    <td style={{ padding: "11px 18px" }}><AccessBadge access={tool.effective_access} /></td>
                                    <td style={{ padding: "11px 18px" }}>
                                        {tool.permissions?.map((p, pi) => {
                                            const a = ACCESS[p.access] || ACCESS.unknown
                                            return (
                                                <div key={pi} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 11, marginBottom: 3, fontFamily: "Menlo, Consolas, monospace" }}>
                                                    <span style={{ color: a.color, fontWeight: 700 }}>{a.symbol}</span>
                                                    <span style={{ color: "var(--text2)" }}>{p.operations.join(", ")}</span>
                                                    <span style={{ color: "var(--text3)" }}>on</span>
                                                    <span style={{ color: "var(--cream)" }}>{p.on}</span>
                                                </div>
                                            )
                                        })}
                                        {tool.denied_by && <span style={{ fontSize: 11, color: "var(--text3)", fontStyle: "italic", fontFamily: "Menlo, Consolas, monospace" }}>{tool.denied_by}</span>}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </Card>
            ))}

            {agent.file_access?.length > 0 && (
                <Card>
                    <CardHead>File Access</CardHead>
                    {agent.file_access.map((fa, i) => (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 14, padding: "11px 18px", borderBottom: i < agent.file_access.length - 1 ? "1px solid var(--border)" : "none" }}>
                            <span style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 12, color: "var(--lime-dim)", flex: 1 }}>{fa.path}</span>
                            <Tag>{fa.permission}</Tag>
                            {fa.note && <span style={{ fontSize: 11, color: "var(--text3)" }}>{fa.note}</span>}
                        </div>
                    ))}
                </Card>
            )}

            {agent.servers?.length === 0 && <Card><Empty msg="no mcp server access — orchestration only" /></Card>}
        </div>
    )
}