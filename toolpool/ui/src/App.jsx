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
        </div>
    )
}