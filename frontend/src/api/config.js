const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || 'http://localhost:8000'
const relativeApiBaseUrl = configuredApiBaseUrl.startsWith('/')
export const API_BASE_URL = configuredApiBaseUrl.replace(/\/+$/, '') || (relativeApiBaseUrl ? '/' : 'http://localhost:8000')
export const apiUrl = (path) => relativeApiBaseUrl ? `${API_BASE_URL === '/' ? '' : API_BASE_URL}${path}` : new URL(path, `${API_BASE_URL}/`).toString()
function deriveSocketUrl() { const url = new URL(API_BASE_URL, window.location.origin); url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'; url.pathname = `${API_BASE_URL === '/' ? '' : API_BASE_URL}/ws/monitoring`; url.search = ''; url.hash = ''; return url.toString() }
export const MONITORING_WEBSOCKET_URL = import.meta.env.VITE_MONITORING_WEBSOCKET_URL?.trim() || deriveSocketUrl()
