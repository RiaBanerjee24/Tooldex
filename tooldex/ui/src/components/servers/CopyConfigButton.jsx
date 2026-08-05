import { useState } from "react"

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

export function CopyConfigButton({ detail }) {
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
            border: "1.5px solid rgba(255,255,255,0.3)", borderRadius: "var(--radius)",
            cursor: "pointer", fontSize: 10,
            color: state === "copied" ? "var(--lime)" : "var(--cream)",
            fontFamily: "Menlo, Consolas, monospace", letterSpacing: "0.04em",
            transition: "color 0.2s", whiteSpace: "nowrap", flexShrink: 0,
        }}>
            {state === "copied" ? "copied ✓" : "copy config"}
        </button>
    )
}
