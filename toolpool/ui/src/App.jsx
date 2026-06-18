import { useState } from "react"
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
    const { data: health } = useFetch(api.health)
    const { data: servers } = useFetch(api.servers)

    const navigateToServer = (id) => {
        setSelectedServerId(id)
        setTab("Servers")
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
                        />
                    )}
                    {tab === "Servers" && <Servers initialSel={selectedServerId} />}
                </Wrap>
            </div>
            <footer style={{
                background: "#0a0d14",
                borderTop: "1px solid #1a1f2e",
                padding: "18px 32px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
                fontSize: 12,
                color: "#4a5268",
                fontFamily: "Menlo, Consolas, monospace",
            }}>
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
            </footer>
        </div>
    )
}