// report/builder.js
// Normalises raw API data into a format-agnostic ReportData object.
// Both PdfGenerator and MarkdownGenerator consume this shape.

export const REPO_URL  = 'https://github.com/RiaBanerjee24/Tooldex'
export const DOCS_URL  = 'https://riabanerjee24.github.io/Tooldex/'

/**
 * @param {object[]} serverList   — from api.servers() .servers array
 * @param {object[]} serverDetails — from api.server(id) for each server
 * @param {string|null} scannedAt  — ISO timestamp from manifest
 * @returns {ReportData}
 */
export function buildReportData(serverList, serverDetails, scannedAt) {
    const detailById = Object.fromEntries(serverDetails.map(d => [d.id, d]))

    const servers = serverList.map(s => {
        const detail = detailById[s.id] || s
        return {
            id:              s.id,
            name:            s.name,
            client:          s.client || 'unknown',
            transport:       s.transport,
            probeStatus:     s.probe_status,
            securityRisk:    s.security_risk || null,
            securityScanned: s.security_scanned || false,
            tools:           detail.discovered_tools || [],
            findings:        detail.security_findings || [],
        }
    })

    const agentMap = {}
    for (const s of servers) {
        const key = s.client
        if (!agentMap[key]) agentMap[key] = { client: key, serverCount: 0, toolCount: 0 }
        agentMap[key].serverCount++
        agentMap[key].toolCount += s.tools.length
    }

    const totalTools    = servers.reduce((n, s) => n + s.tools.length, 0)
    const totalFindings = servers.reduce((n, s) => n + s.findings.length, 0)
    const flaggedCount  = servers.filter(s => s.securityRisk).length
    const cleanCount    = servers.filter(s => s.securityScanned && !s.securityRisk).length

    return {
        meta: {
            generatedAt: new Date(),
            scannedAt:   scannedAt ? new Date(scannedAt) : null,
            repoUrl:     REPO_URL,
            docsUrl:     DOCS_URL,
        },
        summary: {
            totalServers:  servers.length,
            totalTools,
            totalFindings,
            cleanServers:  cleanCount,
            flaggedServers: flaggedCount,
        },
        agents:  Object.values(agentMap),
        servers,
    }
}

export function fmtDateTime(date) {
    if (!date) return '—'
    return date.toISOString().replace('T', ' ').slice(0, 19) + ' UTC'
}
