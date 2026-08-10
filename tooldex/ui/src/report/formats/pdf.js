// report/formats/pdf.js
// PdfGenerator — multi-page A4 PDF report: servers + tool descriptions, plus
// an optional Security Findings section (servers/tools with findings only).
//
// Implements the generator interface: generate(reportData, options) → void (triggers download).

import jsPDF from 'jspdf'
import autoTable from 'jspdf-autotable'
import { LOGO_POLYGONS } from '../../assets/logo.js'
import { fmtDateTime, serverCommandLine } from '../builder.js'
import { groupServers } from '../../components/servers/serverHelpers.jsx'

// ── colour palette ────────────────────────────────────────────────────────────
const C = {
    coverBg:      [10,  13,  20],
    coverText:    [245, 240, 232],
    coverSubtext: [160, 170, 150],
    coverAccent:  [223, 232, 168],
    white:        [255, 255, 255],
    headingText:  [15,  23,  42],
    bodyText:     [51,  65,  85],
    mutedText:    [100, 116, 139],
    tableHead:    [30,  41,  59],
    tableHeadTxt: [241, 245, 249],
    tableRowAlt:  [248, 250, 252],
    borderColor:  [226, 232, 240],
    accentLime:   [138, 154, 40],
    sevCritical:  [185, 28,  28],
    sevHigh:      [239, 68,  68],
    sevMedium:    [245, 158, 11],
    sevLow:       [56,  189, 248],
    sevInfo:      [148, 163, 184],
}

function sevColor(sev) {
    switch ((sev || '').toUpperCase()) {
        case 'CRITICAL': return C.sevCritical
        case 'HIGH':     return C.sevHigh
        case 'MEDIUM':   return C.sevMedium
        case 'LOW':      return C.sevLow
        default:         return C.sevInfo
    }
}

function hexToRgb(hex) {
    return [parseInt(hex.slice(1,3),16), parseInt(hex.slice(3,5),16), parseInt(hex.slice(5,7),16)]
}

// ── layout constants ──────────────────────────────────────────────────────────
const PAGE_W  = 210
const PAGE_H  = 297
const MARGIN  = 15
const CONTENT = PAGE_W - MARGIN * 2

// ── logo ──────────────────────────────────────────────────────────────────────
function drawLogo(doc, cx, cy, size) {
    const scale = size / 64
    const ox = cx - size / 2
    const oy = cy - size / 2
    for (const { points, fill } of LOGO_POLYGONS) {
        const [r, g, b] = hexToRgb(fill)
        doc.setFillColor(r, g, b)
        doc.setDrawColor(r, g, b)
        const [p0, p1, p2] = points
        const sx = p => ox + p[0] * scale
        const sy = p => oy + p[1] * scale
        doc.lines(
            [[sx(p1)-sx(p0), sy(p1)-sy(p0)], [sx(p2)-sx(p1), sy(p2)-sy(p1)], [sx(p0)-sx(p2), sy(p0)-sy(p2)]],
            sx(p0), sy(p0), [1,1], 'F', true
        )
    }
}

// ── helpers ───────────────────────────────────────────────────────────────────
function setFont(doc, size, style = 'normal', color = C.bodyText) {
    doc.setFont('helvetica', style)
    doc.setFontSize(size)
    doc.setTextColor(...color)
}

function hline(doc, y, color = C.borderColor) {
    doc.setDrawColor(...color)
    doc.setLineWidth(0.2)
    doc.line(MARGIN, y, PAGE_W - MARGIN, y)
}

// Compact shared table style — tighter padding and smaller font than default
function tableStyle(extraStyles = {}) {
    return {
        font: 'helvetica',
        fontSize: 8,
        cellPadding: { top: 2, bottom: 2, left: 3, right: 3 },
        textColor: [...C.bodyText],
        lineColor: [...C.borderColor],
        lineWidth: 0.1,
        overflow: 'linebreak',
        ...extraStyles,
    }
}

function headStyle(extraStyles = {}) {
    return {
        fillColor: [...C.tableHead],
        textColor: [...C.tableHeadTxt],
        fontStyle: 'bold',
        fontSize: 8,
        ...extraStyles,
    }
}

function runTable(doc, startY, head, body, columnStyles = {}, extraOpts = {}) {
    autoTable(doc, {
        startY,
        head,
        body,
        margin: { left: MARGIN, right: MARGIN },
        styles: tableStyle(),
        headStyles: headStyle(),
        alternateRowStyles: { fillColor: [...C.tableRowAlt] },
        columnStyles,
        theme: 'grid',
        ...extraOpts,
    })
    return doc.lastAutoTable.finalY + 8
}

// ── footer ────────────────────────────────────────────────────────────────────
function addFooters(doc, dateStr, totalPages) {
    for (let i = 2; i <= totalPages; i++) {
        doc.setPage(i)
        hline(doc, PAGE_H - 12, C.borderColor)
        setFont(doc, 7, 'normal', C.mutedText)
        doc.text(`Tooldex Report  ·  Generated ${dateStr}`, MARGIN, PAGE_H - 7)
        doc.text(`Page ${i} of ${totalPages}`, PAGE_W - MARGIN, PAGE_H - 7, { align: 'right' })
    }
}

// ── cover ─────────────────────────────────────────────────────────────────────
function buildCover(doc, meta, scopeTitle) {
    doc.setFillColor(...C.coverBg)
    doc.rect(0, 0, PAGE_W, PAGE_H, 'F')

    drawLogo(doc, PAGE_W / 2, 90, 36)

    setFont(doc, 42, 'bold', C.coverText)
    doc.text('Tooldex', PAGE_W / 2, 122, { align: 'center' })

    setFont(doc, 13, 'normal', C.coverAccent)
    doc.text(`Security & Discovery Report — ${scopeTitle}`, PAGE_W / 2, 133, { align: 'center' })

    doc.setDrawColor(...C.accentLime)
    doc.setLineWidth(0.4)
    doc.line(60, 142, 150, 142)

    setFont(doc, 9, 'normal', C.coverSubtext)
    doc.text('Generated', PAGE_W / 2, 153, { align: 'center' })
    setFont(doc, 11, 'bold', C.coverText)
    doc.text(fmtDateTime(meta.generatedAt), PAGE_W / 2, 160, { align: 'center' })

    if (meta.scannedAt) {
        setFont(doc, 9, 'normal', C.coverSubtext)
        doc.text('Scanned At', PAGE_W / 2, 170, { align: 'center' })
        setFont(doc, 11, 'bold', C.coverText)
        doc.text(fmtDateTime(meta.scannedAt), PAGE_W / 2, 177, { align: 'center' })
    }

    const linkY = 210
    setFont(doc, 9, 'normal', C.coverSubtext)
    doc.text('Repository',     PAGE_W / 2 - 2, linkY,     { align: 'right' })
    doc.text('Documentation',  PAGE_W / 2 - 2, linkY + 9, { align: 'right' })
    setFont(doc, 9, 'normal', C.coverAccent)
    doc.textWithLink(meta.repoUrl, PAGE_W / 2 + 2, linkY,     { url: meta.repoUrl })
    doc.textWithLink(meta.docsUrl, PAGE_W / 2 + 2, linkY + 9, { url: meta.docsUrl })

    doc.setDrawColor(...C.coverSubtext)
    doc.setLineWidth(0.15)
    doc.line(MARGIN, PAGE_H - 14, PAGE_W - MARGIN, PAGE_H - 14)
    setFont(doc, 7, 'normal', C.coverSubtext)
    doc.text('riabanerjee24.github.io/Tooldex', PAGE_W / 2, PAGE_H - 8, { align: 'center' })
}

// ── TOC ───────────────────────────────────────────────────────────────────────
function buildTOC(doc, pageRef) {
    setFont(doc, 20, 'bold', C.headingText)
    doc.text('Contents', MARGIN, 32)
    hline(doc, 37)

    let y = 48
    for (const [label, page] of Object.entries(pageRef)) {
        setFont(doc, 11, 'normal', C.bodyText)
        doc.text(label, MARGIN, y)
        setFont(doc, 11, 'normal', C.mutedText)
        doc.text(String(page), PAGE_W - MARGIN, y, { align: 'right' })
        doc.setDrawColor(...C.borderColor)
        doc.setLineWidth(0.15)
        const lx1 = MARGIN + doc.getTextWidth(label) + 4
        const lx2 = PAGE_W - MARGIN - doc.getTextWidth(String(page)) - 4
        if (lx2 > lx1) {
            let x = lx1
            while (x < lx2) { doc.circle(x, y - 1.5, 0.4, 'F'); x += 3 }
        }
        y += 12
    }
}

// ── section heading ───────────────────────────────────────────────────────────
function sectionHeading(doc, title, subtitle = null) {
    const y = 22
    doc.setFillColor(...C.accentLime)
    doc.rect(MARGIN, y - 5, 2, 9, 'F')
    setFont(doc, 16, 'bold', C.headingText)
    doc.text(title, MARGIN + 5, y)
    if (subtitle) {
        setFont(doc, 9, 'normal', C.mutedText)
        doc.text(subtitle, MARGIN + 5, y + 6)
        return y + 14
    }
    return y + 10
}

// ── sections ──────────────────────────────────────────────────────────────────
function buildOverview(doc, summary) {
    const startY = sectionHeading(doc, 'Overview', 'Consolidated scan summary')
    runTable(doc, startY,
        [['Metric', 'Count']],
        [
            ['Total Servers',    String(summary.totalServers)],
            ['Total Tools',      String(summary.totalTools)],
            ['Servers Scanned',  String(summary.cleanServers + summary.flaggedServers)],
            ['Clean Servers',    String(summary.cleanServers)],
            ['Flagged Servers',  String(summary.flaggedServers)],
            ['Total Findings',   String(summary.totalFindings)],
        ],
        { 0: { cellWidth: 120 }, 1: { cellWidth: CONTENT - 120, halign: 'right' } }
    )
}

function buildAgents(doc, agents) {
    const startY = sectionHeading(doc, 'AI Agents', 'MCP clients detected')
    runTable(doc, startY,
        [['Agent', 'Servers', 'Tools']],
        agents.map(a => [a.agent, String(a.serverCount), String(a.toolCount)]),
        {
            0: { cellWidth: 110 },
            1: { cellWidth: 40, halign: 'right' },
            2: { cellWidth: 40, halign: 'right' },
        }
    )
}

// Servers & tools. Each server heading carries its agent ("Gemini:postman-
// mcp-server") so no separate per-agent section banner is needed, and each
// tool name carries its server ("postman-mcp-server:createCollection") so
// the table needs no separate Server column. Hairline borders, no fill —
// keeps the grid without the byte cost of alternating row shading.
const BOTTOM_LIMIT = PAGE_H - 20
const LINE_H = 3.6

function buildServersAndTools(doc, servers, pageRef) {
    doc.addPage()
    pageRef['Servers & Tools'] = doc.internal.getCurrentPageInfo().pageNumber
    let y = sectionHeading(doc, 'Servers & Tools', 'Tool names, descriptions, and connection details')

    const groups = groupServers(servers)

    function ensureSpace(needed) {
        if (y + needed > BOTTOM_LIMIT) {
            doc.addPage()
            y = MARGIN + 8
        }
    }

    for (const group of groups) {
        for (const s of group.servers) {
            ensureSpace(14)
            setFont(doc, 10, 'bold', C.headingText)
            doc.text(`${group.key}:${s.name}`, MARGIN, y)
            y += 4.5

            const metaText = [s.transport, s.package, serverCommandLine(s)]
                .filter(Boolean)
                .join('   ·   ')
            if (metaText) {
                setFont(doc, 7.5, 'normal', C.mutedText)
                const lines = doc.splitTextToSize(metaText, CONTENT)
                ensureSpace(lines.length * LINE_H + 2)
                lines.forEach((line, i) => doc.text(line, MARGIN, y + i * LINE_H))
                y += lines.length * LINE_H + 3
            }

            if (!s.tools.length) {
                setFont(doc, 8, 'normal', C.mutedText)
                doc.text('No tools discovered.', MARGIN, y)
                y += 8
                continue
            }

            ensureSpace(12)
            autoTable(doc, {
                startY: y,
                body: s.tools.map(t => [`${s.name}:${t.name}`, t.description || '—']),
                margin: { left: MARGIN, right: MARGIN },
                styles: tableStyle({ lineWidth: 0.05 }),
                columnStyles: { 0: { cellWidth: 62, fontStyle: 'bold' }, 1: { cellWidth: CONTENT - 62 } },
                theme: 'grid',
            })
            y = doc.lastAutoTable.finalY + 8
        }
    }
}

// Security findings — server + only tools with findings + severity/analyzer/summary
function buildSecuritySection(doc, servers) {
    const startY = sectionHeading(doc, 'Security Findings', 'Servers and tools with detected issues')

    const flagged = servers.filter(s => s.findings.length > 0)
    if (!flagged.length) {
        setFont(doc, 9, 'normal', C.mutedText)
        doc.text('No security findings detected across all scanned servers.', MARGIN, startY + 6)
        return
    }

    const rows = []
    for (const s of flagged) {
        for (const f of s.findings) {
            rows.push({ data: [s.name, f.tool_name || '—', f.severity || '—', f.analyzer || '—', f.summary || '—'], sev: f.severity })
        }
    }

    autoTable(doc, {
        startY,
        head: [['Server', 'Tool', 'Severity', 'Analyzer', 'Summary']],
        body: rows.map(r => r.data),
        margin: { left: MARGIN, right: MARGIN },
        styles: tableStyle({ overflow: 'linebreak' }),
        headStyles: headStyle(),
        alternateRowStyles: { fillColor: [...C.tableRowAlt] },
        columnStyles: {
            0: { cellWidth: 36 },
            1: { cellWidth: 36 },
            2: { cellWidth: 22 },
            3: { cellWidth: 28 },
            4: { cellWidth: CONTENT - 122 },
        },
        didParseCell(data) {
            if (data.section === 'body' && data.column.index === 2) {
                const sev = rows[data.row.index]?.sev
                data.cell.styles.textColor = sevColor(sev)
                data.cell.styles.fontStyle = 'bold'
            }
        },
        theme: 'grid',
    })
}

// ── public interface ──────────────────────────────────────────────────────────
export class PdfGenerator {
    generate(data, options = {}) {
        const { includeSecurity = false, scopeLabel = 'all' } = options
        const { meta, summary, agents, servers } = data
        const scopeTitle = scopeLabel === 'all' ? 'All Servers' : scopeLabel
        const dateStr = fmtDateTime(meta.generatedAt)

        const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4', compress: true })
        const pageRef = {}

        // Page 1 — cover
        buildCover(doc, meta, scopeTitle)

        // Page 2 — TOC placeholder
        doc.addPage()
        const tocPage = doc.internal.getCurrentPageInfo().pageNumber

        // Overview
        doc.addPage()
        pageRef['Overview'] = doc.internal.getCurrentPageInfo().pageNumber
        buildOverview(doc, summary)

        // Agents
        doc.addPage()
        pageRef['AI Agents'] = doc.internal.getCurrentPageInfo().pageNumber
        buildAgents(doc, agents)

        // Servers & Tools (sectioned per agent when more than one is present)
        buildServersAndTools(doc, servers, pageRef)

        // Security (optional)
        if (includeSecurity) {
            doc.addPage()
            pageRef['Security Findings'] = doc.internal.getCurrentPageInfo().pageNumber
            buildSecuritySection(doc, servers)
        }

        // Fill in TOC now that all page numbers are known
        doc.setPage(tocPage)
        buildTOC(doc, pageRef)

        // Footers on every page except cover
        addFooters(doc, dateStr, doc.internal.getNumberOfPages())

        doc.save(`tooldex-report-${scopeLabel}-${new Date().toISOString().slice(0, 10)}.pdf`)
    }
}
