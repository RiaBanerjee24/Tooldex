import { Card, CardHead, Spinner, StatCard } from "../components/ui.jsx"

function RescanButton({ onRescan, rescanState, rescanSeconds }) {
    const label = rescanState === "scanning" ? `scanning… ${rescanSeconds}s` : rescanState === "done" ? "done ✓" : "rescan"
    const color = rescanState === "scanning" ? "var(--yellow-muted)" : rescanState === "done" ? "var(--lime)" : "var(--text3)"
    const borderColor = rescanState === "scanning" ? "var(--yellow-muted)" : "var(--border2)"

    return (
        <button onClick={onRescan} style={{
            padding: "6px 14px", background: "var(--surface2)",
            border: `1px solid ${borderColor}`,
            borderRadius: "var(--radius)", cursor: rescanState === "scanning" ? "default" : "pointer",
            fontSize: 11, color, fontFamily: "Menlo, Consolas, monospace",
            letterSpacing: "0.04em", transition: "color 0.2s, border-color 0.2s",
        }}>
            {label}
        </button>
    )
}

export function Dashboard({ health, serversData, onNavigateServers, onNavigateToServer, onRescan, rescanState, rescanSeconds }) {
    if (!health || !serversData) return <Spinner />
    const servers = serversData.servers || []
    const discoveredTools = servers.reduce((n, s) => n + (s.discovered_tool_count || 0), 0)


    const connected = servers.filter(s => {
        if (s.probe_status != null) return s.probe_status === "found"
        return s.connection_status === "connected" || s.connection_status === "enabled"
    }).length
    const failed = servers.filter(s => {
        if (s.probe_status != null) return s.probe_status !== "found"
        return s.connection_status === "failed" || s.connection_status === "disabled"
    }).length

    const statusPills = (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 10, color: "var(--lime)", fontFamily: "var(--font-mono)" }}>
                {connected} connected
            </span>
            {failed > 0 && <>
                <span style={{ color: "var(--border2)", fontSize: 10 }}>·</span>
                <span style={{ fontSize: 10, color: "var(--red)", fontFamily: "var(--font-mono)" }}>
                    {failed} failed
                </span>
            </>}
        </div>
    )

    return (
        <div className="fade" style={{ padding: "32px 0" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 28 }}>
                <h1 style={{
                    fontFamily: "Calibri, Arial, sans-serif", fontWeight: 400,
                    fontSize: 36, color: "var(--cream)", letterSpacing: "-0.01em", lineHeight: 1.1, margin: 0,
                }}>
                    Overview
                </h1>
                <RescanButton onRescan={onRescan} rescanState={rescanState} rescanSeconds={rescanSeconds} />
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
                <CardHead right={servers.length > 0 ? statusPills : null}>MCP Servers</CardHead>
                {servers.slice(0, 5).map((srv) => (
                    <div key={srv.id} onClick={() => onNavigateToServer(srv.id)} style={{
                        display: "flex", alignItems: "center", justifyContent: "space-between",
                        padding: "12px 18px",
                        borderBottom: "1px solid var(--border)",
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
                {servers.length > 5 && (
                    <div onClick={onNavigateServers} style={{
                        display: "flex", alignItems: "center", justifyContent: "space-between",
                        padding: "11px 18px", cursor: "pointer",
                        background: "var(--surface2)",
                    }}>
                        <span style={{ fontSize: 12, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace" }}>
                            +{servers.length - 5} more
                        </span>
                        <span style={{ fontSize: 12, color: "var(--yellow-muted)", fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.04em" }}>
                            View All →
                        </span>
                    </div>
                )}
            </Card>
        </div>
    )
}
