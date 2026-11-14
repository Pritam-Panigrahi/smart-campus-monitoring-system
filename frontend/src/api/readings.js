import { apiUrl } from './config'

const modules = {
  water_tanks: { path: 'water-tanks', valueKey: 'water_percentage', label: 'Water Tank', unit: '%' },
  waste_bins: { path: 'waste-bins', valueKey: 'fill_percentage', label: 'Waste Bin', unit: '%' },
  aqi_stations: { path: 'aqi-stations', valueKey: 'current_aqi', label: 'AQI', unit: 'AQI' },
}

export { modules }

export async function fetchDeviceReadings(moduleKey, deviceId, { startDate, endDate, limit = 100, signal } = {}) {
  const module = modules[moduleKey]
  const params = new URLSearchParams({ limit: String(limit) })
  if (startDate) params.set('start_date', startDate.toISOString())
  if (endDate) params.set('end_date', endDate.toISOString())
  const response = await fetch(apiUrl(`/api/${module.path}/${encodeURIComponent(deviceId)}/readings?${params}`), { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`${module.label} history request failed (${response.status}).`)
  return response.json()
}

export async function fetchSimulationStatus(signal) {
  const response = await fetch(apiUrl('/api/simulation/status'), { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`Simulation status request failed (${response.status}).`)
  return response.json()
}
