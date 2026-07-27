// Reusable SVG icon components.
// All icons accept `size` (default 14) and `color` (default "currentColor").

export function SecurityWarningIcon({ size = 14, color = "currentColor" }) {
    return (
        <svg
            width={size} height={size}
            viewBox="0 0 16 16"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            style={{ flexShrink: 0, display: "block" }}

        >
            {/* filled triangle */}
            <path
                d="M7.13 2.47a1 1 0 0 1 1.74 0l5.93 10.28A1 1 0 0 1 13.93 14H2.07a1 1 0 0 1-.87-1.25z"
                fill={color}
                opacity="0.18"
            />
            <path
                d="M7.13 2.47a1 1 0 0 1 1.74 0l5.93 10.28A1 1 0 0 1 13.93 14H2.07a1 1 0 0 1-.87-1.25z"
                stroke={color}
                strokeWidth="1.25"
                strokeLinejoin="round"
            />
            {/* exclamation stem */}
            <line x1="8" y1="6.5" x2="8" y2="10" stroke={color} strokeWidth="1.4" strokeLinecap="round" />
            {/* exclamation dot */}
            <circle cx="8" cy="12" r="0.85" fill={color} />
        </svg>
    )
}

export function SecurityCleanIcon({ size = 14, color = "currentColor" }) {
    return (
        <svg
            width={size} height={size}
            viewBox="0 0 16 16"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            style={{ flexShrink: 0, display: "block" }}
        >
            <circle cx="8" cy="8" r="6.5" stroke={color} strokeWidth="1.25" opacity="0.35" />
            <path
                d="M5.5 8.25l1.75 1.75 3.25-3.5"
                stroke={color}
                strokeWidth="1.4"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    )
}
