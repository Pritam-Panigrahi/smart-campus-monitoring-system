import { modules } from '../api/readings'

export const moduleOrder = ['water_tanks', 'waste_bins', 'aqi_stations']
export const timeFilters = [{ key: '1h', label: 'Last 1 hour', hours: 1 }, { key: '24h', label: 'Last 24 hours', hours: 24 }, { key: '7d', label: 'Last 7 days', hours: 168 }]

export function statusLevel(status, hasReading = true) {
  if (!hasReading || status === 'No data' || status === 'Inactive') return 'unavailable'
  if (['Normal', 'Low', 'Good', 'Satisfactory'].includes(status)) return 'normal'
  if (['Attention', 'Medium', 'Almost Full', 'Moderate'].includes(status)) return 'attention'
  return 'critical'
}
export function deviceName(device, moduleKey) { return device.tank_name || device.bin_name || device.station_name || modules[moduleKey].label }
export function flattenDevices(summary) { return moduleOrder.flatMap((moduleKey) => (summary?.[moduleKey] || []).map((device) => ({ ...device, moduleKey, module: modules[moduleKey] }))) }
export function formatTime(value) { if (!value) return 'No reading'; const date = new Date(value); return Number.isNaN(date.getTime()) ? 'Unavailable' : date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) }
export function formatChartTime(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '' : date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
export function makeReading(moduleKey, device, reading) { const { valueKey, label, unit } = modules[moduleKey]; return { id: `${moduleKey}-${reading.reading_id}`, readingId: reading.reading_id, moduleKey, module: label, deviceId: device.device_id, deviceName: deviceName(device, moduleKey), location: device.location_name, value: reading[valueKey], unit, source: reading.source, recordedAt: reading.recorded_at, status: device.status } }
export function mergeReadings(current, incoming) { const indexed = new Map(current.map((item) => [item.id, item])); incoming.forEach((item) => indexed.set(item.id, item)); return [...indexed.values()].sort((left, right) => new Date(right.recordedAt) - new Date(left.recordedAt)) }
export function eventReading(event, devices) { const moduleKey = event.module; const device = devices.find((item) => item.moduleKey === moduleKey && item.device_id === event.device_id); if (!device || !modules[moduleKey]) return null; return { id: `${moduleKey}-${event.reading_id}`, readingId: event.reading_id, moduleKey, module: modules[moduleKey].label, deviceId: event.device_id, deviceName: deviceName(device, moduleKey), location: device.location_name, value: event.value, unit: modules[moduleKey].unit, source: event.source, recordedAt: event.recorded_at, status: event.status }
}
export function isAlert(device) { return device.latest_reading && statusLevel(device.status, true) === 'critical' }
