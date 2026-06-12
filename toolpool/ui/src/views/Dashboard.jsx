import { Card, CardHead, Spinner, StatCard } from "../components/ui.jsx"

export function Dashboard({ health, serversData, onNavigateServers, onNavigateToServer }) {
    if (!health || !serversData) return <Spinner />
    const servers = serversData.servers || []
    const discoveredTools = servers.reduce((n, s) => n + (s.discovered_tool_count || 0), 0)

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

            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 14, marginBottom: 28 }}>
                <StatCard label="MCP Servers" value={serversData.total} sub="configured" onClick={onNavigateServers} />
                <StatCard label="Tools Tracked" value={discoveredTools} sub="via MCP servers" />
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

            <Card>
                <CardHead>MCP Servers</CardHead>
                {servers.map((srv, i) => (
                    <div key={srv.id} onClick={() => onNavigateToServer(srv.id)} style={{
                        display: "flex", alignItems: "center", justifyContent: "space-between",
                        padding: "12px 18px",
                        borderBottom: i < servers.length - 1 ? "1px solid var(--border)" : "none",
                        cursor: "pointer",
                    }}>
                        <div>
                            <div style={{ fontWeight: 500, fontSize: 13, color: "var(--cream)" }}>{srv.name}</div>
                            <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>{srv.description}</div>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
                            <span style={{ fontFamily: "Menlo, Consolas, monospace", color: "var(--text3)" }}>{srv.transport}</span>
                        </div>
                    </div>
                ))}
            </Card>
        </div>
    )
}