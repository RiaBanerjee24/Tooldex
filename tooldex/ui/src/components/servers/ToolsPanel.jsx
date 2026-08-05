import { useState, useEffect, useRef } from "react"
import { SecurityWarningIcon } from "../../assets/icons.jsx"
import { securityRiskColor, SecurityRiskBadge } from "./serverHelpers.jsx"

const _SEV_RANK = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4 }
const _SEV_FILTER_LEVELS = ["HIGH", "MEDIUM", "LOW"]

// ---------------------------------------------------------------------------
// Per-tool findings panel — own sort + filter state
// ---------------------------------------------------------------------------

function ToolFindingsPanel({ findings }) {
    const [sortDir, setSortDir] = useState(null)
    const [sevFilter, setSevFilter] = useState(new Set())
    const [tagFilter, setTagFilter] = useState(new Set())
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
        if (tagFilter.size > 0) list = list.filter(f => {
            const label = (f.threat_category || f.analyzer || "").toUpperCase()
            return tagFilter.has(label)
        })
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

    // Collect unique issue tags — prefer threat_category, fall back to analyzer.
    // Color each tag by the worst severity that carries that label.
    const tags = (() => {
        const map = {}
        for (const f of findings) {
            const label = (f.threat_category || f.analyzer || "").toUpperCase()
            if (!label) continue
            const rank = _SEV_RANK[f.severity?.toUpperCase()] ?? 99
            if (!(label in map) || rank < map[label].rank) {
                map[label] = { label, rank, color: securityRiskColor(f.severity) }
            }
        }
        return Object.values(map).sort((a, b) => a.rank - b.rank)
    })()

    return (
        <div style={{ marginTop: 6 }}>
            {/* issue tags */}
            {tags.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 10 }}>
                    {tags.map(t => {
                        const active = tagFilter.has(t.label)
                        return (
                            <button
                                key={t.label}
                                onClick={() => setTagFilter(prev => {
                                    const next = new Set(prev)
                                    next.has(t.label) ? next.delete(t.label) : next.add(t.label)
                                    return next
                                })}
                                style={{
                                    padding: "2px 8px",
                                    borderRadius: 99,
                                    fontSize: 9,
                                    fontFamily: "Menlo, Consolas, monospace",
                                    letterSpacing: "0.06em",
                                    textTransform: "uppercase",
                                    fontWeight: 600,
                                    cursor: "pointer",
                                    color: t.color,
                                    background: active
                                        ? `color-mix(in srgb, ${t.color} 22%, var(--surface3))`
                                        : `color-mix(in srgb, ${t.color} 10%, var(--surface2))`,
                                    border: `1px solid color-mix(in srgb, ${t.color} ${active ? "60%" : "25%"}, transparent)`,
                                    transition: "all 0.12s",
                                    outline: "none",
                                }}
                            >{t.label}</button>
                        )
                    })}
                </div>
            )}
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

export function ToolsPanel({ tools, findings }) {
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
