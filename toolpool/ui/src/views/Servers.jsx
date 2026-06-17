import { useState, useEffect } from "react"
import { api } from "../api.js"
import { useFetch } from "../hooks/useFetch.js"
import {
    Tag, Card, CardHead, Empty, Spinner, Err, SidebarBtn, ProvenanceDot,
} from "../components/ui.jsx"

// ---------------------------------------------------------------------------
// Client → group / label mapping
// ---------------------------------------------------------------------------

const CLIENT_META = {
    claude_desktop:       { group: "Claude",    label: "Claude Desktop", scope: null },
    claude_code_user:     { group: "Claude",    label: "Claude Code",    scope: "global" },
    claude_code_project:  { group: "Claude",    label: "Claude Code",    scope: "project" },
    cursor_user:          { group: "Cursor",    label: "Cursor",         scope: "global" },
    cursor_project:       { group: "Cursor",    label: "Cursor",         scope: "project" },
    windsurf:             { group: "Windsurf",  label: "Windsurf",       scope: null },
    codex:                { group: "Codex",     label: "Codex",          scope: "global" },
    codex_project:        { group: "Codex",     label: "Codex",          scope: "project" },
    mcp_json_user:        { group: "MCP JSON",  label: "MCP JSON",       scope: "global" },
    mcp_json_project:     { group: "MCP JSON",  label: "MCP JSON",       scope: "project" },
    custom:               { group: "Custom",    label: "Custom",         scope: null },
}

const GROUP_ORDER = ["Claude", "Cursor", "Windsurf", "Codex", "MCP JSON", "Docker MCP", "Custom"]

function classifyClient(client) {
    if (!client) return { group: "Unknown", label: "—", scope: null }
    if (client.startsWith("docker_mcp:")) {
        const profile = client.split(":").slice(1).join(":")
        return { group: `Docker MCP · ${profile}`, label: `Docker MCP · ${profile}`, scope: null }
    }
    return CLIENT_META[client] || { group: client, label: client, scope: null }
}

function ScopeTag({ scope }) {
    if (!scope) return null
    const isProject = scope === "project"
    return (
        <span style={{
            padding: "1px 5px", borderRadius: 3,
            border: `1px solid ${isProject ? "var(--lime-dim)" : "var(--border)"}`,
            fontSize: 9, letterSpacing: "0.06em", textTransform: "uppercase",
            color: isProject ? "var(--lime-dim)" : "var(--text3)",
            fontFamily: "Menlo, Consolas, monospace", flexShrink: 0,
        }}>{scope}</span>
    )
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
// Vendor mini-dashboard card
// ---------------------------------------------------------------------------

function VendorCard({ group, toolCount, active, onClick }) {
    return (
        <div onClick={onClick} style={{
            padding: "14px 18px", minWidth: 120, flex: "0 0 auto",
            borderRadius: "var(--radius-lg)",
            border: `1px solid ${active ? "var(--border3)" : "var(--border)"}`,
            background: active ? "var(--surface3)" : "var(--surface)",
            boxShadow: active ? "var(--shadow-accent)" : "var(--shadow)",
            cursor: "pointer", transition: "all 0.12s",
        }}>
            <div style={{
                fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase",
                color: active ? "var(--cream)" : "var(--text3)",
                fontFamily: "Menlo, Consolas, monospace", marginBottom: 12,
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                maxWidth: 140,
            }}>{group.key}</div>
            <div style={{ display: "flex", gap: 18, alignItems: "flex-end" }}>
                <div>
                    <div style={{
                        fontFamily: "Georgia, serif", fontSize: 26, fontWeight: 300,
                        lineHeight: 1, color: "var(--cream)", fontStyle: "italic",
                    }}>{group.servers.length}</div>
                    <div style={{ fontSize: 9, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", marginTop: 3 }}>servers</div>
                </div>
                <div>
                    <div style={{
                        fontFamily: "Georgia, serif", fontSize: 26, fontWeight: 300,
                        lineHeight: 1, color: "var(--yellow-muted)", fontStyle: "italic",
                    }}>{toolCount}</div>
                    <div style={{ fontSize: 9, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", marginTop: 3 }}>tools</div>
                </div>
            </div>
        </div>
    )
}

// ---------------------------------------------------------------------------
// View
// ---------------------------------------------------------------------------

export function Servers({ initialSel }) {
    const { data: list, loading, error } = useFetch(api.servers)
    const [sel, setSel] = useState(null)
    const [search, setSearch] = useState("")
    const [activeVendor, setActiveVendor] = useState(null)
    const { data: detail, loading: dLoading } = useFetch(
        () => sel ? api.server(sel) : Promise.resolve(null), [sel]
    )

    useEffect(() => {
        if (!list?.servers?.length) return
        if (initialSel) setSel(initialSel)
        else if (!sel) setSel(list.servers[0].id)
    }, [list, initialSel])

    if (loading) return <Spinner />
    if (error) return <Err msg={error} />

    const allGroups = groupServers(list.servers)

    // Vendor cards always show all groups with full counts
    const vendorStats = allGroups.map(g => ({
        ...g,
        toolCount: g.servers.reduce((n, s) => n + (s.discovered_tool_count || 0), 0),
    }))

    // Sidebar: filter by active vendor and search
    const q = search.toLowerCase()
    const filteredGroups = allGroups
        .filter(g => !activeVendor || g.key === activeVendor)
        .map(g => ({
            ...g,
            servers: q ? g.servers.filter(s => s.name.toLowerCase().includes(q)) : g.servers,
        }))
        .filter(g => g.servers.length > 0)

    const toggleVendor = (key) => {
        setActiveVendor(v => v === key ? null : key)
        setSearch("")
    }

    return (
        <div className="fade" style={{ padding: "32px 0" }}>
            <h1 style={{ fontFamily: "Calibri, Arial, sans-serif", fontWeight: 400, fontSize: 36, color: "var(--cream)", marginBottom: 24 }}>
                MCP Servers
            </h1>

            {/* Vendor mini-dashboard */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 24 }}>
                {vendorStats.map(g => (
                    <VendorCard
                        key={g.key}
                        group={g}
                        toolCount={g.toolCount}
                        active={activeVendor === g.key}
                        onClick={() => toggleVendor(g.key)}
                    />
                ))}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "210px 1fr", gap: 14, alignItems: "start" }}>

                {/* Sidebar */}
                <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                    {/* Search */}
                    <input
                        type="text"
                        placeholder={activeVendor ? `Search in ${activeVendor}…` : "Search all servers…"}
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        style={{
                            width: "100%", padding: "7px 10px", marginBottom: 10,
                            background: "var(--surface2)", border: "1px solid var(--border)",
                            borderRadius: "var(--radius)", color: "var(--cream)",
                            fontSize: 12, fontFamily: "Menlo, Consolas, monospace",
                            outline: "none", boxSizing: "border-box",
                        }}
                    />

                    {filteredGroups.length === 0
                        ? <div style={{ padding: "18px 10px", fontSize: 11, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace" }}>no results</div>
                        : filteredGroups.map((group, gi) => (
                            <div key={group.key} style={{ marginBottom: gi < filteredGroups.length - 1 ? 10 : 0 }}>
                                <div style={{
                                    padding: "6px 10px 4px", fontSize: 9, fontWeight: 700,
                                    letterSpacing: "0.12em", textTransform: "uppercase",
                                    color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace",
                                    display: "flex", alignItems: "center", justifyContent: "space-between",
                                }}>
                                    <span>{group.key}</span>
                                    <span style={{ opacity: 0.5 }}>{group.servers.length}</span>
                                </div>
                                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                    {group.servers.map(s => {
                                        const { scope } = classifyClient(s.client)
                                        return (
                                            <SidebarBtn key={s.id} active={sel === s.id} onClick={() => setSel(s.id)}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                                                    <ProvenanceDot server={s} />
                                                    <div style={{ fontWeight: 500, fontSize: 13, color: sel === s.id ? "var(--cream)" : "var(--text2)" }}>{s.name}</div>
                                                </div>
                                                <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", marginTop: 2 }}>
                                                    <span>{s.agent_count}a · {s.transport}</span>
                                                    <ScopeTag scope={scope} />
                                                </div>
                                            </SidebarBtn>
                                        )
                                    })}
                                </div>
                            </div>
                        ))
                    }
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
                                </div>
                                <p style={{ fontSize: 13, color: "var(--text2)", marginBottom: 16 }}>{detail.description}</p>
                                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
                                    {[
                                        ["Transport", detail.transport],
                                        ["Source", classifyClient(detail.client).label],
                                        ["Package", detail.package],
                                        ["Command", detail.command ? `${detail.command} ${(detail.args || []).join(" ")}` : "—"],
                                    ].map(([k, v]) => (
                                        <div key={k} style={{ padding: "11px 14px", background: "var(--surface2)", borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
                                            <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text3)", marginBottom: 5, fontFamily: "Menlo, Consolas, monospace" }}>{k}</div>
                                            {k === "Source"
                                                ? <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                                                    <span style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 11, color: "var(--cream)" }}>{v || "—"}</span>
                                                    <ScopeTag scope={classifyClient(detail.client).scope} />
                                                  </div>
                                                : <div style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 11, color: "var(--cream)", wordBreak: "break-all" }}>{v || "—"}</div>
                                            }
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

                    </div>
                )}
            </div>
        </div>
    )
}
