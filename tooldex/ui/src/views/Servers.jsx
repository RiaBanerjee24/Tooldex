import { useState, useEffect, useRef } from "react"
import { api } from "../api.js"
import { useFetch } from "../hooks/useFetch.js"
import {
    Tag, Card, CardHead, Empty, Spinner, Err, SidebarBtn, ProvenanceDot,
} from "../components/ui.jsx"

// ---------------------------------------------------------------------------
// Copy config button
// ---------------------------------------------------------------------------

function buildCopyConfig(detail) {
    const key = detail.name || detail.id
    const cfg = {}
    if (detail.url) {
        cfg.type = detail.transport || "http"
        cfg.url = detail.url
        if (detail.headers && Object.keys(detail.headers).length > 0)
            cfg.headers = detail.headers
    } else {
        if (detail.command) cfg.command = detail.command
        if (detail.args?.length) cfg.args = detail.args
        if (detail.env && Object.keys(detail.env).length > 0) cfg.env = detail.env
    }
    return JSON.stringify({ mcpServers: { [key]: cfg } }, null, 2)
}

function CopyConfigButton({ detail }) {
    const [state, setState] = useState("idle") // idle | copied

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(buildCopyConfig(detail))
            setState("copied")
            setTimeout(() => setState("idle"), 2000)
        } catch {
            // fallback for older browsers
            const el = document.createElement("textarea")
            el.value = buildCopyConfig(detail)
            document.body.appendChild(el)
            el.select()
            document.execCommand("copy")
            document.body.removeChild(el)
            setState("copied")
            setTimeout(() => setState("idle"), 2000)
        }
    }

    return (
        <button onClick={handleCopy} style={{
            padding: "5px 12px", background: "var(--surface2)",
            border: "1px solid var(--border2)", borderRadius: "var(--radius)",
            cursor: "pointer", fontSize: 10,
            color: state === "copied" ? "var(--lime)" : "var(--text3)",
            fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.04em",
            transition: "color 0.2s", whiteSpace: "nowrap", flexShrink: 0,
        }}>
            {state === "copied" ? "copied ✓" : "copy config"}
        </button>
    )
}

// ---------------------------------------------------------------------------
// Per-server rescan button
// ---------------------------------------------------------------------------

function RescanServerButton({ serverId, onDone }) {
    const [state, setState] = useState("idle") // idle | scanning | done | error

    const handleClick = async () => {
        if (state === "scanning") return
        setState("scanning")
        try {
            await api.rescanServer(serverId)
            setState("done")
            onDone?.()
            setTimeout(() => setState("idle"), 2000)
        } catch {
            setState("error")
            setTimeout(() => setState("idle"), 2500)
        }
    }

    const label = state === "scanning" ? "scanning…"
        : state === "done" ? "done ✓"
        : state === "error" ? "failed ✗"
        : "rescan server"
    const color = state === "done" ? "var(--lime)"
        : state === "error" ? "var(--red)"
        : "var(--text3)"

    return (
        <button onClick={handleClick} style={{
            padding: "5px 12px", background: "var(--surface2)",
            border: "1px solid var(--border2)", borderRadius: "var(--radius)",
            cursor: state === "scanning" ? "default" : "pointer", fontSize: 10,
            color, fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.04em",
            transition: "color 0.2s", whiteSpace: "nowrap", flexShrink: 0,
            opacity: state === "scanning" ? 0.7 : 1,
        }}>
            {label}
        </button>
    )
}

// ---------------------------------------------------------------------------
// Rescan all button (header level)
// ---------------------------------------------------------------------------

function RescanAllButton({ onRescan, rescanState, rescanSeconds }) {
    const label = rescanState === "scanning" ? `scanning… ${rescanSeconds}s` : rescanState === "done" ? "done ✓" : "rescan all"
    const color = rescanState === "scanning" ? "var(--yellow-muted)" : rescanState === "done" ? "var(--lime)" : "var(--text3)"
    const borderColor = rescanState === "scanning" ? "var(--yellow-muted)" : "var(--border2)"

    return (
        <button onClick={onRescan} style={{
            padding: "6px 14px", background: "var(--surface2)",
            border: `1px solid ${borderColor}`, borderRadius: "var(--radius)",
            cursor: rescanState === "scanning" ? "default" : "pointer", fontSize: 11,
            color, fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.04em",
            transition: "color 0.2s, border-color 0.2s",
        }}>
            {label}
        </button>
    )
}

// ---------------------------------------------------------------------------
// Env vars table — shows redacted placeholder for sensitive values
// ---------------------------------------------------------------------------

function EnvTable({ env }) {
    if (!env || Object.keys(env).length === 0) return null
    const entries = Object.entries(env)
    return (
        <div style={{ marginTop: 10 }}>
            <div style={{
                fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase",
                color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", marginBottom: 6,
            }}>Environment</div>
            <div style={{
                background: "var(--surface2)", borderRadius: "var(--radius)",
                border: "1px solid var(--border)", overflow: "hidden",
            }}>
                {entries.map(([k, v], i) => (
                    <div key={k} style={{
                        display: "flex", alignItems: "center", gap: 12,
                        padding: "7px 12px",
                        borderBottom: i < entries.length - 1 ? "1px solid var(--border)" : "none",
                    }}>
                        <span style={{
                            fontFamily: "Menlo, Consolas, monospace", fontSize: 11,
                            color: "var(--cream)", minWidth: 180, flexShrink: 0,
                        }}>{k}</span>
                        {v === "***"
                            ? <span style={{
                                fontFamily: "Menlo, Consolas, monospace", fontSize: 10,
                                color: "var(--text3)", padding: "1px 6px",
                                background: "var(--surface3)", borderRadius: 3,
                                border: "1px solid var(--border2)", letterSpacing: "0.04em",
                            }}>redacted</span>
                            : <span style={{
                                fontFamily: "Menlo, Consolas, monospace", fontSize: 11,
                                color: "var(--text2)", wordBreak: "break-all",
                            }}>{v}</span>
                        }
                    </div>
                ))}
            </div>
        </div>
    )
}

// ---------------------------------------------------------------------------
// Last-scanned timestamp
// ---------------------------------------------------------------------------

function formatRelativeTime(isoStr) {
    if (!isoStr) return null
    const diff = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000)
    if (diff < 10) return "just now"
    if (diff < 60) return `${diff}s ago`
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
}

function ScannedAt({ timestamp }) {
    const [rel, setRel] = useState(() => formatRelativeTime(timestamp))
    useEffect(() => {
        setRel(formatRelativeTime(timestamp))
        const id = setInterval(() => setRel(formatRelativeTime(timestamp)), 30_000)
        return () => clearInterval(id)
    }, [timestamp])
    if (!rel) return null
    return (
        <span title={timestamp} style={{
            fontSize: 10, color: "var(--text3)",
            fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.04em",
        }}>
            scanned {rel}
        </span>
    )
}

// ---------------------------------------------------------------------------
// Client → group / label mapping
// ---------------------------------------------------------------------------

const CLIENT_META = {
    claude_code_user:     { group: "Claude",       label: "Claude Code",  scope: "global" },
    claude_code_project:  { group: "Claude",       label: "Claude Code",  scope: "project" },
    cursor_user:          { group: "Cursor",       label: "Cursor",       scope: "global" },
    cursor_project:       { group: "Cursor",       label: "Cursor",       scope: "project" },
    codex:                { group: "Codex",        label: "Codex",        scope: "global" },
    codex_project:        { group: "Codex",        label: "Codex",        scope: "project" },
    mcp_json_user:        { group: "MCP JSON",     label: "MCP JSON",     scope: "global" },
    mcp_json_project:     { group: "MCP JSON",     label: "MCP JSON",     scope: "project" },
    antigravity_user:        { group: "Gemini",   label: "Gemini (Antigravity)",  scope: "global" },
    antigravity_project:     { group: "Gemini",   label: "Gemini (Antigravity)",  scope: "project" },
    mcp_json_bare_project:   { group: "Custom",   label: "mcp.json",              scope: "project" },
    agents_user:             { group: "Custom",   label: "Agents",   scope: "global" },
    agents_user_dotfile:     { group: "Custom",   label: "Agents",   scope: "global" },
    agents_project:          { group: "Custom",   label: "Agents",   scope: "project" },
    agents_project_dotfile:  { group: "Custom",   label: "Agents",   scope: "project" },
    custom:                  { group: "Custom",   label: "Custom",                scope: null },
}

const GROUP_ORDER = ["Claude", "Cursor", "Codex", "MCP JSON", "Gemini", "Docker MCP", "Custom"]

function classifyClient(client) {
    if (!client) return { group: "Unknown", label: "—", scope: null }
    if (client.startsWith("docker_mcp:")) {
        const profile = client.split(":").slice(1).join(":")
        return { group: `Docker MCP · ${profile}`, label: `Docker MCP · ${profile}`, scope: null }
    }
    return CLIENT_META[client] || { group: client, label: client, scope: null }
}

const CONNECTION_STATUS = {
    connected:  { label: "connected",  color: "var(--lime)",         bg: "var(--lime-bg)",    border: "var(--lime-border)" },
    failed:     { label: "failed",     color: "var(--red)",          bg: "var(--red-bg)",     border: "var(--red-border)" },
    needs_auth: { label: "needs auth", color: "var(--yellow-muted)", bg: "var(--orange-bg)",  border: "var(--orange-border)" },
    enabled:    { label: "enabled",    color: "var(--lime)",         bg: "var(--lime-bg)",    border: "var(--lime-border)" },
    disabled:   { label: "disabled",   color: "var(--red)",          bg: "var(--red-bg)",     border: "var(--red-border)" },
    discovered: { label: "discovered", color: "var(--text3)",        bg: "var(--surface2)",   border: "var(--border)" },
}

const SHOW_STATUS = new Set(["failed", "disabled"])

// probe_status is the ground truth; fall back to connection_status for YAML-only manifests
function effectiveStatus(s) {
    if (s.probe_status != null) return s.probe_status === "found" ? null : "failed"
    return s.connection_status || null
}

function ConnectionStatusBadge({ status }) {
    if (!status || !SHOW_STATUS.has(status)) return null
    const c = CONNECTION_STATUS[status]
    if (!c) return null
    return (
        <span style={{
            padding: "1px 6px", borderRadius: 3,
            border: `1px solid ${c.border}`,
            fontSize: 9, letterSpacing: "0.06em", textTransform: "uppercase",
            color: c.color, background: c.bg,
            fontFamily: "Menlo, Consolas, monospace", flexShrink: 0,
        }}>{c.label}</span>
    )
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

function FilterChip({ label, checked, onChange }) {
    return (
        <label style={{
            display: "flex", alignItems: "center", gap: 5, cursor: "pointer",
            padding: "4px 8px", borderRadius: "var(--radius)",
            border: `1px solid ${checked ? "var(--border3)" : "var(--border)"}`,
            background: checked ? "var(--surface3)" : "transparent",
            fontSize: 10, color: checked ? "var(--cream)" : "var(--text3)",
            fontFamily: "Menlo, Consolas, monospace", userSelect: "none",
            transition: "all 0.1s", whiteSpace: "nowrap",
        }}>
            <input
                type="checkbox"
                checked={checked}
                onChange={onChange}
                style={{ accentColor: "var(--lime)", width: 10, height: 10, cursor: "pointer", flexShrink: 0 }}
            />
            {label}
        </label>
    )
}

export function Servers({ initialSel, scanKey = 0, onRescan, rescanState = "idle", rescanSeconds = 0 }) {
    const { data: list, loading, error, refetch: refetchList } = useFetch(api.servers, [scanKey])
    const [sel, setSel] = useState(null)
    const [search, setSearch] = useState("")
    const [activeVendor, setActiveVendor] = useState(null)
    const [filters, setFilters] = useState({ scope: new Set(), status: new Set(), transport: new Set() })
    const [filterOpen, setFilterOpen] = useState(false)
    const filterRef = useRef(null)
    const { data: detail, loading: dLoading, refetch: refetchDetail } = useFetch(
        () => sel ? api.server(sel) : Promise.resolve(null), [sel]
    )

    useEffect(() => {
        if (!list?.servers?.length) return
        if (initialSel) { setSel(initialSel); return }
        const ids = new Set(list.servers.map(s => s.id))
        if (!sel || !ids.has(sel)) setSel(list.servers[0].id)
    }, [list, initialSel])

    // Refresh list + detail when a global rescan completes
    useEffect(() => {
        if (rescanState === "done") { refetchList(); refetchDetail() }
    }, [rescanState])

    useEffect(() => {
        if (!filterOpen) return
        function handleClick(e) {
            if (filterRef.current && !filterRef.current.contains(e.target)) setFilterOpen(false)
        }
        document.addEventListener("mousedown", handleClick)
        return () => document.removeEventListener("mousedown", handleClick)
    }, [filterOpen])

    if (loading) return <Spinner />
    if (error) return <Err msg={error} />

    const allGroups = groupServers(list.servers)

    // Vendor cards always show all groups with full counts
    const vendorStats = allGroups.map(g => ({
        ...g,
        toolCount: g.servers.reduce((n, s) => n + (s.discovered_tool_count || 0), 0),
    }))

    function toggleFilter(dim, val) {
        setFilters(prev => {
            const next = new Set(prev[dim])
            next.has(val) ? next.delete(val) : next.add(val)
            return { ...prev, [dim]: next }
        })
    }

    // Sidebar: filter by active vendor, search, and checkboxes
    const q = search.toLowerCase()
    const filteredGroups = allGroups
        .filter(g => !activeVendor || g.key === activeVendor)
        .map(g => ({
            ...g,
            servers: g.servers.filter(s => {
                if (q && !s.name.toLowerCase().includes(q)) return false
                const { scope } = classifyClient(s.client)
                if (filters.scope.size > 0 && !filters.scope.has(scope)) return false
                if (filters.status.has("failed")) {
                    if (effectiveStatus(s) !== "failed") return false
                }
                if (filters.transport.size > 0 && !filters.transport.has(s.transport)) return false
                return true
            }),
        }))
        .filter(g => g.servers.length > 0)

    const activeFilterCount = filters.scope.size + filters.status.size + filters.transport.size

    const toggleVendor = (key) => {
        setActiveVendor(v => v === key ? null : key)
        setSearch("")
    }

    return (
        <div className="fade" style={{ padding: "32px 0" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
                <h1 style={{ fontFamily: "Calibri, Arial, sans-serif", fontWeight: 400, fontSize: 36, color: "var(--cream)", margin: 0 }}>
                    MCP Servers
                </h1>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <ScannedAt timestamp={list?.scanned_at} />
                    <RescanAllButton onRescan={onRescan} rescanState={rescanState} rescanSeconds={rescanSeconds} />
                </div>
            </div>

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

            <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 20, alignItems: "start" }}>

                {/* Sidebar */}
                <div style={{
                    display: "flex", flexDirection: "column",
                    position: "sticky", top: 56,
                    maxHeight: "calc(100vh - 72px)",
                }}>
                    {/* Search + Filter row — pinned, never scrolls */}
                    <div style={{ display: "flex", gap: 6, marginBottom: 10, flexShrink: 0 }}>
                        <input
                            type="text"
                            placeholder={activeVendor ? `Search in ${activeVendor}…` : "Search…"}
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                            style={{
                                flex: 1, minWidth: 0, padding: "7px 10px",
                                background: "var(--surface2)", border: "1px solid var(--border)",
                                borderRadius: "var(--radius)", color: "var(--cream)",
                                fontSize: 12, fontFamily: "Menlo, Consolas, monospace",
                                outline: "none", boxSizing: "border-box",
                            }}
                        />
                        <div ref={filterRef} style={{ position: "relative", flexShrink: 0 }}>
                            <button
                                onClick={() => setFilterOpen(o => !o)}
                                style={{
                                    height: "100%", padding: "0 10px",
                                    background: filterOpen || activeFilterCount > 0 ? "var(--surface3)" : "var(--surface2)",
                                    border: `1px solid ${filterOpen || activeFilterCount > 0 ? "var(--border3)" : "var(--border)"}`,
                                    borderRadius: "var(--radius)", color: activeFilterCount > 0 ? "var(--cream)" : "var(--text3)",
                                    fontSize: 11, fontFamily: "Menlo, Consolas, monospace",
                                    cursor: "pointer", display: "flex", alignItems: "center", gap: 5,
                                    transition: "all 0.12s", whiteSpace: "nowrap",
                                }}
                            >
                                <span>Filter</span>
                                {activeFilterCount > 0 && (
                                    <span style={{
                                        background: "var(--lime)", color: "#0a0d14",
                                        borderRadius: 9, fontSize: 9, fontWeight: 700,
                                        padding: "1px 5px", lineHeight: 1.4,
                                    }}>{activeFilterCount}</span>
                                )}
                                <span style={{ fontSize: 9, opacity: 0.6 }}>{filterOpen ? "▲" : "▼"}</span>
                            </button>

                            {filterOpen && (
                                <div style={{
                                    position: "absolute", top: "calc(100% + 6px)", right: 0,
                                    background: "var(--surface2)", border: "1px solid var(--border3)",
                                    borderRadius: "var(--radius-lg)", padding: "14px 16px",
                                    zIndex: 200, minWidth: 200,
                                    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                                    display: "flex", flexDirection: "column", gap: 14,
                                }}>
                                    <div>
                                        <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", marginBottom: 8 }}>Scope</div>
                                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                                            <FilterChip label="global"  checked={filters.scope.has("global")}  onChange={() => toggleFilter("scope", "global")} />
                                            <FilterChip label="project" checked={filters.scope.has("project")} onChange={() => toggleFilter("scope", "project")} />
                                        </div>
                                    </div>
                                    <div>
                                        <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", marginBottom: 8 }}>Status</div>
                                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                                            <FilterChip label="failed" checked={filters.status.has("failed")} onChange={() => toggleFilter("status", "failed")} />
                                        </div>
                                    </div>
                                    <div>
                                        <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", marginBottom: 8 }}>Transport</div>
                                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                                            <FilterChip label="stdio" checked={filters.transport.has("stdio")} onChange={() => toggleFilter("transport", "stdio")} />
                                            <FilterChip label="http"  checked={filters.transport.has("http")}  onChange={() => toggleFilter("transport", "http")} />
                                            <FilterChip label="sse"   checked={filters.transport.has("sse")}   onChange={() => toggleFilter("transport", "sse")} />
                                        </div>
                                    </div>
                                    {activeFilterCount > 0 && (
                                        <button
                                            onClick={() => setFilters({ scope: new Set(), status: new Set(), transport: new Set() })}
                                            style={{
                                                padding: "5px 0", background: "none", border: "none",
                                                borderTop: "1px solid var(--border)", color: "var(--text3)",
                                                fontSize: 10, fontFamily: "Menlo, Consolas, monospace",
                                                cursor: "pointer", textAlign: "left",
                                            }}
                                            onMouseEnter={e => e.target.style.color = "var(--red)"}
                                            onMouseLeave={e => e.target.style.color = "var(--text3)"}
                                        >
                                            clear all filters
                                        </button>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Server list — scrolls independently */}
                    <div style={{ overflowY: "auto", flex: 1 }}>
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
                                                    <ConnectionStatusBadge status={effectiveStatus(s)} />
                                                </div>
                                            </SidebarBtn>
                                        )
                                    })}
                                </div>
                            </div>
                        ))
                    }
                    </div>
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
                                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                                        <ConnectionStatusBadge status={effectiveStatus(detail)} />
                                        <RescanServerButton serverId={sel} onDone={() => { refetchDetail(); refetchList() }} />
                                        <CopyConfigButton detail={detail} />
                                    </div>
                                </div>
                                {detail.description && <p style={{ fontSize: 13, color: "var(--text2)", marginBottom: 12 }}>{detail.description}</p>}
                                {effectiveStatus(detail) === "failed" && (
                                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                                        <span style={{ fontSize: 10, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.06em", textTransform: "uppercase" }}>status</span>
                                        <span style={{ fontSize: 11, color: "var(--red)", fontFamily: "Menlo, Consolas, monospace" }}>
                                            {detail.probe_error || detail.raw_connection_status || detail.probe_status}
                                        </span>
                                    </div>
                                )}
                                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: detail.env && Object.keys(detail.env).length > 0 ? 0 : undefined }}>
                                    {[
                                        ["Transport", detail.transport],
                                        ["Source", classifyClient(detail.client).label],
                                        ["Package", detail.package],
                                        ["Command", detail.command ? `${detail.command} ${(detail.args || []).join(" ")}` : "—"],
                                    ].map(([k, v]) => (
                                        <div key={k} style={{ padding: "11px 14px", background: "var(--surface2)", borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
                                            <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text3)", marginBottom: 5, fontFamily: "Menlo, Consolas, monospace" }}>{k}</div>
                                            {k === "Source"
                                                ? <div>
                                                    <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 4 }}>
                                                        <span style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 11, color: "var(--cream)" }}>{v || "—"}</span>
                                                        <ScopeTag scope={classifyClient(detail.client).scope} />
                                                    </div>
                                                    {detail.source_path && (
                                                        <div style={{ fontSize: 9, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", wordBreak: "break-all", lineHeight: 1.5 }}>
                                                            {detail.source_path}
                                                        </div>
                                                    )}
                                                    {detail.project_path && (
                                                        <div style={{ fontSize: 9, color: "var(--lime-dim)", fontFamily: "Menlo, Consolas, monospace", wordBreak: "break-all", lineHeight: 1.5, marginTop: 2 }}>
                                                            {detail.project_path}
                                                        </div>
                                                    )}
                                                  </div>
                                                : <div style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 11, color: "var(--cream)", wordBreak: "break-all" }}>{v || "—"}</div>
                                            }
                                        </div>
                                    ))}
                                </div>
                                <EnvTable env={detail.env} />
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
