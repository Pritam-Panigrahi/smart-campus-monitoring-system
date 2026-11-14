import { apiUrl } from './config'

async function request(path, options = {}) {
  const response = await fetch(apiUrl(path), options)
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`
    try { const body = await response.json(); detail = typeof body.detail === 'string' ? body.detail : body.detail?.message || detail } catch { /* Keep the safe fallback. */ }
    throw new Error(detail)
  }
  return response
}

export async function fetchSimulationStatus(signal) { return (await request('/api/simulation/status', { signal })).json() }
export async function updateSimulation(action) { return (await request(`/api/simulation/${action}`, { method: 'POST' })).json() }
export async function updateSimulationMode(mode) { return (await request('/api/simulation/mode', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode }) })).json() }
export async function previewCsv(module, file) { const form = new FormData(); form.append('file', file); return (await request(`/api/data-management/preview/${module}`, { method: 'POST', body: form })).json() }
export async function importCsv(module, mode, file) { const form = new FormData(); form.append('file', file); return (await request(`/api/data-management/import/${module}?mode=${mode}`, { method: 'POST', body: form })).json() }
const storedDataFilterKeys = ['device_id', 'start_date', 'end_date', 'source']
function storedDataFilterQuery(filters = {}) { const query = new URLSearchParams(); for (const key of storedDataFilterKeys) if (filters[key]) query.set(key, filters[key]); return query }
export async function fetchStoredReadings(module, filters = {}, signal) { const query = storedDataFilterQuery(filters); query.set('page', String(filters.page || 1)); query.set('page_size', String(filters.pageSize || 20)); return (await request(`/api/data-management/stored/${module}?${query}`, { signal })).json() }
export async function exportReadings(module, filters = {}) { return request(`/api/data-management/export/${module}?${storedDataFilterQuery(filters)}`) }
export async function resetReadings() { return (await request('/api/data-management/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirm: true }) })).json() }
