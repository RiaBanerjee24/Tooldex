import { useState, useEffect } from "react"
import { api } from "../api.js"
import { useFetch } from "../hooks/useFetch.js"
import {
    Tag, RiskBadge, AccessBadge, Card, CardHead, Empty, Spinner, Err, SidebarBtn,
    ProvenanceTag, ProvenanceDot,
} from "../components/ui.jsx"

// ---------------------------------------------------------------------------
// Client → group / label mapping
// ---------------------------------------------------------------------------

const CLIENT_META = {
    claude_desktop:       { group: "Claude",    label: "Claude Desktop" },
    claude_code_user:     { group: "Claude",    label: "Claude Code" },
    claude_code_project:  { group: "Claude",    label: "Claude Code (project)" },
    cursor_user:          { group: "Cursor",    label: "Cursor" },
    cursor_project:       { group: "Cursor",    label: "Cursor (project)" },
    windsurf:             { group: "Windsurf",  label: "Windsurf" },
    codex:                { group: "Codex",     label: "Codex" },
    codex_project:        { group: "Codex",     label: "Codex (project)" },
    custom:               { group: "Custom",    label: "Custom" },
}

const GROUP_ORDER = ["Claude", "Cursor", "Windsurf", "Codex", "Docker MCP", "Custom"]

function classifyClient(client) {
    if (!client) return { group: "Unknown", label: "—" }
    if (client.startsWith("docker_mcp:")) {
        const profile = client.split(":").slice(1).join(":")
        return { group: `Docker MCP · ${profile}`, label: `Docker MCP · ${profile}` }
    }
    return CLIENT_META[client] || { group: client, label: client }
}

function groupServers(servers) {
    const groups = {}
    for (const srv of servers || []) {
        const { group, label } = classifyClient(srv.client)
        if (!groups[group]) groups[group] = { key: group, label, servers: [] }
        groups[group].servers.push(srv)
    }
    return Object.values(groups).sort((a, b) => {
        const ai = GROUP_ORDER.findIndex(g => a.key.startsWith(g))
        const bi = GROUP_ORDER.findIndex(g => b.key.startsWith(g))
        const an = ai === -1 ? GROUP_ORDER.length : ai
        const bn = bi === -1 ? GROUP_ORDER.length : bi
        if (an !== bn) return an - bn
        return a.label.localeCompare(b.label)
    })
}

// ---------------------------------------------------------------------------
// View
// ---------------------------------------------------------------------------

export function Servers() {
    const { data: list, loading, error } = useFetch(api.servers)
    const [sel, setSel] = useState(null)
    const { data: detail, loading: dLoading } = useFetch(
        () => sel ? api.server(sel) : Promise.resolve(null), [sel]
    )
    useEffect(() => { if (list?.servers?.length && !sel) setSel(list.servers[0].id) }, [list])

    if (loading) return <Spinner />
    if (error) return <Err msg={error} />

    const groups = groupServers(list.servers)

    return (
        <div className="fade" style={{ padding: "32px 0" }}>
            <h1 style={{ fontFamily: "Calibri, Arial, sans-serif", fontWeight: 400, fontSize: 36, color: "var(--cream)", marginBottom: 24 }}>
                MCP Servers
            </h1>
            <div style={{ display: "grid", gridTemplateColumns: "210px 1fr", gap: 14, alignItems: "start" }}>

                {/* Grouped sidebar */}
                <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                    {groups.map((group, gi) => (
                        <div key={group.key} style={{ marginBottom: gi < groups.length - 1 ? 10 : 0 }}>
                            <div style={{
                                padding: "6px 10px 4px",
                                fontSize: 9,
                                fontWeight: 700,
                                letterSpacing: "0.12em",
                                textTransform: "uppercase",
                                color: "var(--text3)",
                                fontFamily: "Menlo, Consolas, monospace",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                            }}>
                                <span>{group.label}</span>
                                <span style={{ opacity: 0.5 }}>{group.servers.length}</span>
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                {group.servers.map(s => (
                                    <SidebarBtn key={s.id} active={sel === s.id} onClick={() => setSel(s.id)}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                                            <ProvenanceDot server={s} />
                                            <div style={{ fontWeight: 500, fontSize: 13, color: sel === s.id ? "var(--cream)" : "var(--text2)" }}>{s.name}</div>
                                        </div>
                                        <div style={{ fontSize: 10, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", marginTop: 2 }}>
                                            {s.agent_count}a · {s.transport}
                                        </div>
                                    </SidebarBtn>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>

                {/* Detail panel */}
                {dLoading ? <Spinner /> : detail && (
                    <div className="fade" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                        <Card highlight>
                            <div style={{ padding: "20px 22px" }}>
                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6, gap: 12 }}>
                                    <h2 style={{ fontFamily: "Calibri, Arial, sans-serif", fontWeight: 400, fontSize: 24, color: "var(--cream)", margin: 0 }}>
                                        {detail.name}
                                    </h2>
                                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                        <ClientTag client={detail.client} />
                                        <ProvenanceTag server={detail} />
                                    </div>
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
                            <CardHead right={<Tag>{detail.discovered_tools?.length || 0}</Tag>}>Tools</CardHead>
                            {!detail.discovered_tools?.length
                                ? <Empty msg="no tools discovered" />
                                : (
                                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                                        <tbody>
                                            {detail.discovered_tools.map((tool, ti) => (
                                                <tr key={ti} style={{ borderBottom: ti < detail.discovered_tools.length - 1 ? "1px solid var(--border)" : "none" }}>
                                                    <td style={{ padding: "10px 18px", width: 220, verticalAlign: "top" }}>
                                                        <span style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 12, color: "var(--cream)", fontWeight: 500 }}>{tool.name}</span>
                                                    </td>
                                                    <td style={{ padding: "10px 18px", verticalAlign: "top" }}>
                                                        <span style={{ fontSize: 12, color: "var(--text2)" }}>{tool.description || "—"}</span>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                )
                            }
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

function ClientTag({ client }) {
    if (!client) return null
    const { label } = classifyClient(client)
    return (
        <span style={{
            fontSize: 10,
            fontFamily: "Menlo, Consolas, monospace",
            fontWeight: 500,
            padding: "2px 8px",
            borderRadius: 3,
            background: "var(--surface2)",
            border: "1px solid var(--border)",
            color: "var(--text2)",
            letterSpacing: "0.04em",
        }}>
            {label}
        </span>
    )
}
