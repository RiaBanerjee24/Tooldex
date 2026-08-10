import { useState, useRef, useEffect } from "react"

export function DownloadServerReport({ server, scannedAt }) {
    const [open, setOpen] = useState(false)
    const [status, setStatus] = useState("idle") // idle | loading | done | error
    const [errMsg, setErrMsg] = useState(null)
    const [includeSecurity, setIncludeSecurity] = useState(false)
    const ref = useRef(null)

    useEffect(() => {
        if (!open) return
        function onClickOutside(e) {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false)
        }
        document.addEventListener("mousedown", onClickOutside)
        return () => document.removeEventListener("mousedown", onClickOutside)
    }, [open])

    async function handleDownload(format) {
        if (!server) return
        setOpen(false)
        setStatus("loading")
        setErrMsg(null)
        try {
            const { downloadReport } = await import("../../report/download.js")
            await downloadReport([server], scannedAt, format, { includeSecurity, scopeLabel: server.name })
            setStatus("done")
            setTimeout(() => setStatus("idle"), 2500)
        } catch (err) {
            setErrMsg(err.message)
            setStatus("error")
            setTimeout(() => setStatus("idle"), 3000)
        }
    }

    const isLoading = status === "loading"
    const label = status === "loading" ? "building…"
        : status === "done"    ? "downloaded ✓"
        : status === "error"   ? "failed ✗"
        : "download report"
    const color = status === "done" ? "var(--lime)"
        : status === "error" ? "var(--red)"
        : "var(--cream)"

    return (
        <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
            <button
                onClick={() => !isLoading && setOpen(o => !o)}
                style={{
                    padding: "5px 12px", background: "var(--surface2)",
                    border: "1.5px solid rgba(255,255,255,0.3)", borderRadius: "var(--radius)",
                    cursor: isLoading ? "default" : "pointer", fontSize: 10,
                    color, fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.04em",
                    transition: "color 0.2s", whiteSpace: "nowrap", flexShrink: 0,
                    opacity: isLoading ? 0.7 : 1,
                }}
            >
                {label}
            </button>

            {open && (
                <div style={{
                    position: "absolute", top: "calc(100% + 5px)", right: 0,
                    background: "var(--surface2)",
                    border: "1px solid var(--border3)",
                    borderRadius: "var(--radius-lg)",
                    padding: "6px 0",
                    minWidth: 210,
                    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                    zIndex: 200,
                }}>
                    <label style={{
                        display: "flex", alignItems: "center", gap: 8,
                        padding: "6px 14px", cursor: "pointer", userSelect: "none",
                        fontSize: 11, color: "var(--text2)", fontFamily: "Menlo, Consolas, monospace",
                    }}>
                        <input
                            type="checkbox"
                            checked={includeSecurity}
                            onChange={() => setIncludeSecurity(v => !v)}
                            style={{ accentColor: "var(--lime)", width: 12, height: 12, cursor: "pointer", flexShrink: 0 }}
                        />
                        Include security scan
                    </label>

                    <div style={{ borderTop: "1px solid var(--border)", margin: "6px 0" }} />

                    <div style={{ display: "flex", gap: 6, padding: "4px 14px 2px" }}>
                        <button
                            onClick={() => handleDownload("pdf")}
                            style={{
                                flex: 1, padding: "7px 0", background: "var(--surface3)",
                                border: "1px solid var(--border2)", borderRadius: "var(--radius)",
                                cursor: "pointer", fontSize: 10, color: "var(--cream)",
                                fontFamily: "Menlo, Consolas, monospace",
                            }}
                        >
                            PDF
                        </button>
                        <button
                            onClick={() => handleDownload("markdown")}
                            style={{
                                flex: 1, padding: "7px 0", background: "var(--surface3)",
                                border: "1px solid var(--border2)", borderRadius: "var(--radius)",
                                cursor: "pointer", fontSize: 10, color: "var(--cream)",
                                fontFamily: "Menlo, Consolas, monospace",
                            }}
                        >
                            Markdown
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}
