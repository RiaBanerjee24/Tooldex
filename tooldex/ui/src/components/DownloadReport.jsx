import { useState, useRef, useEffect } from 'react'
import { api } from '../api.js'

const FORMATS = [
    { key: 'pdf-summary', label: 'Summary PDF',  ext: '.pdf', hint: 'servers · tool names · severity' },
    { key: 'pdf-full',    label: 'Full PDF',      ext: '.pdf', hint: 'descriptions · inline findings'  },
    { key: 'markdown',    label: 'Markdown',      ext: '.md',  hint: 'full report as .md'              },
]

export function DownloadReport({ servers, scannedAt }) {
    const [open, setOpen]       = useState(false)
    const [status, setStatus]   = useState('idle') // idle | loading | done | error
    const [errMsg, setErrMsg]   = useState(null)
    const ref = useRef(null)

    useEffect(() => {
        if (!open) return
        function onClickOutside(e) {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false)
        }
        document.addEventListener('mousedown', onClickOutside)
        return () => document.removeEventListener('mousedown', onClickOutside)
    }, [open])

    async function handleDownload(format) {
        setOpen(false)
        setStatus('loading')
        setErrMsg(null)
        try {
            const [details, { buildReportData }, { generateReport }] = await Promise.all([
                Promise.all((servers || []).map(s => api.server(s.id))),
                import('../report/builder.js'),
                import('../report/index.js'),
            ])
            const reportData = buildReportData(servers || [], details, scannedAt)
            generateReport(reportData, format)
            setStatus('done')
            setTimeout(() => setStatus('idle'), 2500)
        } catch (err) {
            setErrMsg(err.message)
            setStatus('error')
            setTimeout(() => setStatus('idle'), 3000)
        }
    }

    const isLoading = status === 'loading'
    const label = status === 'loading' ? 'Building report…'
        : status === 'done'    ? 'Downloaded ✓'
        : status === 'error'   ? (errMsg || 'Failed')
        : 'Download Report'

    const btnColor = status === 'done'  ? 'var(--lime)'
        : status === 'error' ? 'var(--red)'
        : 'var(--text2)'

    return (
        <div style={{ display: 'flex', justifyContent: 'center', margin: '4px 0 20px' }}>
            <div ref={ref} style={{ position: 'relative' }}>
                <button
                    onClick={() => !isLoading && setOpen(o => !o)}
                    style={{
                        display: 'flex', alignItems: 'center', gap: 7,
                        padding: '7px 18px',
                        background: 'var(--surface2)',
                        border: `1px solid ${open ? 'var(--border3)' : 'var(--border)'}`,
                        borderRadius: 'var(--radius)',
                        cursor: isLoading ? 'default' : 'pointer',
                        fontSize: 11, fontFamily: 'Menlo, Consolas, monospace',
                        color: btnColor,
                        letterSpacing: '0.04em',
                        transition: 'color 0.2s, border-color 0.2s',
                        opacity: isLoading ? 0.7 : 1,
                    }}
                >
                    {/* download arrow icon */}
                    {!isLoading && status === 'idle' && (
                        <svg width="11" height="11" viewBox="0 0 12 12" fill="none" style={{ flexShrink: 0 }}>
                            <path d="M6 1v7M3 6l3 3 3-3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                            <path d="M1 10h10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
                        </svg>
                    )}
                    {isLoading && (
                        <svg width="11" height="11" viewBox="0 0 12 12" fill="none" style={{ flexShrink: 0, animation: 'spin 1s linear infinite' }}>
                            <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.4" strokeDasharray="14 8" strokeLinecap="round"/>
                        </svg>
                    )}
                    {label}
                    {!isLoading && status === 'idle' && (
                        <span style={{ fontSize: 8, opacity: 0.5 }}>{open ? '▲' : '▼'}</span>
                    )}
                </button>

                {open && (
                    <div style={{
                        position: 'absolute', top: 'calc(100% + 5px)',
                        left: '50%', transform: 'translateX(-50%)',
                        background: 'var(--surface2)',
                        border: '1px solid var(--border3)',
                        borderRadius: 'var(--radius-lg)',
                        padding: '6px 0',
                        minWidth: 160,
                        boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                        zIndex: 200,
                    }}>
                        {FORMATS.map(f => (
                            <button
                                key={f.key}
                                onClick={() => handleDownload(f.key)}
                                style={{
                                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                    width: '100%', padding: '8px 16px',
                                    background: 'none', border: 'none',
                                    cursor: 'pointer', textAlign: 'left',
                                    fontFamily: 'Menlo, Consolas, monospace',
                                    gap: 12,
                                }}
                                onMouseEnter={e => e.currentTarget.style.background = 'var(--surface3)'}
                                onMouseLeave={e => e.currentTarget.style.background = 'none'}
                            >
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 2, alignItems: 'flex-start' }}>
                                    <span style={{ fontSize: 11, color: 'var(--text2)' }}>{f.label}</span>
                                    <span style={{ fontSize: 9, color: 'var(--text3)' }}>{f.hint}</span>
                                </div>
                                <span style={{ fontSize: 9, color: 'var(--text3)', flexShrink: 0 }}>{f.ext}</span>
                            </button>
                        ))}
                    </div>
                )}
            </div>

            <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
        </div>
    )
}
