import { useState, useEffect } from "react"
import "./index.css"
import { api } from "./api.js"
import { useFetch } from "./hooks/useFetch.js"
import { Wrap } from "./components/ui.jsx"
import { Topbar } from "./components/Topbar.jsx"
import { Dashboard } from "./views/Dashboard.jsx"
import { Servers } from "./views/Servers.jsx"

export default function App() {
    const [tab, setTab] = useState("Dashboard")
    const [selectedServerId, setSelectedServerId] = useState(null)
    const [scanKey, setScanKey] = useState(0)

    // Shared rescan state — lifted here so both pages stay in sync
    const [rescanState, setRescanState] = useState("idle") // idle | scanning | done
    const [rescanSeconds, setRescanSeconds] = useState(0)

    useEffect(() => {
        if (rescanState !== "scanning") { setRescanSeconds(0); return }
        const id = setInterval(() => setRescanSeconds(s => s + 1), 1000)
        return () => clearInterval(id)
    }, [rescanState])

    const { data: health } = useFetch(api.health, [scanKey])
    const { data: servers } = useFetch(api.servers, [scanKey])

    const navigateToServer = (id) => {
        setSelectedServerId(id)
        setTab("Servers")
    }

    const handleRescan = async () => {
        if (rescanState === "scanning") return
        setRescanState("scanning")
        try {
            const res = await api.rescan()
            if (res?.status === "already_scanning") { setRescanState("idle"); return res }
            setScanKey(k => k + 1)
            setRescanState("done")
            setTimeout(() => setRescanState("idle"), 2000)
            return res
        } catch {
            setRescanState("idle")
        }
    }

    return (
        <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
            <Topbar tab={tab} setTab={setTab} health={health} />
            <div style={{ flex: 1 }}>
                <Wrap>
                    {tab === "Dashboard" && (
                        <Dashboard
                            health={health}
                            serversData={servers}
                            onNavigateServers={() => setTab("Servers")}
                            onNavigateToServer={navigateToServer}
                            onRescan={handleRescan}
                            rescanState={rescanState}
                            rescanSeconds={rescanSeconds}
                        />
                    )}
                    {tab === "Servers" && (
                        <Servers
                            initialSel={selectedServerId}
                            scanKey={scanKey}
                            onRescan={handleRescan}
                            rescanState={rescanState}
                            rescanSeconds={rescanSeconds}
                        />
                    )}
                </Wrap>
            </div>
            <footer style={{
                background: "#0a0d14",
                borderTop: "1px solid #1a1f2e",
                padding: "18px 32px",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 6,
                fontSize: 12,
                color: "#4a5268",
                fontFamily: "Menlo, Consolas, monospace",
            }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span>© {new Date().getFullYear()} made by</span>
                    <a
                        href="https://www.linkedin.com/in/riabanerjee2406/"
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: "#6b7591", textDecoration: "none", borderBottom: "1px solid #2e3448" }}
                        onMouseEnter={e => e.target.style.color = "#BED754"}
                        onMouseLeave={e => e.target.style.color = "#6b7591"}
                    >
                        Ria Banerjee
                    </a>
                </div>
                <a
                    href="https://riabanerjee24.github.io/Toolpool/"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: "#4a5268", textDecoration: "none", letterSpacing: "0.05em" }}
                    onMouseEnter={e => e.target.style.color = "#BED754"}
                    onMouseLeave={e => e.target.style.color = "#4a5268"}
                >
                    docs ↗
                </a>
            </footer>
        </div>
    )
}
