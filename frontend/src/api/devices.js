import { apiUrl } from './config'

export async function fetchWaterTanks(signal) {
  const response = await fetch(apiUrl('/api/water-tanks'), { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`Water tank request failed (${response.status}).`)
  return response.json()
}

export async function fetchWasteBins(signal) {
  const response = await fetch(apiUrl('/api/waste-bins'), { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`Waste bin request failed (${response.status}).`)
  return response.json()
}

export async function fetchAQIStations(signal) {
  const response = await fetch(apiUrl('/api/aqi-stations'), { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`AQI station request failed (${response.status}).`)
  return response.json()
}

const devicePaths = { water_tanks: 'water-tanks', waste_bins: 'waste-bins', aqi_stations: 'aqi-stations' }
async function deviceRequest(path, options = {}) { const response = await fetch(apiUrl(path), { ...options, headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}) } }); if (!response.ok) { let detail = `Device request failed (${response.status}).`; try { detail = (await response.json()).detail || detail } catch { /* Use the safe fallback. */ } throw new Error(typeof detail === 'string' ? detail : 'Device request failed.'); } return response.json() }
export function createDevice(module, payload) { return deviceRequest(`/api/${devicePaths[module]}`, { method: 'POST', body: JSON.stringify(payload) }) }
export function updateDevice(module, deviceId, payload) { return deviceRequest(`/api/${devicePaths[module]}/${encodeURIComponent(deviceId)}`, { method: 'PUT', body: JSON.stringify(payload) }) }
export function updateDeviceStatus(module, deviceId, is_active) { return deviceRequest(`/api/${devicePaths[module]}/${encodeURIComponent(deviceId)}/status`, { method: 'PATCH', body: JSON.stringify({ is_active }) }) }
