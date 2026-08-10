import { SecurityWarningIcon, SecurityCleanIcon } from "../../assets/icons.jsx"

// ---------------------------------------------------------------------------
// Last-scanned timestamp
// ---------------------------------------------------------------------------

export function formatRelativeTime(isoStr) {
    if (!isoStr) return null
    const diff = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000)
    if (diff < 10) return "just now"
    if (diff < 60) return `${diff}s ago`
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
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
    vscode_project:         { group: "VSCode", label: "VSCode", scope: "project", scopeLabel: "workspace" },
    vscode_project_dotfile: { group: "VSCode", label: "VSCode", scope: "project", scopeLabel: "workspace" },
    vscode_user:            { group: "VSCode", label: "VSCode", scope: "global",  scopeLabel: "user" },
    copilot_cli_user:     { group: "Copilot",      label: "Copilot",      scope: "global" },
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

const GROUP_ORDER = ["Claude", "Cursor", "Codex", "VSCode", "Copilot", "MCP JSON", "Gemini", "Docker MCP", "Custom"]

export function classifyClient(client) {
    if (!client) return { group: "Unknown", label: "—", scope: null }
    if (client.startsWith("docker_mcp:")) {
        const profile = client.split(":").slice(1).join(":")
        return { group: `Docker MCP · ${profile}`, label: `Docker MCP · ${profile}`, scope: null }
    }
    return CLIENT_META[client] || { group: client, label: client, scope: null }
}

export function groupServers(servers) {
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
// Security risk badge
// ---------------------------------------------------------------------------

const _RISK_COLOR = {
    CRITICAL: "var(--red)",
    HIGH:     "var(--red)",
    MEDIUM:   "var(--yellow-muted)",
    LOW:      "#5eead4",
    INFO:     "var(--text3)",
}

export function securityRiskColor(risk) {
    return _RISK_COLOR[(risk || "").toUpperCase()] || "var(--text3)"
}

// Sidebar icon: warning triangle (colored by severity) or green tick (clean)
export function SecurityStatusIcon({ risk, scanned, size = 13 }) {
    if (risk) {
        return <SecurityWarningIcon size={size} color={securityRiskColor(risk)} />
    }
    if (scanned) {
        return <SecurityCleanIcon size={size} color="var(--lime)" />
    }
    return null
}

export function SecurityRiskBadge({ risk }) {
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
export function effectiveStatus(s) {
    if (s.probe_status != null) return s.probe_status === "found" ? null : "failed"
    return s.connection_status || null
}

export function ConnectionStatusBadge({ status }) {
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

export function ScopeTag({ scope, label }) {
    if (!scope) return null
    const isProject = scope === "project"
    return (
        <span style={{
            padding: "1px 5px", borderRadius: 3,
            border: `1px solid ${isProject ? "var(--lime-dim)" : "var(--border)"}`,
            fontSize: 9, letterSpacing: "0.06em", textTransform: "uppercase",
            color: isProject ? "var(--lime-dim)" : "var(--text3)",
            fontFamily: "Menlo, Consolas, monospace", flexShrink: 0,
        }}>{label || scope}</span>
    )
}
