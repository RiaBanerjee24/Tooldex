import { useState } from "react"
import "./index.css"
import { api } from "./api.js"
import { useFetch } from "./hooks/useFetch.js"
import { Wrap } from "./components/ui.jsx"
import { Topbar } from "./components/Topbar.jsx"
import { Dashboard } from "./views/Dashboard.jsx"
import { Agents } from "./views/Agents.jsx"
import { Servers } from "./views/Servers.jsx"
import { Permissions } from "./views/Permissions.jsx"

export default function App() {
    const [tab, setTab] = useState("Dashboard")
    const { data: health } = useFetch(api.health)
    const { data: agents } = useFetch(api.agents)
    const { data: servers } = useFetch(api.servers)

    return (
        <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
            <Topbar tab={tab} setTab={setTab} health={health} />
            <div style={{ flex: 1 }}>
                <Wrap>
                    {tab === "Dashboard" && <Dashboard health={health} agentsData={agents} serversData={servers} />}
                    {tab === "Agents" && <Agents />}
                    {tab === "Servers" && <Servers />}
                    {tab === "Permissions" && <Permissions />}
                </Wrap>
            </div>
        </div>
    )
}