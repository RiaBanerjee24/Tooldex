import { useState, useRef, useEffect } from 'react'
import { groupServers } from './servers/serverHelpers.jsx'

export function DownloadReport({ servers, scannedAt }) {
    const [open, setOpen]                 = useState(false)
    const [status, setStatus]             = useState('idle') // idle | loading | done | error
    const [errMsg, setErrMsg]             = useState(null)
    const [allChecked, setAllChecked]     = useState(true)
    const [checkedGroups, setCheckedGroups] = useState(new Set())
    const [includeSecurity, setIncludeSecurity] = useState(false)
    const ref = useRef(null)

    useEffect(() => {
        if (!open) return
        function onClickOutside(e) {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false)
        }
        document.addEventListener('mousedown', onClickOutside)
        return () => document.removeEventListener('mousedown', onClickOutside)
    }, [open])

    const groups = groupServers(servers || [])

    function toggleAll() {
        setAllChecked(true)
        setCheckedGroups(new Set())
    }

    function toggleGroup(key) {
        setAllChecked(false)
        setCheckedGroups(prev => {
            const next = new Set(prev)
            next.has(key) ? next.delete(key) : next.add(key)
            return next
        })
    }

    const scopedServers = allChecked
        ? (servers || [])
        : groups.filter(g => checkedGroups.has(g.key)).flatMap(g => g.servers)

    const scopeLabel = allChecked
        ? 'All'
        : groups.filter(g => checkedGroups.has(g.key)).map(g => g.key).join('+') || 'none'

    const canDownload = (allChecked || checkedGroups.size > 0) && scopedServers.length > 0

    async function handleDownload(format) {
        if (!canDownload) return
        setOpen(false)
        setStatus('loading')
        setErrMsg(null)
        try {
            const { downloadReport } = await import('../report/download.js')
            await downloadReport(scopedServers, scannedAt, format, { includeSecurity, scopeLabel })
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

    const checkboxRow = {
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 10, padding: '6px 16px', cursor: 'pointer', userSelect: 'none',
    }
    const checkboxLabel = {
        display: 'flex', alignItems: 'center', gap: 8,
        fontSize: 11, color: 'var(--text2)', fontFamily: 'Menlo, Consolas, monospace',
    }
    const checkboxInput = { accentColor: 'var(--lime)', width: 12, height: 12, cursor: 'pointer', flexShrink: 0 }
    const sectionLabel = {
        padding: '8px 16px 4px', fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
        textTransform: 'uppercase', color: 'var(--text3)', fontFamily: 'Menlo, Consolas, monospace',
    }

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
                        minWidth: 250,
                        boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                        zIndex: 200,
                    }}>
                        <div style={sectionLabel}>Scope</div>
                        <label style={checkboxRow}>
                            <span style={checkboxLabel}>
                                <input type="checkbox" checked={allChecked} onChange={toggleAll} style={checkboxInput} />
                                All servers
                            </span>
                            <span style={{ fontSize: 9, color: 'var(--text3)' }}>{(servers || []).length}</span>
                        </label>
                        {groups.map(g => (
                            <label key={g.key} style={checkboxRow}>
                                <span style={checkboxLabel}>
                                    <input
                                        type="checkbox"
                                        checked={!allChecked && checkedGroups.has(g.key)}
                                        onChange={() => toggleGroup(g.key)}
                                        style={checkboxInput}
                                    />
                                    {g.key}
                                </span>
                                <span style={{ fontSize: 9, color: 'var(--text3)' }}>{g.servers.length}</span>
                            </label>
                        ))}

                        <div style={{ borderTop: '1px solid var(--border)', margin: '6px 0' }} />

                        <label style={checkboxRow}>
                            <span style={checkboxLabel}>
                                <input
                                    type="checkbox"
                                    checked={includeSecurity}
                                    onChange={() => setIncludeSecurity(v => !v)}
                                    style={checkboxInput}
                                />
                                Include security scan
                            </span>
                        </label>

                        <div style={{ borderTop: '1px solid var(--border)', margin: '6px 0' }} />

                        <div style={{ display: 'flex', gap: 6, padding: '4px 16px 2px' }}>
                            <button
                                onClick={() => handleDownload('pdf')}
                                disabled={!canDownload}
                                style={{
                                    flex: 1, padding: '7px 0', background: 'var(--surface3)',
                                    border: '1px solid var(--border2)', borderRadius: 'var(--radius)',
                                    cursor: canDownload ? 'pointer' : 'default', opacity: canDownload ? 1 : 0.4,
                                    fontSize: 10, color: 'var(--cream)', fontFamily: 'Menlo, Consolas, monospace',
                                }}
                            >
                                PDF
                            </button>
                            <button
                                onClick={() => handleDownload('markdown')}
                                disabled={!canDownload}
                                style={{
                                    flex: 1, padding: '7px 0', background: 'var(--surface3)',
                                    border: '1px solid var(--border2)', borderRadius: 'var(--radius)',
                                    cursor: canDownload ? 'pointer' : 'default', opacity: canDownload ? 1 : 0.4,
                                    fontSize: 10, color: 'var(--cream)', fontFamily: 'Menlo, Consolas, monospace',
                                }}
                            >
                                Markdown
                            </button>
                        </div>
                    </div>
                )}
            </div>

            <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
        </div>
    )
}
