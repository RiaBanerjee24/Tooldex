import { useMemo, useRef } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { SidebarBtn, ProvenanceDot } from "../ui.jsx"
import { classifyClient, effectiveStatus, ConnectionStatusBadge, ScopeTag, SecurityStatusIcon } from "./serverHelpers.jsx"

export function ServerSidebarList({ filteredGroups, sel, setSel, serverScanState }) {
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
