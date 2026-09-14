import { useState, useEffect, useRef } from "react"
import { createPortal } from "react-dom"
import { api } from "../../api.js"
import { ShieldIcon, SecurityWarningIcon } from "../../assets/icons.jsx"

const btnStyle = (color, border) => ({
    padding: "5px 12px", background: "var(--surface2)",
    border: `1.5px solid ${border || "rgba(255,255,255,0.3)"}`, borderRadius: "var(--radius)",
    cursor: "pointer", fontSize: 10,
    color, fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.04em",
    transition: "color 0.2s, border-color 0.2s", whiteSpace: "nowrap", flexShrink: 0,
})

const linkStyle = {
    background: "none", border: "none", padding: 0, cursor: "pointer",
    fontSize: 10, color: "var(--text3)", fontFamily: "Menlo, Consolas, monospace",
    textDecoration: "underline", letterSpacing: "0.02em",
}

// Approve / deny / revoke gate for a stdio server Tooldex has to spawn to
// list its tools. Mirrors RescanServerButton's anchored-popup pattern for
// the (destructive-ish) revoke confirmation — this codebase has no modal
// primitive, so an inline popup is the established convention.
export function TrustGateButtons({ serverId, trustStatus, trustDiff, onDone }) {
    const [busy, setBusy] = useState(null) // null | "allow" | "deny" | "revoke"
    const [error, setError] = useState(false)
    const [confirmOpen, setConfirmOpen] = useState(false)
    const [diffOpen, setDiffOpen] = useState(false)
    const [pos, setPos] = useState(null)
    const revokeBtnRef = useRef(null)
    const popRef = useRef(null)

    useEffect(() => {
        if (!confirmOpen) return
        function handleClick(e) {
            if (popRef.current && !popRef.current.contains(e.target) && !revokeBtnRef.current?.contains(e.target)) {
                setConfirmOpen(false)
            }
        }
        document.addEventListener("mousedown", handleClick)
        return () => document.removeEventListener("mousedown", handleClick)
    }, [confirmOpen])

    if (!trustStatus) return null // non-stdio servers aren't gated

    async function decide(decision) {
        setBusy(decision)
        setError(false)
        try {
            await api.trustServer(serverId, decision)
            onDone?.()
        } catch {
            setError(true)
            setTimeout(() => setError(false), 2500)
        } finally {
            setBusy(null)
        }
    }

    async function revoke() {
        setConfirmOpen(false)
        setBusy("revoke")
        setError(false)
        try {
            await api.revokeTrust(serverId)
            onDone?.()
        } catch {
            setError(true)
            setTimeout(() => setError(false), 2500)
        } finally {
            setBusy(null)
        }
    }

    function openConfirm() {
        const r = revokeBtnRef.current?.getBoundingClientRect()
        if (r) setPos({ top: r.bottom + 8, left: r.left })
        setConfirmOpen(true)
    }

    if (trustStatus === "pending") {
        return (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <button
                    onClick={() => decide("allow")}
                    disabled={busy != null}
                    style={btnStyle(busy === "allow" ? "var(--yellow-muted)" : "var(--lime)", "var(--lime-border)")}
                >
                    {busy === "allow" ? "approving…" : error ? "failed ✗" : "approve"}
                </button>
                <button
                    onClick={() => decide("deny")}
                    disabled={busy != null}
                    style={btnStyle(busy === "deny" ? "var(--yellow-muted)" : "var(--red)", "var(--red-border)")}
                >
                    {busy === "deny" ? "declining…" : "deny"}
                </button>
            </div>
        )
    }

    if (trustStatus === "denied") {
        return (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 10, color: "var(--red)", fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.04em" }}>
                    {busy === "allow" ? "approving…" : "declined"}
                </span>
                <button onClick={() => decide("allow")} disabled={busy != null} style={linkStyle}>
                    approve instead
                </button>
            </div>
        )
    }

    if (trustStatus === "changed") {
        return (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <SecurityWarningIcon size={12} color="var(--yellow-muted)" />
                    <span style={{ fontSize: 10, color: "var(--yellow-muted)", fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.04em" }}>
                        tool list changed, needs fresh approval to get tool list
                    </span>
                    <button onClick={() => setDiffOpen(o => !o)} style={linkStyle}>
                        {diffOpen ? "hide diff" : "review changes"}
                    </button>
                    <button
                        onClick={() => decide("allow")}
                        disabled={busy != null}
                        style={btnStyle(busy === "allow" ? "var(--yellow-muted)" : "var(--lime)", "var(--lime-border)")}
                    >
                        {busy === "allow" ? "approving…" : "approve changes"}
                    </button>
                </div>
                {diffOpen && <TrustDiff diff={trustDiff} />}
            </div>
        )
    }

    // "allowed"
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <ShieldIcon size={12} color="var(--lime)" />
                <span style={{ fontSize: 9, color: "var(--lime)", fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                    approved
                </span>
            </div>
            <button ref={revokeBtnRef} onClick={openConfirm} disabled={busy != null} style={linkStyle}>
                {busy === "revoke" ? "revoking…" : error ? "failed ✗" : "revoke"}
            </button>
            {confirmOpen && pos && createPortal(
                <div ref={popRef} style={{
                    position: "fixed", top: pos.top, left: pos.left, zIndex: 1000,
                    width: 240, padding: "10px 12px", background: "var(--surface3)",
                    border: "1px solid var(--border3)", borderRadius: "var(--radius)",
                    boxShadow: "0 4px 14px rgba(0,0,0,0.5)",
                    fontSize: 10.5, color: "var(--text2)", fontFamily: "Menlo, Consolas, monospace",
                    lineHeight: 1.5,
                }}>
                    Revoke trust for this server? It will need to be approved again before Tooldex probes it.
                    <div style={{ display: "flex", gap: 6, justifyContent: "flex-end", marginTop: 10 }}>
                        <button onClick={() => setConfirmOpen(false)} style={{
                            padding: "4px 9px", background: "var(--surface2)",
                            border: "1px solid var(--border2)", borderRadius: "var(--radius)",
                            cursor: "pointer", fontSize: 10, color: "var(--text3)",
                            fontFamily: "Menlo, Consolas, monospace",
                        }}>
                            cancel
                        </button>
                        <button onClick={revoke} style={{
                            padding: "4px 9px", background: "var(--red-bg)",
                            border: "1px solid var(--red-border)", borderRadius: "var(--radius)",
                            cursor: "pointer", fontSize: 10, color: "var(--red)",
                            fontFamily: "Menlo, Consolas, monospace",
                        }}>
                            revoke
                        </button>
                    </div>
                </div>,
                document.body
            )}
        </div>
    )
}

const DIFF_LABEL = { added: "+ added", removed: "− removed", changed: "~ changed" }
const DIFF_COLOR = { added: "var(--lime)", removed: "var(--red)", changed: "var(--yellow-muted)" }

function TrustDiff({ diff }) {
    if (!diff?.length) return null
    return (
        <div style={{
            background: "var(--surface2)", borderRadius: "var(--radius)",
            border: "1px solid var(--border)", overflow: "hidden", width: "100%", maxWidth: 420,
        }}>
            {diff.map((d, i) => (
                <div key={`${d.tool}-${i}`} style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "6px 10px",
                    borderBottom: i < diff.length - 1 ? "1px solid var(--border)" : "none",
                    fontSize: 10.5, fontFamily: "Menlo, Consolas, monospace",
                }}>
                    <span style={{ color: DIFF_COLOR[d.change], flexShrink: 0, minWidth: 62 }}>{DIFF_LABEL[d.change]}</span>
                    <span style={{ color: "var(--cream)" }}>{d.tool}</span>
                </div>
            ))}
        </div>
    )
}
