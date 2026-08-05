// report/builder.js
// Normalises raw API data into a format-agnostic ReportData object.
// Both PdfGenerator and MarkdownGenerator consume this shape.

import { groupServers } from '../components/servers/serverHelpers.jsx'

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
            package:         detail.package || null,
            command:         detail.command || null,
            args:            detail.args || [],
            url:             detail.url || null,
            probeStatus:     s.probe_status,
            securityRisk:    s.security_risk || null,
            securityScanned: s.security_scanned || false,
            tools:           detail.discovered_tools || [],
            findings:        detail.security_findings || [],
        }
    })

    // Same grouping as the Servers page sidebar (Claude, Cursor, Codex, Gemini,
    // Docker MCP · <profile>, Custom, ...) — not raw client ids like "codex_project".
    const agentGroups = groupServers(servers).map(g => ({
        agent:       g.key, // matches the group name shown on the Servers page (sidebar headers, vendor cards)
        serverCount: g.servers.length,
        toolCount:   g.servers.reduce((n, s) => n + s.tools.length, 0),
    }))

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
        agents:  agentGroups,
        servers,
    }
}

export function fmtDateTime(date) {
    if (!date) return '—'
    return date.toISOString().replace('T', ' ').slice(0, 19) + ' UTC'
}

/** Single-line launch command for a server — stdio command+args, or its URL. */
export function serverCommandLine(s) {
    if (s.command) return [s.command, ...(s.args || [])].join(' ')
    if (s.url) return s.url
    return null
}
