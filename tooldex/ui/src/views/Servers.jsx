import { useState, useEffect, useRef } from "react"
import { api } from "../api.js"
import { useFetch } from "../hooks/useFetch.js"
import { Card, CardHead, Empty, Spinner, Err } from "../components/ui.jsx"
import { SecurityWarningIcon, SecurityCleanIcon } from "../assets/icons.jsx"
import { DownloadReport } from "../components/DownloadReport.jsx"
import { DownloadServerReport } from "../components/servers/DownloadServerReport.jsx"
import { CopyConfigButton } from "../components/servers/CopyConfigButton.jsx"
import { RescanServerButton } from "../components/servers/RescanServerButton.jsx"
import { LlmScanServerButton } from "../components/servers/LlmScanServerButton.jsx"
import { ServerSidebarList } from "../components/servers/ServerSidebarList.jsx"
import { ToolsPanel } from "../components/servers/ToolsPanel.jsx"
import {
    classifyClient, groupServers, effectiveStatus, ConnectionStatusBadge,
    ScopeTag, SecurityRiskBadge, securityRiskColor, formatRelativeTime,
} from "../components/servers/serverHelpers.jsx"

// ---------------------------------------------------------------------------
// Rescan all button (header level)
// ---------------------------------------------------------------------------

function RescanAllButton({ onRescan, rescanState, rescanSeconds }) {
    const label = rescanState === "scanning" ? `scanning… ${rescanSeconds}s` : rescanState === "done" ? "done ✓" : "rescan all"
    const color = rescanState === "scanning" ? "var(--yellow-muted)" : rescanState === "done" ? "var(--lime)" : "var(--text3)"
    const borderColor = rescanState === "scanning" ? "var(--yellow-muted)" : "var(--border2)"

    return (
        <button onClick={() => onRescan()} style={{
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

// Attribution line — security scanning is powered by Cisco's mcp-scanner
function ScanPoweredByBanner() {
    return (
        <div style={{
            marginBottom: 16, fontSize: 11, color: "var(--text3)",
            fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.02em",
        }}>
            Security scanning powered by opensource{" "}
            <a
                href="https://github.com/cisco-ai-defense/mcp-scanner"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "#7ec8ff", textDecoration: "none" }}
            >
                Cisco AI Defense-MCP Scanner
            </a>{" "}
            library
        </div>
    )
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
        if (!sel || !ids.has(sel)) {
            // Default to the first server of the first agent group, matching
            // the order actually shown in the sidebar — not raw API order.
            const firstGroup = groupServers(list.servers)[0]
            setSel(firstGroup?.servers[0]?.id ?? list.servers[0].id)
        }
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

            <ScanPoweredByBanner />

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
                                    <div style={{ display: "flex", alignItems: "flex-start", gap: 8, flexShrink: 0 }}>
                                        <ConnectionStatusBadge status={effectiveStatus(detail)} />
                                        <RescanServerButton serverId={sel} onDone={() => { refetchDetail(); refetchList() }} />
                                        <CopyConfigButton detail={detail} />
                                        {detail.discovered_tools?.length > 0 && (
                                            <LlmScanServerButton
                                                serverId={sel}
                                                onDone={() => { refetchDetail(); refetchList() }}
                                                lastScannedAt={detail.security_llm_scanned_at}
                                                newFindings={detail.security_llm_new_findings}
                                                totalFindings={(detail.security_findings || []).filter(f => f.analyzer === "LLM").length}
                                                cacheHits={detail.security_llm_cache_hits}
                                                lastScanTotal={detail.security_llm_last_scan_total}
                                                hasLlmCache={detail.has_llm_cache}
                                            />
                                        )}
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
                                                        <ScopeTag scope={classifyClient(detail.client).scope} label={classifyClient(detail.client).scopeLabel} />
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

                        <div style={{ display: "flex", justifyContent: "flex-end" }}>
                            <DownloadServerReport server={detail} scannedAt={list?.scanned_at} />
                        </div>

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
