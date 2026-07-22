// Tooldex logo — single source of truth for all logo usage.
// Refactor: Topbar and report generators both import from here.

export const LOGO_URL = '/tooldex.svg'

// Raw SVG string for contexts that need inline SVG (e.g. email templates).
export const LOGO_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <polygon points="32,6 18,31 46,31" fill="#5d6b15"/>
  <polygon points="4,56 18,31 32,56" fill="#8a9a28"/>
  <polygon points="60,56 46,31 32,56" fill="#b4c44a"/>
  <polygon points="18,31 46,31 32,56" fill="#dfe8a8"/>
</svg>`

// Logo polygon data for PDF rendering via jsPDF drawing primitives.
// Coordinates are in the SVG's native 64×64 viewBox space.
// Each entry: { points: [[x,y],...], fill: hex }
export const LOGO_POLYGONS = [
    { points: [[32, 6], [18, 31], [46, 31]],          fill: '#5d6b15' },
    { points: [[4, 56], [18, 31], [32, 56]],           fill: '#8a9a28' },
    { points: [[60, 56], [46, 31], [32, 56]],          fill: '#b4c44a' },
    { points: [[18, 31], [46, 31], [32, 56]],          fill: '#dfe8a8' },
]
