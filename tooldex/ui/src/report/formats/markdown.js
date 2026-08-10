// report/formats/markdown.js
// MarkdownGenerator — produces a .md report and triggers a file download.
// Implements the generator interface: generate(reportData) → void.

import { fmtDateTime, serverCommandLine } from '../builder.js'
import { groupServers } from '../../components/servers/serverHelpers.jsx'

function download(content, filename) {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
}

function mdTable(headers, rows) {
    const sep = headers.map(() => '---')
    const fmt = row => '| ' + row.join(' | ') + ' |'
    return [fmt(headers), fmt(sep), ...rows.map(fmt)].join('\n')
}

export class MarkdownGenerator {
    generate(data, options = {}) {
        const { includeSecurity = false, scopeLabel = 'all' } = options
        const { meta, summary, agents, servers } = data
        const lines = []

        const groups = groupServers(servers)

        // ── Header ────────────────────────────────────────────────────────────
        lines.push('# Tooldex — Security & Discovery Report', '')
        lines.push(`**Generated:** ${fmtDateTime(meta.generatedAt)}`)
        if (meta.scannedAt) lines.push(`**Scanned At:** ${fmtDateTime(meta.scannedAt)}`)
        lines.push('')
        lines.push(`**Repository:** [${meta.repoUrl}](${meta.repoUrl})`)
        lines.push(`**Documentation:** [${meta.docsUrl}](${meta.docsUrl})`)
        lines.push('')
        lines.push('---', '')

        // ── Table of Contents ─────────────────────────────────────────────────
        lines.push('## Table of Contents', '')
        lines.push('1. [Overview](#overview)')
        lines.push('2. [AI Agents](#ai-agents)')
        lines.push('3. [Servers & Tools](#servers--tools)')
        if (includeSecurity) lines.push('4. [Security Findings](#security-findings)')
        lines.push('', '---', '')

        // ── Overview ──────────────────────────────────────────────────────────
        lines.push('## Overview', '')
        lines.push(mdTable(
            ['Metric', 'Count'],
            [
                ['Total Servers',    String(summary.totalServers)],
                ['Total Tools',      String(summary.totalTools)],
                ['Servers Scanned',  String(summary.cleanServers + summary.flaggedServers)],
                ['Clean Servers',    String(summary.cleanServers)],
                ['Flagged Servers',  String(summary.flaggedServers)],
                ['Total Findings',   String(summary.totalFindings)],
            ]
        ))
        lines.push('', '---', '')

        // ── Agents ────────────────────────────────────────────────────────────
        lines.push('## AI Agents', '')
        lines.push(mdTable(
            ['Agent', 'Servers', 'Tools'],
            agents.map(a => [a.agent, String(a.serverCount), String(a.toolCount)])
        ))
        lines.push('', '---', '')

        // ── Tools ─────────────────────────────────────────────────────────────
        // Each server heading carries its agent ("Gemini:postman-mcp-server")
        // and each tool name carries its server ("postman-mcp-server:createCollection"),
        // so no separate per-agent sections or Server column are needed.
        lines.push('## Servers & Tools', '')
        for (const group of groups) {
            for (const s of group.servers) {
                lines.push(`### ${group.key}:${s.name}`)
                const metaParts = []
                if (s.transport) metaParts.push(`**Transport:** ${s.transport}`)
                if (s.package) metaParts.push(`**Package:** ${s.package}`)
                const cmd = serverCommandLine(s)
                if (cmd) metaParts.push(`**Command:** \`${cmd}\``)
                if (metaParts.length) lines.push(metaParts.join('  '))
                if (!s.tools.length) {
                    lines.push('_No tools discovered._', '')
                    continue
                }
                lines.push('')
                lines.push(mdTable(
                    ['Tool', 'Description'],
                    s.tools.map(t => [
                        `\`${s.name}:${t.name}\``,
                        (t.description || '—').replace(/\|/g, '\\|'),
                    ])
                ))
                lines.push('')
            }
        }
        lines.push('---', '')

        // ── Security ──────────────────────────────────────────────────────────
        if (includeSecurity) {
            lines.push('## Security Findings', '')
            const flagged = servers.filter(s => s.findings.length > 0)
            if (!flagged.length) {
                lines.push('_No security findings detected across all scanned servers._', '')
            } else {
                for (const s of flagged) {
                    lines.push(`### ${s.name}`, '')
                    lines.push(mdTable(
                        ['Tool', 'Severity', 'Analyzer', 'Category', 'Summary'],
                        s.findings.map(f => [
                            f.tool_name || '—',
                            f.severity || '—',
                            f.analyzer || '—',
                            f.threat_category || '—',
                            (f.summary || '—').replace(/\|/g, '\\|'),
                        ])
                    ))
                    lines.push('')
                }
            }
            lines.push('---', '')
        }

        lines.push(`_Report generated by [Tooldex](${meta.repoUrl})_`)

        const filename = `tooldex-report-${scopeLabel}-${new Date().toISOString().slice(0, 10)}.md`
        download(lines.join('\n'), filename)
    }
}
