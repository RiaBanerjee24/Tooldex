import { useState, useEffect, useRef } from "react"
import { createPortal } from "react-dom"
import { api } from "../../api.js"
import { GearIcon, StopSquareIcon, InfoIcon, ReplayIcon, TrashIcon } from "../../assets/icons.jsx"
import { formatRelativeTime } from "./serverHelpers.jsx"

export function LlmScanServerButton({ serverId, onDone, lastScannedAt, newFindings, totalFindings, cacheHits, lastScanTotal, hasLlmCache }) {
    const [state, setState] = useState("idle") // idle | running | done | stopped | error
    const [errMsg, setErrMsg] = useState("")
    const [progress, setProgress] = useState({ scanned: 0, total: 0 })
    const [hover, setHover] = useState(false)
    const [pressed, setPressed] = useState(false)
    const [pos, setPos] = useState(null)
    const [infoHover, setInfoHover] = useState(false)
    const [infoPos, setInfoPos] = useState(null)
    const [replayHover, setReplayHover] = useState(false)
    const [clearHover, setClearHover] = useState(false)
    const [clearState, setClearState] = useState("idle") // idle | clearing | done
    const [lastScannedRel, setLastScannedRel] = useState(() => formatRelativeTime(lastScannedAt))
    const btnRef = useRef(null)
    const infoRef = useRef(null)
    const pollRef = useRef(null)

    useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

    useEffect(() => {
        setLastScannedRel(formatRelativeTime(lastScannedAt))
        if (!lastScannedAt) return
        const id = setInterval(() => setLastScannedRel(formatRelativeTime(lastScannedAt)), 30_000)
        return () => clearInterval(id)
    }, [lastScannedAt])

    const stopPolling = () => {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    }

    const startPolling = () => {
        pollRef.current = setInterval(async () => {
            let s
            try {
                s = await api.llmScanStatus(serverId)
            } catch {
                return // transient — try again next tick
            }
            setProgress(p => ({ scanned: s.scanned ?? p.scanned, total: s.total ?? p.total }))
            if (s.status === "done" || s.status === "stopped") {
                stopPolling()
                setState(s.status)
                onDone?.()
                setTimeout(() => setState("idle"), 2000)
            } else if (s.status === "error") {
                stopPolling()
                setErrMsg(s.error || "")
                setState("error")
                setTimeout(() => setState("idle"), 3000)
            }
        }, 800)
    }

    const handleClick = async () => {
        if (state === "running") return
        setState("running")
        setProgress({ scanned: 0, total: 0 })
        try {
            const res = await api.llmScanServer(serverId)
            setProgress({ scanned: res.scanned || 0, total: res.total || 0 })
            startPolling()
        } catch (e) {
            setErrMsg(e.message || "")
            setState("error")
            setTimeout(() => setState("idle"), 3000)
        }
    }

    const handleStop = (e) => {
        e.stopPropagation()
        api.llmScanStop(serverId).catch(() => {})
    }

    const handleClearCache = async (e) => {
        e.stopPropagation()
        if (clearState === "clearing" || !hasLlmCache) return
        setClearState("clearing")
        try {
            await api.llmInvalidateCache(serverId)
            setClearState("done")
            onDone?.()
            setTimeout(() => setClearState("idle"), 1500)
        } catch (err) {
            console.error("clear cache failed:", err)
            setClearState("error")
            setTimeout(() => setClearState("idle"), 2500)
        }
    }

    const showTooltip = () => {
        const r = btnRef.current?.getBoundingClientRect()
        if (r) setPos({ top: r.top, left: r.left + r.width / 2 })
        setHover(true)
    }

    const showInfoTooltip = () => {
        const r = infoRef.current?.getBoundingClientRect()
        if (r) setInfoPos({ top: r.top, left: r.left + r.width / 2 })
        setInfoHover(true)
    }

    const hasScanned = lastScannedAt != null && newFindings != null
    const infoText = !hasScanned ? "Not yet scanned"
        : newFindings > 0
        ? `${newFindings} new vulnerabilit${newFindings === 1 ? "y" : "ies"} found (${totalFindings ?? newFindings} total)`
        : `No new vulnerabilities since last scan (${totalFindings ?? 0} total)`
    const cacheText = cacheHits > 0
        ? `${cacheHits}/${lastScanTotal ?? cacheHits} tool${lastScanTotal === 1 ? "" : "s"} served from cached results`
        : null

    const running = state === "running"
    const label = running ? "judging"
        : state === "done" ? "done ✓"
        : state === "stopped" ? "stopped ✓"
        : state === "error" ? (
            errMsg.includes("not configured") ? "no llm key ✗"
            : errMsg.includes("rejected the API key") ? "bad llm key ✗"
            : errMsg.includes("denied access") ? "access denied ✗"
            : errMsg.includes("doesn't exist") ? "bad model ✗"
            : errMsg.includes("rate limit") ? "rate limited ✗"
            : "failed ✗"
          )
        : "AI security scan"
    const color = state === "done" ? "var(--lime)"
        : state === "stopped" ? "var(--yellow-muted)"
        : state === "error" ? "var(--red)"
        : "var(--cream)"

    return (
        <div style={{ display: "inline-flex", flexDirection: "column", alignItems: "flex-start", gap: 3, flexShrink: 0 }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            {running && (
                <span style={{
                    fontSize: 10, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace",
                    letterSpacing: "0.03em", whiteSpace: "nowrap",
                }}>
                    tools scanned {progress.scanned}/{progress.total}
                </span>
            )}
            <button
                ref={btnRef}
                onClick={handleClick}
                onMouseEnter={showTooltip}
                onMouseLeave={() => { setHover(false); setPressed(false) }}
                onMouseDown={() => setPressed(true)}
                onMouseUp={() => setPressed(false)}
                style={{
                    display: "inline-flex", alignItems: "center", gap: 6,
                    padding: "5px 12px",
                    background: pressed
                        ? "linear-gradient(180deg, var(--surface2), var(--surface3))"
                        : hover
                        ? "linear-gradient(180deg, #333333, var(--surface2))"
                        : "linear-gradient(180deg, var(--surface3), var(--surface2))",
                    border: `2px solid ${pressed || hover ? "var(--lime)" : "var(--lime-dim)"}`,
                    borderRadius: "var(--radius)",
                    cursor: running ? "default" : "pointer", fontSize: 10,
                    color, fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.04em",
                    transition: "color 0.15s, background 0.15s, border-color 0.15s, box-shadow 0.15s, transform 0.1s",
                    whiteSpace: "nowrap", flexShrink: 0,
                    opacity: running ? 0.9 : 1,
                    transform: pressed ? "translateY(1px)" : hover ? "translateY(-1px)" : "none",
                    boxShadow: pressed
                        ? "inset 0 1px 3px rgba(0,0,0,0.5)"
                        : hover
                        ? "0 0 8px rgba(190,215,84,0.4), 0 3px 8px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.08)"
                        : "0 1px 0 rgba(255,255,255,0.03) inset, 0 2px 3px rgba(0,0,0,0.35)",
                }}
            >
                {running && <GearIcon size={11} color="var(--text3)" spinning />}
                {label}
            </button>
            {running && (
                <button
                    onClick={handleStop}
                    title="Stop scan — keeps results collected so far"
                    style={{
                        display: "inline-flex", alignItems: "center", justifyContent: "center",
                        width: 20, height: 20, padding: 0, flexShrink: 0,
                        background: "var(--red-bg)", border: "1px solid var(--red-border)",
                        borderRadius: "var(--radius)", cursor: "pointer",
                    }}
                >
                    <StopSquareIcon size={9} />
                </button>
            )}
            {hover && pos && createPortal(
                <div style={{
                    position: "fixed", top: pos.top - 9, left: pos.left, transform: "translate(-50%, -100%)",
                    padding: "7px 11px", background: "var(--surface3)",
                    border: "1px solid var(--border3)", borderRadius: "var(--radius)",
                    boxShadow: "0 4px 14px rgba(0,0,0,0.5)",
                    fontSize: 10, color: "var(--text2)", fontFamily: "Menlo, Consolas, monospace",
                    lineHeight: 1.5, zIndex: 1000, pointerEvents: "none", maxWidth: 220,
                }}>
                    LLM-as-a-judge based security scan,<br />runs per server
                    <div style={{ marginTop: 4 }}>
                        <span style={{ color: "var(--yellow-muted)", fontWeight: 700, fontSize: 14 }}>⚠</span>{" "}
                        <span style={{ color: "var(--yellow-muted)", fontWeight: 700 }}>WARNING:</span>{" "}
                        This sends data to the LLM provider you configure
                    </div>
                    <div style={{
                        position: "absolute", top: "100%", left: "50%", transform: "translateX(-50%)",
                        width: 0, height: 0,
                        borderLeft: "5px solid transparent", borderRight: "5px solid transparent",
                        borderTop: "5px solid var(--border3)",
                    }} />
                    <div style={{
                        position: "absolute", top: "calc(100% - 1px)", left: "50%", transform: "translateX(-50%)",
                        width: 0, height: 0,
                        borderLeft: "4px solid transparent", borderRight: "4px solid transparent",
                        borderTop: "4px solid var(--surface3)",
                    }} />
                </div>,
                document.body
            )}
        </div>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 11, minHeight: 22, paddingLeft: 2 }}>
            <span
                ref={infoRef}
                onMouseEnter={showInfoTooltip}
                onMouseLeave={() => setInfoHover(false)}
                style={{
                    display: "inline-flex", alignItems: "center", justifyContent: "center",
                    width: 22, height: 22, flexShrink: 0, cursor: "default",
                    background: infoHover ? "var(--surface3)" : "var(--surface2)",
                    border: `1px solid ${infoHover ? "rgba(255,255,255,0.5)" : "rgba(255,255,255,0.32)"}`,
                    borderRadius: "var(--radius)",
                    transition: "background 0.15s, border-color 0.15s",
                }}
            >
                <InfoIcon size={13} color={hasScanned && newFindings > 0 ? "var(--yellow-muted)" : "var(--cream)"} />
            </span>
            {infoHover && infoPos && createPortal(
                <div style={{
                    position: "fixed", top: infoPos.top - 9, left: infoPos.left, transform: "translate(-50%, -100%)",
                    padding: "7px 11px", background: "var(--surface3)",
                    border: "1px solid var(--border3)", borderRadius: "var(--radius)",
                    boxShadow: "0 4px 14px rgba(0,0,0,0.5)",
                    fontSize: 10, color: "var(--text2)", fontFamily: "Menlo, Consolas, monospace",
                    lineHeight: 1.5, zIndex: 1000, pointerEvents: "none", whiteSpace: "nowrap",
                }}>
                    <div>{infoText}</div>
                    {cacheText && (
                        <div style={{ color: "var(--yellow-muted)", marginTop: 3, fontWeight: 600 }}>
                            {cacheText}
                        </div>
                    )}
                    <div style={{
                        position: "absolute", top: "100%", left: "50%", transform: "translateX(-50%)",
                        width: 0, height: 0,
                        borderLeft: "5px solid transparent", borderRight: "5px solid transparent",
                        borderTop: "5px solid var(--border3)",
                    }} />
                    <div style={{
                        position: "absolute", top: "calc(100% - 1px)", left: "50%", transform: "translateX(-50%)",
                        width: 0, height: 0,
                        borderLeft: "4px solid transparent", borderRight: "4px solid transparent",
                        borderTop: "4px solid var(--surface3)",
                    }} />
                </div>,
                document.body
            )}
            <button
                onClick={handleClick}
                onMouseEnter={() => setReplayHover(true)}
                onMouseLeave={() => setReplayHover(false)}
                disabled={running}
                title="Run AI security scan again"
                style={{
                    display: "inline-flex", alignItems: "center", justifyContent: "center",
                    width: 22, height: 22, flexShrink: 0, padding: 0,
                    background: replayHover ? "var(--surface3)" : "var(--surface2)",
                    border: `1px solid ${replayHover ? "rgba(255,255,255,0.5)" : "rgba(255,255,255,0.32)"}`,
                    borderRadius: "var(--radius)",
                    transition: "background 0.15s, border-color 0.15s",
                    cursor: running ? "default" : "pointer",
                    color: "var(--cream)",
                }}
            >
                <ReplayIcon size={13} color="currentColor" />
            </button>
            <button
                onClick={handleClearCache}
                onMouseEnter={() => setClearHover(true)}
                onMouseLeave={() => setClearHover(false)}
                disabled={clearState === "clearing" || !hasLlmCache}
                title={
                    !hasLlmCache ? "No cached results for this server"
                    : clearState === "done" ? "Cache cleared ✓"
                    : clearState === "error" ? "Failed to clear cache — see browser console"
                    : "Clear cached AI scan results for this server"
                }
                style={{
                    display: "inline-flex", alignItems: "center", justifyContent: "center",
                    width: 22, height: 22, flexShrink: 0, padding: 0,
                    background: hasLlmCache && clearHover ? "var(--surface3)" : "var(--surface2)",
                    border: `1px solid ${hasLlmCache && clearHover ? "rgba(255,255,255,0.5)" : "rgba(255,255,255,0.32)"}`,
                    borderRadius: "var(--radius)",
                    transition: "background 0.15s, border-color 0.15s, color 0.15s",
                    cursor: (clearState === "clearing" || !hasLlmCache) ? "default" : "pointer",
                    opacity: !hasLlmCache ? 0.35 : clearState === "clearing" ? 0.6 : 1,
                    color: clearState === "done" ? "var(--lime)"
                        : clearState === "error" ? "var(--red)"
                        : "var(--cream)",
                }}
            >
                <TrashIcon size={13} color="currentColor" />
            </button>
            <span style={{
                fontSize: 9, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace",
                letterSpacing: "0.03em", whiteSpace: "nowrap",
                visibility: lastScannedRel ? "visible" : "hidden",
            }}>
                scanned {lastScannedRel || "—"}
            </span>
        </div>
        </div>
    )
}
