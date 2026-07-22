export const ACCESS = {
    allowed: { bg: "var(--lime-bg)", border: "var(--lime-border)", color: "var(--lime)", symbol: "✓", label: "Allowed" },
    denied: { bg: "var(--red-bg)", border: "var(--red-border)", color: "var(--red)", symbol: "✕", label: "Denied" },
    partial: { bg: "var(--orange-bg)", border: "var(--orange-border)", color: "var(--orange)", symbol: "◐", label: "Partial" },
    not_configured: { bg: "transparent", border: "transparent", color: "var(--text3)", symbol: "—", label: "—" },
    unknown: { bg: "var(--grey-bg)", border: "var(--grey-border)", color: "var(--grey)", symbol: "?", label: "Unknown" },
}

export const RISK = {
    low: { bg: "var(--lime-bg)", border: "var(--lime-border)", color: "var(--lime)" },
    medium: { bg: "var(--orange-bg)", border: "var(--orange-border)", color: "var(--orange)" },
    high: { bg: "var(--red-bg)", border: "var(--red-border)", color: "var(--red)" },
    critical: { bg: "var(--purple-bg)", border: "var(--purple-border)", color: "var(--purple)" },
}