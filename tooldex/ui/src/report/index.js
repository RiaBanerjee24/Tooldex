// report/index.js
// Public API for the report system.
//
// To add a new format (e.g. docx, xlsx):
//   1. Create src/report/formats/docx.js exporting a DocxGenerator class
//   2. Add an entry to GENERATORS below
//   3. No other files need to change.

import { PdfGenerator }      from './formats/pdf.js'
import { MarkdownGenerator } from './formats/markdown.js'

const GENERATORS = {
    pdf:      new PdfGenerator(),
    markdown: new MarkdownGenerator(),
}

export const SUPPORTED_FORMATS = Object.keys(GENERATORS)

/**
 * Generate and download a report in the given format.
 * @param {ReportData} data    — from buildReportData()
 * @param {'pdf'|'markdown'} format
 * @param {{ includeSecurity?: boolean, scopeLabel?: string }} options
 */
export function generateReport(data, format, options = {}) {
    const generator = GENERATORS[format]
    if (!generator) throw new Error(`Unsupported report format: "${format}"`)
    generator.generate(data, options)
}
