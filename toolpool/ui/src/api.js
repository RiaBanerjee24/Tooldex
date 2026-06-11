/**
 * api.js — all fetch calls to the Toolpool backend in one place.
 * Base URL is empty — works both in dev (Vite proxies /api → :8282)
 * and in production (FastAPI serves everything on same port).
 */

const BASE = ""

async function get(path) {
    const res = await fetch(`${BASE}${path}`)
    if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`)
    return res.json()
}

export const api = {
    health: () => get("/api/health"),
    agents: () => get("/api/agents"),
    agent: (id) => get(`/api/agents/${id}`),
    servers: () => get("/api/servers"),
    server: (id) => get(`/api/servers/${id}`),
    matrix: () => get("/api/policy/matrix"),
    engines: () => get("/api/policy/engines"),
    engineRaw: (id) => get(`/api/policy/engines/${id}/raw`),
}