// report/download.js
// Shared fetch-details → build → generate sequence, reused by the top-level
// and per-server download buttons.

import { api } from '../api.js'
import { buildReportData } from './builder.js'
import { generateReport } from './index.js'

function slugify(label) {
    return (label || 'report')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '') || 'report'
}

/**
 * Fetch full details for `servers`, build report data, and trigger a download.
 * @param {object[]} servers       — subset of api.servers().servers to include
 * @param {string|null} scannedAt
 * @param {'pdf'|'markdown'} format
 * @param {{ includeSecurity?: boolean, scopeLabel?: string }} options — scopeLabel is a human label (e.g. "All", "Claude", a server name)
 */
export async function downloadReport(servers, scannedAt, format, options = {}) {
    const { includeSecurity = false, scopeLabel = 'all' } = options
    const details = await Promise.all((servers || []).map(s => api.server(s.id)))
    const reportData = buildReportData(servers || [], details, scannedAt)
    generateReport(reportData, format, { includeSecurity, scopeLabel: slugify(scopeLabel) })
}
