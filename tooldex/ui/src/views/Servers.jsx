import { useState, useEffect, useRef, useMemo } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { api } from "../api.js"
import { useFetch } from "../hooks/useFetch.js"
import {
    Card, CardHead, Empty, Spinner, Err, SidebarBtn, ProvenanceDot,
} from "../components/ui.jsx"
import { SecurityWarningIcon, SecurityCleanIcon } from "../assets/icons.jsx"
import { DownloadReport } from "../components/DownloadReport.jsx"

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

// ---------------------------------------------------------------------------
// Security risk badge
// ---------------------------------------------------------------------------

const _RISK_COLOR = {
    CRITICAL: "var(--red)",
    HIGH:     "var(--red)",
    MEDIUM:   "var(--yellow-muted)",
    LOW:      "#5eead4",
    INFO:     "var(--text3)",
}

function securityRiskColor(risk) {
    return _RISK_COLOR[(risk || "").toUpperCase()] || "var(--text3)"
}

// Sidebar icon: warning triangle (colored by severity) or green tick (clean)
function SecurityStatusIcon({ risk, scanned, size = 13 }) {
    if (risk) {
        return <SecurityWarningIcon size={size} color={securityRiskColor(risk)} />
    }
    if (scanned) {
        return <SecurityCleanIcon size={size} color="var(--lime)" />
    }
    return null
}

function SecurityRiskBadge({ risk }) {
    if (!risk) return null
    const color = securityRiskColor(risk)
    return (
        <span style={{
            padding: "1px 6px", borderRadius: 3,
            border: `1px solid ${color}`,
            fontSize: 9, letterSpacing: "0.06em", textTransform: "uppercase",
            color, fontFamily: "Menlo, Consolas, monospace", flexShrink: 0,
        }}>{risk}</span>
    )
}

// ---------------------------------------------------------------------------
// Tools panel — integrated tool list with inline security findings
// ---------------------------------------------------------------------------

const _SEV_RANK = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4 }
const _SEV_FILTER_LEVELS = ["HIGH", "MEDIUM", "LOW"]

// ---------------------------------------------------------------------------
// Per-tool findings panel — own sort + filter state
// ---------------------------------------------------------------------------

function ToolFindingsPanel({ findings }) {
    const [sortDir, setSortDir] = useState(null)
    const [sevFilter, setSevFilter] = useState(new Set())
    const [sortOpen, setSortOpen] = useState(false)
    const [sevOpen, setSevOpen] = useState(false)
    const sortRef = useRef(null)
    const sevRef = useRef(null)

    useEffect(() => {
        function handleClick(e) {
            if (sortRef.current && !sortRef.current.contains(e.target)) setSortOpen(false)
            if (sevRef.current && !sevRef.current.contains(e.target)) setSevOpen(false)
        }
        document.addEventListener("mousedown", handleClick)
        return () => document.removeEventListener("mousedown", handleClick)
    }, [])

    const displayed = (() => {
        let list = findings
        if (sevFilter.size > 0) list = list.filter(f => sevFilter.has(f.severity?.toUpperCase()))
        if (sortDir === "desc") list = [...list].sort((a, b) => (_SEV_RANK[a.severity?.toUpperCase()] ?? 99) - (_SEV_RANK[b.severity?.toUpperCase()] ?? 99))
        if (sortDir === "asc")  list = [...list].sort((a, b) => (_SEV_RANK[b.severity?.toUpperCase()] ?? 99) - (_SEV_RANK[a.severity?.toUpperCase()] ?? 99))
        return list
    })()

    const miniBtn = (active) => ({
        padding: "2px 7px", borderRadius: 3, cursor: "pointer",
        fontSize: 9, fontFamily: "Menlo, Consolas, monospace",
        letterSpacing: "0.05em", textTransform: "uppercase",
        border: `1px solid ${active ? "var(--border3)" : "var(--border)"}`,
        background: active ? "var(--surface3)" : "var(--surface2)",
        color: active ? "var(--cream)" : "var(--text3)",
        display: "flex", alignItems: "center", gap: 4,
        transition: "all 0.1s",
    })

    const dropdownBase = {
        position: "absolute", top: "calc(100% + 4px)", left: 0,
        background: "var(--surface2)", border: "1px solid var(--border3)",
        borderRadius: "var(--radius)", padding: "6px 0",
        zIndex: 300, minWidth: 130,
        boxShadow: "0 6px 20px rgba(0,0,0,0.4)",
    }
    const dropdownItem = {
        display: "flex", alignItems: "center", gap: 7,
        padding: "5px 12px", cursor: "pointer",
        fontSize: 10, fontFamily: "Menlo, Consolas, monospace",
        color: "var(--text2)", userSelect: "none",
    }

    return (
        <div style={{ marginTop: 6 }}>
            {/* controls row */}
            <div style={{ display: "flex", gap: 5, marginBottom: 7 }}>
                {/* Sort */}
                <div ref={sortRef} style={{ position: "relative" }}>
                    <button onClick={() => { setSortOpen(o => !o); setSevOpen(false) }} style={miniBtn(!!sortDir)}>
                        Sort
                        {sortDir && <span style={{ background: "var(--lime)", color: "#0a0d14", borderRadius: 9, fontSize: 8, fontWeight: 700, padding: "0 4px", lineHeight: 1.5 }}>1</span>}
                        <span style={{ fontSize: 7, opacity: 0.5 }}>{sortOpen ? "▲" : "▼"}</span>
                    </button>
                    {sortOpen && (
                        <div style={dropdownBase}>
                            {[
                                { value: null,   label: "Default" },
                                { value: "desc", label: "High → Low" },
                                { value: "asc",  label: "Low → High" },
                            ].map(opt => (
                                <div key={String(opt.value)} onClick={() => { setSortDir(opt.value); setSortOpen(false) }}
                                    style={{ ...dropdownItem, color: sortDir === opt.value ? "var(--cream)" : "var(--text2)", background: sortDir === opt.value ? "var(--surface3)" : "transparent" }}>
                                    <span style={{ width: 7, height: 7, borderRadius: "50%", flexShrink: 0, background: sortDir === opt.value ? "var(--lime)" : "transparent", border: `1px solid ${sortDir === opt.value ? "var(--lime)" : "var(--border3)"}` }} />
                                    {opt.label}
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Filter */}
                <div ref={sevRef} style={{ position: "relative" }}>
                    <button onClick={() => { setSevOpen(o => !o); setSortOpen(false) }} style={miniBtn(sevFilter.size > 0)}>
                        Filter
                        {sevFilter.size > 0 && <span style={{ background: "var(--lime)", color: "#0a0d14", borderRadius: 9, fontSize: 8, fontWeight: 700, padding: "0 4px", lineHeight: 1.5 }}>{sevFilter.size}</span>}
                        <span style={{ fontSize: 7, opacity: 0.5 }}>{sevOpen ? "▲" : "▼"}</span>
                    </button>
                    {sevOpen && (
                        <div style={dropdownBase}>
                            {_SEV_FILTER_LEVELS.map(sev => (
                                <label key={sev} style={{ ...dropdownItem, color: sevFilter.has(sev) ? securityRiskColor(sev) : "var(--text2)" }}>
                                    <input type="checkbox" checked={sevFilter.has(sev)}
                                        onChange={() => setSevFilter(prev => { const n = new Set(prev); n.has(sev) ? n.delete(sev) : n.add(sev); return n })}
                                        style={{ accentColor: securityRiskColor(sev), width: 11, height: 11, cursor: "pointer", flexShrink: 0 }} />
                                    {sev}
                                </label>
                            ))}
                            {sevFilter.size > 0 && (
                                <div onClick={() => setSevFilter(new Set())}
                                    style={{ ...dropdownItem, color: "var(--text3)", fontSize: 9, borderTop: "1px solid var(--border)", marginTop: 3, paddingTop: 7 }}>
                                    clear
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* findings list */}
            {displayed.length === 0
                ? <div style={{ fontSize: 10, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", padding: "4px 0" }}>no matching issues</div>
                : displayed.map((f, fi) => (
                    <div key={fi} style={{
                        marginTop: fi > 0 ? 6 : 0,
                        padding: "7px 10px",
                        background: "var(--surface2)",
                        borderRadius: "var(--radius)",
                        borderLeft: `2px solid ${securityRiskColor(f.severity)}`,
                    }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 4 }}>
                            <span style={{ fontSize: 9, color: securityRiskColor(f.severity), fontFamily: "Menlo, Consolas, monospace", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600 }}>{f.severity}</span>
                            <span style={{ fontSize: 9, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", textTransform: "uppercase", letterSpacing: "0.04em" }}>{f.analyzer}</span>
                            {f.threat_category && <>
                                <span style={{ fontSize: 9, color: "var(--text3)" }}>·</span>
                                <span style={{ fontSize: 9, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", textTransform: "uppercase", letterSpacing: "0.04em" }}>{f.threat_category}</span>
                            </>}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--text2)", lineHeight: 1.5 }}>{f.summary}</div>
                    </div>
                ))
            }
        </div>
    )
}
const _SORT_OPTIONS = [
    { value: null,      label: "Default",   group: null },
    { value: "desc",    label: "High → Low", group: "severity" },
    { value: "asc",     label: "Low → High", group: "severity" },
    { value: "name-az", label: "A → Z",      group: "name" },
    { value: "name-za", label: "Z → A",      group: "name" },
]

function ToolsPanel({ tools, findings }) {
    const [search, setSearch] = useState("")
    const [sevFilter, setSevFilter] = useState(new Set())
    const [expanded, setExpanded] = useState(new Set())
    const [expandedDescs, setExpandedDescs] = useState(new Set())
    const [sortDir, setSortDir] = useState(null)
    const [sortOpen, setSortOpen] = useState(false)
    const [sevOpen, setSevOpen] = useState(false)
    const sortRef = useRef(null)
    const sevRef = useRef(null)

    useEffect(() => {
        function handleClick(e) {
            if (sortRef.current && !sortRef.current.contains(e.target)) setSortOpen(false)
            if (sevRef.current && !sevRef.current.contains(e.target)) setSevOpen(false)
        }
        document.addEventListener("mousedown", handleClick)
        return () => document.removeEventListener("mousedown", handleClick)
    }, [])

    const findingsByTool = {}
    for (const f of findings || []) {
        if (!findingsByTool[f.tool_name]) findingsByTool[f.tool_name] = []
        findingsByTool[f.tool_name].push(f)
    }

    const q = search.toLowerCase()
    const filtered = (tools || []).filter(tool => {
        const tf = findingsByTool[tool.name] || []
        if (sevFilter.size > 0) {
            const toolSevs = new Set(tf.map(f => f.severity?.toUpperCase()))
            if (![...sevFilter].some(s => toolSevs.has(s))) return false
        }
        if (q) {
            const inName = tool.name.toLowerCase().includes(q)
            const inDesc = (tool.description || "").toLowerCase().includes(q)
            const inSec = tf.some(f =>
                (f.summary || "").toLowerCase().includes(q) ||
                (f.threat_category || "").toLowerCase().includes(q)
            )
            if (!inName && !inDesc && !inSec) return false
        }
        return true
    })

    function worstRank(tool) {
        const tf = findingsByTool[tool.name] || []
        if (!tf.length) return 99
        return Math.min(...tf.map(f => _SEV_RANK[f.severity?.toUpperCase()] ?? 99))
    }

    const displayed = sortDir
        ? [...filtered].sort((a, b) => {
            if (sortDir === "desc") return worstRank(a) - worstRank(b)
            if (sortDir === "asc")  return worstRank(b) - worstRank(a)
            if (sortDir === "name-az") return a.name.localeCompare(b.name)
            if (sortDir === "name-za") return b.name.localeCompare(a.name)
            return 0
          })
        : filtered

    function toggleSev(sev) {
        setSevFilter(prev => {
            const next = new Set(prev)
            next.has(sev) ? next.delete(sev) : next.add(sev)
            return next
        })
    }

    function toggleExpand(name) {
        setExpanded(prev => {
            const next = new Set(prev)
            next.has(name) ? next.delete(name) : next.add(name)
            return next
        })
    }

    const hasSecurity = Object.keys(findingsByTool).length > 0

    const dropdownBase = {
        position: "absolute", top: "calc(100% + 5px)", right: 0,
        background: "var(--surface2)", border: "1px solid var(--border3)",
        borderRadius: "var(--radius-lg)", padding: "8px 0",
        zIndex: 200, minWidth: 140,
        boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
    }
    const dropdownItemBase = {
        display: "flex", alignItems: "center", gap: 8,
        padding: "6px 14px", cursor: "pointer",
        fontSize: 11, fontFamily: "Menlo, Consolas, monospace",
        color: "var(--text2)", userSelect: "none",
    }

    return (
        <>
            <div style={{ padding: "10px 14px 8px", display: "flex", gap: 6, alignItems: "center", borderBottom: "1px solid var(--border)" }}>
                <input
                    type="text"
                    placeholder="Search tools…"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    style={{
                        flex: 1, minWidth: 120, padding: "5px 9px",
                        background: "var(--surface2)", border: "1px solid var(--border)",
                        borderRadius: "var(--radius)", color: "var(--cream)",
                        fontSize: 11, fontFamily: "Menlo, Consolas, monospace",
                        outline: "none",
                    }}
                />

                {/* Severity filter dropdown */}
                {hasSecurity && (
                    <div ref={sevRef} style={{ position: "relative", flexShrink: 0 }}>
                        <button onClick={() => { setSevOpen(o => !o); setSortOpen(false) }} style={{
                            padding: "5px 10px", borderRadius: "var(--radius)", cursor: "pointer",
                            fontSize: 10, fontFamily: "Menlo, Consolas, monospace",
                            border: `1px solid ${sevFilter.size > 0 ? "var(--border3)" : "var(--border)"}`,
                            background: sevFilter.size > 0 ? "var(--surface3)" : "var(--surface2)",
                            color: sevFilter.size > 0 ? "var(--cream)" : "var(--text3)",
                            display: "flex", alignItems: "center", gap: 5,
                            transition: "all 0.1s",
                        }}>
                            <span>Filter</span>
                            {sevFilter.size > 0 && (
                                <span style={{
                                    background: "var(--lime)", color: "#0a0d14",
                                    borderRadius: 9, fontSize: 9, fontWeight: 700,
                                    padding: "1px 5px", lineHeight: 1.4,
                                }}>{sevFilter.size}</span>
                            )}
                            <span style={{ fontSize: 8, opacity: 0.5 }}>{sevOpen ? "▲" : "▼"}</span>
                        </button>
                        {sevOpen && (
                            <div style={dropdownBase}>
                                {_SEV_FILTER_LEVELS.map(sev => (
                                    <label key={sev} style={{ ...dropdownItemBase, color: sevFilter.has(sev) ? securityRiskColor(sev) : "var(--text2)" }}>
                                        <input
                                            type="checkbox"
                                            checked={sevFilter.has(sev)}
                                            onChange={() => toggleSev(sev)}
                                            style={{ accentColor: securityRiskColor(sev), width: 12, height: 12, cursor: "pointer", flexShrink: 0 }}
                                        />
                                        {sev}
                                    </label>
                                ))}
                                {sevFilter.size > 0 && (
                                    <div
                                        onClick={() => setSevFilter(new Set())}
                                        style={{
                                            ...dropdownItemBase,
                                            color: "var(--text3)", fontSize: 10,
                                            borderTop: "1px solid var(--border)", marginTop: 4, paddingTop: 8,
                                        }}
                                    >
                                        clear
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* Sort dropdown — always visible */}
                <div ref={sortRef} style={{ position: "relative", flexShrink: 0 }}>
                    <button onClick={() => { setSortOpen(o => !o); setSevOpen(false) }} style={{
                        padding: "5px 10px", borderRadius: "var(--radius)", cursor: "pointer",
                        fontSize: 10, fontFamily: "Menlo, Consolas, monospace",
                        border: `1px solid ${sortDir ? "var(--border3)" : "var(--border)"}`,
                        background: sortDir ? "var(--surface3)" : "var(--surface2)",
                        color: sortDir ? "var(--cream)" : "var(--text3)",
                        display: "flex", alignItems: "center", gap: 5,
                        transition: "all 0.1s",
                    }}>
                        <span>Sort</span>
                        {sortDir && (
                            <span style={{
                                background: "var(--lime)", color: "#0a0d14",
                                borderRadius: 9, fontSize: 9, fontWeight: 700,
                                padding: "1px 5px", lineHeight: 1.4,
                            }}>1</span>
                        )}
                        <span style={{ fontSize: 8, opacity: 0.5 }}>{sortOpen ? "▲" : "▼"}</span>
                    </button>
                    {sortOpen && (
                        <div style={{ ...dropdownBase, minWidth: 160 }}>
                            {hasSecurity && (
                                <div style={{ padding: "4px 14px 4px", fontSize: 9, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace" }}>
                                    Severity
                                </div>
                            )}
                            {_SORT_OPTIONS.filter(o => o.group === "severity" || o.value === null).map(opt => {
                                if (opt.group === "severity" && !hasSecurity) return null
                                return (
                                    <div
                                        key={String(opt.value)}
                                        onClick={() => { setSortDir(opt.value); setSortOpen(false) }}
                                        style={{
                                            ...dropdownItemBase,
                                            color: sortDir === opt.value ? "var(--cream)" : "var(--text2)",
                                            background: sortDir === opt.value ? "var(--surface3)" : "transparent",
                                        }}
                                    >
                                        <span style={{
                                            width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                                            background: sortDir === opt.value ? "var(--lime)" : "transparent",
                                            border: `1px solid ${sortDir === opt.value ? "var(--lime)" : "var(--border3)"}`,
                                        }} />
                                        {opt.label}
                                    </div>
                                )
                            })}
                            <div style={{ padding: "6px 14px 4px", fontSize: 9, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", borderTop: hasSecurity ? "1px solid var(--border)" : "none", marginTop: hasSecurity ? 4 : 0 }}>
                                Name
                            </div>
                            {_SORT_OPTIONS.filter(o => o.group === "name").map(opt => (
                                <div
                                    key={String(opt.value)}
                                    onClick={() => { setSortDir(opt.value); setSortOpen(false) }}
                                    style={{
                                        ...dropdownItemBase,
                                        color: sortDir === opt.value ? "var(--cream)" : "var(--text2)",
                                        background: sortDir === opt.value ? "var(--surface3)" : "transparent",
                                    }}
                                >
                                    <span style={{
                                        width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                                        background: sortDir === opt.value ? "var(--lime)" : "transparent",
                                        border: `1px solid ${sortDir === opt.value ? "var(--lime)" : "var(--border3)"}`,
                                    }} />
                                    {opt.label}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
            {displayed.length === 0
                ? <div style={{ padding: "16px 18px", fontSize: 11, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace" }}>no matching tools</div>
                : (
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                        <tbody>
                            {displayed.map((tool, ti) => {
                                const tf = findingsByTool[tool.name] || []
                                const worstSev = tf.length
                                    ? tf.reduce((a, b) =>
                                        (_SEV_RANK[a.severity?.toUpperCase()] ?? 99) <= (_SEV_RANK[b.severity?.toUpperCase()] ?? 99) ? a : b
                                      ).severity
                                    : null
                                const isExpanded = expanded.has(tool.name)
                                return (
                                    <tr key={ti} style={{ borderBottom: ti < displayed.length - 1 ? "1px solid var(--border)" : "none" }}>
                                        <td style={{ padding: "10px 14px", width: 200, verticalAlign: "top" }}>
                                            <div style={{ fontFamily: "Menlo, Consolas, monospace", fontSize: 12, color: "var(--cream)", fontWeight: 500, marginBottom: worstSev ? 5 : 0 }}>
                                                {tool.name}
                                            </div>
                                            {worstSev && <SecurityRiskBadge risk={worstSev} />}
                                        </td>
                                        <td style={{ padding: "10px 14px", verticalAlign: "top" }}>
                                            {(() => {
                                                const desc = tool.description || ""
                                                const words = desc.split(/\s+/).filter(Boolean)
                                                const isLong = words.length > 50
                                                const isDescExpanded = expandedDescs.has(tool.name)
                                                const displayText = isLong && !isDescExpanded
                                                    ? words.slice(0, 50).join(" ") + "…"
                                                    : desc || "—"
                                                return (
                                                    <div style={{ fontSize: 12, color: "var(--text2)", marginBottom: tf.length ? 8 : 0 }}>
                                                        {displayText}
                                                        {isLong && !isDescExpanded && (
                                                            <button
                                                                onClick={() => setExpandedDescs(prev => new Set(prev).add(tool.name))}
                                                                style={{
                                                                    background: "none", border: "none", padding: "0 0 0 5px",
                                                                    cursor: "pointer", fontSize: 11,
                                                                    color: "var(--text3)", display: "inline",
                                                                }}
                                                            >more →</button>
                                                        )}
                                                        {isLong && isDescExpanded && (
                                                            <button
                                                                onClick={() => setExpandedDescs(prev => { const n = new Set(prev); n.delete(tool.name); return n })}
                                                                style={{
                                                                    background: "none", border: "none", padding: "0 0 0 5px",
                                                                    cursor: "pointer", fontSize: 11,
                                                                    color: "var(--text3)", display: "inline",
                                                                }}
                                                            >less ←</button>
                                                        )}
                                                    </div>
                                                )
                                            })()}
                                            {tf.length > 0 && (
                                                <>
                                                    <button
                                                        onClick={() => toggleExpand(tool.name)}
                                                        style={{
                                                            display: "flex", alignItems: "center", gap: 6,
                                                            background: "none", border: "none", padding: 0,
                                                            cursor: "pointer", marginBottom: isExpanded ? 8 : 0,
                                                        }}
                                                    >
                                                        <SecurityWarningIcon size={12} color={securityRiskColor(worstSev)} />
                                                        <span style={{
                                                            fontSize: 10, color: securityRiskColor(worstSev),
                                                            fontFamily: "Menlo, Consolas, monospace",
                                                        }}>
                                                            {tf.length} {tf.length === 1 ? "issue" : "issues"}
                                                        </span>
                                                        <span style={{ fontSize: 9, color: "var(--text3)", marginLeft: 1 }}>
                                                            {isExpanded ? "▲" : "▼"}
                                                        </span>
                                                    </button>
                                                    {isExpanded && <ToolFindingsPanel findings={tf} />}
                                                </>
                                            )}
                                        </td>
                                    </tr>
                                )
                            })}
                        </tbody>
                    </table>
                )
            }
        </>
    )
}

// ---------------------------------------------------------------------------
// Virtualized sidebar server list
// ---------------------------------------------------------------------------

function ServerSidebarList({ filteredGroups, sel, setSel, serverScanState }) {
    const flatItems = useMemo(() => {
        const items = []
        for (const group of filteredGroups) {
            items.push({ type: "header", group })
            for (const server of group.servers) {
                items.push({ type: "server", server, group })
            }
        }
        return items
    }, [filteredGroups])

    const listRef = useRef(null)
    const virtualizer = useVirtualizer({
        count: flatItems.length,
        getScrollElement: () => listRef.current,
        estimateSize: (i) => flatItems[i]?.type === "header" ? 28 : 58,
        overscan: 8,
    })

    if (flatItems.length === 0) {
        return (
            <div style={{ overflowY: "auto", flex: 1 }}>
                <div style={{ padding: "18px 10px", fontSize: 11, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace" }}>no results</div>
            </div>
        )
    }

    return (
        <div ref={listRef} style={{ overflowY: "auto", flex: 1 }}>
            <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
                {virtualizer.getVirtualItems().map(vItem => {
                    const item = flatItems[vItem.index]
                    if (!item) return null

                    if (item.type === "header") {
                        return (
                            <div key={vItem.key} style={{
                                position: "absolute", top: 0, left: 0, width: "100%",
                                transform: `translateY(${vItem.start}px)`,
                                padding: "6px 10px 4px",
                                fontSize: 9, fontWeight: 700,
                                letterSpacing: "0.12em", textTransform: "uppercase",
                                color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace",
                                display: "flex", alignItems: "center", justifyContent: "space-between",
                            }}>
                                <span>{item.group.key}</span>
                                <span style={{ opacity: 0.5 }}>{item.group.servers.length}</span>
                            </div>
                        )
                    }

                    const s = item.server
                    const { scope } = classifyClient(s.client)
                    const scanSt    = serverScanState.get(s.id)
                    const isScanning = scanSt === "scanning"
                    const scanDone   = scanSt === "done"
                    const scanError  = scanSt === "error"

                    return (
                        <div key={vItem.key} style={{
                            position: "absolute", top: 0, left: 0, width: "100%",
                            transform: `translateY(${vItem.start}px)`,
                            paddingBottom: 2,
                        }}>
                            <SidebarBtn active={sel === s.id} onClick={() => setSel(s.id)}>
                                <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                                    <ProvenanceDot server={s} />
                                    <div style={{ fontWeight: 500, fontSize: 13, color: sel === s.id ? "var(--cream)" : "var(--text2)" }}>{s.name}</div>
                                    {isScanning && (
                                        <span style={{ fontSize: 9, color: "var(--yellow-muted)", fontFamily: "Menlo, Consolas, monospace", animation: "pulse 1.2s ease-in-out infinite" }}>●</span>
                                    )}
                                    {scanDone && (
                                        <span style={{ fontSize: 9, color: "var(--lime)", fontFamily: "Menlo, Consolas, monospace" }}>✓</span>
                                    )}
                                    {scanError && (
                                        <span style={{ fontSize: 9, color: "var(--red)", fontFamily: "Menlo, Consolas, monospace" }}>✗</span>
                                    )}
                                </div>
                                <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", marginTop: 2 }}>
                                    <span>{s.agent_count}a · {s.transport}</span>
                                    <ScopeTag scope={scope} />
                                    <ConnectionStatusBadge status={effectiveStatus(s)} />
                                    <SecurityStatusIcon risk={s.security_risk} scanned={s.security_scanned} />
                                </div>
                            </SidebarBtn>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

// ---------------------------------------------------------------------------

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

export function Servers({ initialSel, scanKey = 0, onRescan, rescanState = "idle", rescanSeconds = 0, serverScanState = new Map() }) {
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
                if (filters.status.has("flagged")) {
                    if (!s.security_risk) return false
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
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
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

            <DownloadReport servers={list?.servers} scannedAt={list?.scanned_at} />

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
                                            <FilterChip label="failed"  checked={filters.status.has("failed")}  onChange={() => toggleFilter("status", "failed")} />
                                            <FilterChip label="flagged" checked={filters.status.has("flagged")} onChange={() => toggleFilter("status", "flagged")} />
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

                    {/* Server list — virtualized for 1000+ server performance */}
                    <ServerSidebarList
                        filteredGroups={filteredGroups}
                        sel={sel}
                        setSel={setSel}
                        serverScanState={serverScanState}
                    />
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
                            <CardHead right={
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                    {detail.security_risk
                                        ? <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                                            <SecurityWarningIcon size={13} color={securityRiskColor(detail.security_risk)} />
                                            <SecurityRiskBadge risk={detail.security_risk} />
                                          </div>
                                        : detail.security_scanned
                                            ? <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                                                <SecurityCleanIcon size={13} color="var(--lime)" />
                                                <span style={{ fontSize: 9, color: "var(--lime)", fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.06em", textTransform: "uppercase" }}>clean</span>
                                              </div>
                                            : <span style={{ fontSize: 9, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.04em" }}>no scan</span>
                                    }
                                </div>
                            }>
                                Tools
                                <span style={{
                                    fontFamily: "Menlo, Consolas, monospace", fontSize: 11,
                                    color: "var(--text3)", fontWeight: 400, letterSpacing: "0.04em",
                                    marginLeft: 7,
                                }}>{detail.discovered_tools?.length || 0}</span>
                            </CardHead>
                            {!detail.discovered_tools?.length
                                ? <Empty msg="no tools discovered" />
                                : <ToolsPanel tools={detail.discovered_tools} findings={detail.security_findings} />
                            }
                        </Card>

                    </div>
                )}
            </div>
        </div>
    )
}
