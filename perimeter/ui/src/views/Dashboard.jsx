import { Card, CardHead, Dot, Tag, Spinner, StatCard } from "../components/ui.jsx"

export function Dashboard({ health, agentsData, serversData }) {
    if (!health || !agentsData || !serversData) return <Spinner />
    const agents = agentsData.agents || []
    const servers = serversData.servers || []
    const totalTools = agents.reduce((n, a) => n + (a.total_tools || 0), 0)

    return (
        <div className="fade" style={{ padding: "32px 0" }}>
            <div style={{ marginBottom: 28 }}>
                <h1 style={{ fontFamily: "Calibri, Arial, sans-serif", fontWeight: 400, fontSize: 36, color: "var(--cream)", letterSpacing: "-0.01em", lineHeight: 1.1 }}>
                    Overview
                </h1>
                <div style={{ color: "var(--text3)", fontSize: 12, fontFamily: "Menlo, Consolas, monospace", marginTop: 6 }}>
                    {health.config?.name} · {health.config?.owner}
                </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 28 }}>
                <StatCard label="Agents" value={agentsData.total} sub={`${agents.filter(a => a.status === "active").length} active`} />
                <StatCard label="MCP Servers" value={serversData.total} sub="configured" />
                <StatCard label="Tools Tracked" value={totalTools} sub="across all agents" />
                <StatCard label="Policy Engines" value={health.config?.policy_engines} sub="declared" />
            </div>

            {health.warnings?.length > 0 && (
                <div style={{ marginBottom: 20 }}>
                    {health.warnings.map((w, i) => (
                        <div key={i} style={{
                            padding: "10px 14px", marginBottom: 6, borderRadius: "var(--radius)",
                            background: "var(--orange-bg)", border: "1px solid var(--orange-border)",
                            fontSize: 12, color: "var(--orange)", fontFamily: "Menlo, Consolas, monospace",
                        }}>⚠ {w}</div>
                    ))}
                </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <Card>
                    <CardHead>Agent Fleet</CardHead>
                    {agents.map((agent, i) => (
                        <div key={agent.id} style={{
                            display: "flex", alignItems: "center", justifyContent: "space-between",
                            padding: "12px 18px",
                            borderBottom: i < agents.length - 1 ? "1px solid var(--border)" : "none",
                        }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                <Dot on={agent.status === "active"} />
                                <span style={{ fontWeight: 500, fontSize: 13, color: "var(--cream)" }}>{agent.name}</span>
                                {agent.background && <Tag color="var(--orange)">bg</Tag>}
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
                                <span style={{ fontFamily: "Menlo, Consolas, monospace", color: "var(--text2)" }}>
                                    {agent.total_tools}{agent.total_tools === 1 ? " tool" : " tools"} · {agent.servers?.length || 0}{agent.servers?.length === 1 ? " server" : " servers"}
                                </span>
                                {agent.policy_engine ? <Tag color="var(--lime-dim)">{agent.policy_engine}</Tag> : <Tag>no policy</Tag>}
                            </div>
                        </div>
                    ))}
                </Card>

                <Card>
                    <CardHead>MCP Servers</CardHead>
                    {servers.map((srv, i) => (
                        <div key={srv.id} style={{
                            display: "flex", alignItems: "center", justifyContent: "space-between",
                            padding: "12px 18px",
                            borderBottom: i < servers.length - 1 ? "1px solid var(--border)" : "none",
                        }}>
                            <div>
                                <div style={{ fontWeight: 500, fontSize: 13, color: "var(--cream)" }}>{srv.name}</div>
                                <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>{srv.description}</div>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
                                <span style={{ fontFamily: "Menlo, Consolas, monospace", color: "var(--text3)" }}>{srv.transport}</span>
                                <span style={{ color: "var(--border2)" }}>·</span>
                                <span style={{ color: "var(--text2)" }}>{srv.agent_count} agents</span>
                            </div>
                        </div>
                    ))}
                </Card>
            </div>
        </div>
    )
}