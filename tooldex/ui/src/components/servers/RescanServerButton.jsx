import { useState, useEffect, useRef } from "react"
import { createPortal } from "react-dom"
import { api } from "../../api.js"

export function RescanServerButton({ serverId, onDone }) {
    const [state, setState] = useState("idle") // idle | scanning | done | error | blocked
    const [pos, setPos] = useState(null)
    const btnRef = useRef(null)
    const popRef = useRef(null)

    const doRescan = async (force) => {
        setState("scanning")
        try {
            await api.rescanServer(serverId, force)
            setState("done")
            onDone?.()
            setTimeout(() => setState("idle"), 2000)
        } catch (e) {
            if (e.message === "llm_scan_running") {
                const r = btnRef.current?.getBoundingClientRect()
                if (r) setPos({ top: r.bottom + 8, left: r.left })
                setState("blocked")
                return
            }
            setState("error")
            setTimeout(() => setState("idle"), 2500)
        }
    }

    const handleClick = () => {
        if (state === "scanning") return
        doRescan(false)
    }

    useEffect(() => {
        if (state !== "blocked") return
        function handleClick(e) {
            if (popRef.current && !popRef.current.contains(e.target) && !btnRef.current?.contains(e.target)) {
                setState("idle")
            }
        }
        document.addEventListener("mousedown", handleClick)
        return () => document.removeEventListener("mousedown", handleClick)
    }, [state])

    const label = state === "scanning" ? "scanning…"
        : state === "done" ? "done ✓"
        : state === "error" ? "failed ✗"
        : state === "blocked" ? "blocked ⚠"
        : "rescan server"
    const color = state === "done" ? "var(--lime)"
        : state === "error" ? "var(--red)"
        : state === "blocked" ? "var(--yellow-muted)"
        : "var(--cream)"

    return (
        <>
            <button ref={btnRef} onClick={handleClick} style={{
                padding: "5px 12px", background: "var(--surface2)",
                border: "1.5px solid rgba(255,255,255,0.3)", borderRadius: "var(--radius)",
                cursor: state === "scanning" ? "default" : "pointer", fontSize: 10,
                color, fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.04em",
                transition: "color 0.2s", whiteSpace: "nowrap", flexShrink: 0,
                opacity: state === "scanning" ? 0.7 : 1,
            }}>
                {label}
            </button>
            {state === "blocked" && pos && createPortal(
                <div ref={popRef} style={{
                    position: "fixed", top: pos.top, left: pos.left, zIndex: 1000,
                    width: 220, padding: "10px 12px", background: "var(--surface3)",
                    border: "1px solid var(--yellow-muted)", borderRadius: "var(--radius)",
                    boxShadow: "0 4px 14px rgba(0,0,0,0.5)",
                    fontSize: 10.5, color: "var(--text2)", fontFamily: "Menlo, Consolas, monospace",
                    lineHeight: 1.5,
                }}>
                    AI security scan is running for this server. Rescanning now will abort it mid-scan.
                    <div style={{ display: "flex", gap: 6, justifyContent: "flex-end", marginTop: 10 }}>
                        <button
                            onClick={() => setState("idle")}
                            style={{
                                padding: "4px 9px", background: "var(--surface2)",
                                border: "1px solid var(--border2)", borderRadius: "var(--radius)",
                                cursor: "pointer", fontSize: 10, color: "var(--text3)",
                                fontFamily: "Menlo, Consolas, monospace",
                            }}
                        >
                            cancel
                        </button>
                        <button
                            onClick={() => doRescan(true)}
                            style={{
                                padding: "4px 9px", background: "var(--red-bg)",
                                border: "1px solid var(--red-border)", borderRadius: "var(--radius)",
                                cursor: "pointer", fontSize: 10, color: "var(--red)",
                                fontFamily: "Menlo, Consolas, monospace",
                            }}
                        >
                            force rescan
                        </button>
                    </div>
                </div>,
                document.body
            )}
        </>
    )
}
