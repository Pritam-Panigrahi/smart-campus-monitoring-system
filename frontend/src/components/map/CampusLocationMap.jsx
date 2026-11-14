import { useCallback, useEffect, useMemo, useState } from 'react'
import L from 'leaflet'
import { MapContainer, Marker, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { AlertTriangle, Droplets, MapPin, Radio, Trash2, Wind, X } from 'lucide-react'
import { fetchAQIStations, fetchWasteBins, fetchWaterTanks } from '../../api/devices'
import { fetchDeviceReadings, modules } from '../../api/readings'
import { useMonitoring } from '../../context/MonitoringContext'
import { formatTime } from '../../lib/dashboardData'
import './CampusLocationMap.css'
import './CampusLocationMapOverrides.css'

const typeOptions = [{ key: 'all', label: 'All devices' }, { key: 'water_tanks', label: 'Water Tanks' }, { key: 'waste_bins', label: 'Waste Bins' }, { key: 'aqi_stations', label: 'AQI Stations' }]
const statusOptions = ['All statuses', 'Normal', 'Attention', 'Critical', 'Inactive', 'No reading']
const mapLayers = {
  street: {
    label: 'Street Map',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  },
  satellite: {
    label: 'Satellite View',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
  },
}
const typeMeta = {
  water_tanks: { label: 'Water Tank', color: '#2563eb', Icon: Droplets },
  waste_bins: { label: 'Waste Bin', color: '#ea580c', Icon: Trash2 },
  aqi_stations: { label: 'AQI Station', color: '#16a34a', Icon: Wind },
}

function deviceName(device) { return device.tank_name || device.bin_name || device.station_name || device.device_id }
function validCoordinates(device) { return Number.isFinite(Number(device.latitude)) && Number.isFinite(Number(device.longitude)) }
function displayStatus(device) {
  if (!device.is_active) return 'Inactive'
  const status = device.rawStatus
  if (!device.latestReading || status === 'No data' || status === 'No reading') return 'No reading'
  if (['Normal', 'Low', 'Good', 'Satisfactory'].includes(status)) return 'Normal'
  if (['Attention', 'Medium', 'Almost Full', 'Moderate'].includes(status)) return 'Attention'
  return 'Critical'
}
function markerIcon(device) {
  const meta = typeMeta[device.moduleKey]
  const status = displayStatus(device).toLowerCase().replace(' ', '-')
  const symbol = device.moduleKey === 'water_tanks' ? 'W' : device.moduleKey === 'waste_bins' ? 'B' : 'A'
  return L.divIcon({ className: 'campus-marker-wrapper', html: `<span class="campus-marker campus-marker--${status}" style="--type-color:${meta.color}" role="img" aria-label="${meta.label}, ${displayStatus(device)} status"><b>${symbol}</b></span>`, iconSize: [36, 36], iconAnchor: [18, 18] })
}
function FitBounds({ devices }) {
  const map = useMap()
  useEffect(() => {
    if (!devices.length) return
    const bounds = L.latLngBounds(devices.map((device) => [Number(device.latitude), Number(device.longitude)]))
    map.fitBounds(bounds, { padding: [35, 35], maxZoom: 17 })
  }, [devices, map])
  return null
}
function panelValue(device) { return device.latestReading ? `${device.latestReading.value}${device.unit === '%' ? '%' : ` ${device.unit}`}` : 'No reading' }

export function CampusLocationMap() {
  const { latestReadingEvent } = useMonitoring()
  const [devices, setDevices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('All statuses')
  const [mapLayer, setMapLayer] = useState('street')
  const [selectedId, setSelectedId] = useState(null)

  const loadDevices = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const inventory = await Promise.all([fetchWaterTanks(), fetchWasteBins(), fetchAQIStations()])
      const merged = inventory.flatMap((items, index) => {
        const moduleKey = ['water_tanks', 'waste_bins', 'aqi_stations'][index]
        const { valueKey, unit } = modules[moduleKey]
        return items.map((device) => ({ ...device, moduleKey, unit, latestReading: null, rawStatus: 'No data', valueKey }))
      })
      const withReadings = await Promise.all(merged.map(async (device) => {
        if (!device.is_active) return device
        const readings = await fetchDeviceReadings(device.moduleKey, device.device_id, { limit: 1 })
        const reading = readings[0]
        if (!reading) return device
        const value = reading[device.valueKey]
        const rawStatus = device.moduleKey === 'water_tanks' ? (value >= 50 ? 'Normal' : value >= 25 ? 'Attention' : value >= 10 ? 'Low' : 'Critical') : device.moduleKey === 'waste_bins' ? (value <= 25 ? 'Low' : value <= 50 ? 'Medium' : value <= 80 ? 'Almost Full' : 'Full') : (value <= 50 ? 'Good' : value <= 100 ? 'Satisfactory' : value <= 200 ? 'Moderate' : 'Poor')
        return { ...device, latestReading: { value, recordedAt: reading.recorded_at }, rawStatus }
      }))
      setDevices(withReadings)
    } catch (requestError) { setError(requestError.message || 'Could not load campus devices.') } finally { setLoading(false) }
  }, [])

  useEffect(() => { const timer = window.setTimeout(loadDevices, 0); return () => window.clearTimeout(timer) }, [loadDevices])
  useEffect(() => {
    if (!latestReadingEvent || !['WATER_TANK_READING', 'WASTE_BIN_READING', 'AQI_READING'].includes(latestReadingEvent.event)) return
    const timer = window.setTimeout(() => setDevices((current) => current.map((device) => {
      if (device.device_id !== latestReadingEvent.device_id || device.moduleKey !== latestReadingEvent.module) return device
      return { ...device, latestReading: { value: latestReadingEvent.value, recordedAt: latestReadingEvent.recorded_at }, rawStatus: latestReadingEvent.status }
    })), 0)
    return () => window.clearTimeout(timer)
  }, [latestReadingEvent])

  const coordinateDevices = useMemo(() => devices.filter(validCoordinates), [devices])
  const displayedDevices = useMemo(() => coordinateDevices.filter((device) => (typeFilter === 'all' || device.moduleKey === typeFilter) && (statusFilter === 'All statuses' || displayStatus(device) === statusFilter)), [coordinateDevices, statusFilter, typeFilter])
  const selectedDevice = devices.find((device) => device.device_id === selectedId) || null
  const activeCount = devices.filter((device) => device.is_active).length

  if (loading) return <section className="card campus-map-state">Loading campus device locations…</section>
  if (error) return <section className="card error-state"><h3>Campus map unavailable</h3><p>{error}</p><button className="button" type="button" onClick={loadDevices}>Try again</button></section>
  const activeLayer = mapLayers[mapLayer]
  return <section className="dashboard-section campus-map-section" aria-labelledby="campus-map-title"><div className="section-title"><div><h2 id="campus-map-title">Campus Location Map</h2><p>Live device locations for GATE, Golanthara.</p></div><span className="campus-map-count">{displayedDevices.length} shown</span></div><div className="card campus-map-card"><div className="campus-map-controls"><div className="campus-filter-group" role="group" aria-label="Device type filter">{typeOptions.map((option) => <button className={typeFilter === option.key ? 'filter-button active' : 'filter-button'} type="button" key={option.key} onClick={() => setTypeFilter(option.key)}>{option.label}</button>)}</div><div className="campus-map-selectors"><label className="campus-status-filter">Map layer <select value={mapLayer} onChange={(event) => setMapLayer(event.target.value)}>{Object.entries(mapLayers).map(([key, layer]) => <option key={key} value={key}>{layer.label}</option>)}</select></label><label className="campus-status-filter">Status <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>{statusOptions.map((status) => <option key={status}>{status}</option>)}</select></label></div></div><div className="campus-map-layout"><div className="campus-map-frame">{activeCount === 0 ? <div className="campus-map-empty"><Radio size={22} /> No active devices are available on the map.</div> : displayedDevices.length === 0 ? <div className="campus-map-empty">No mapped devices match these filters.</div> : <MapContainer center={[19.2267, 84.7507]} zoom={16} scrollWheelZoom className="campus-leaflet-map"><TileLayer key={mapLayer} attribution={activeLayer.attribution} url={activeLayer.url} /><FitBounds devices={displayedDevices} />{displayedDevices.map((device) => <Marker key={device.device_id} position={[Number(device.latitude), Number(device.longitude)]} icon={markerIcon(device)} eventHandlers={{ click: () => setSelectedId(device.device_id) }}><Tooltip direction="top" offset={[0, -16]}>{device.device_id} · {deviceName(device)}</Tooltip></Marker>)}</MapContainer>}</div>{selectedDevice && <DevicePanel device={selectedDevice} onClose={() => setSelectedId(null)} />}</div><MapLegend /></div></section>
}

function MapLegend() { return <div className="campus-map-legend" aria-label="Map legend"><span><i className="legend-type water" />Water Tanks</span><span><i className="legend-type waste" />Waste Bins</span><span><i className="legend-type aqi" />AQI Stations</span><span><i className="legend-status normal" />Normal</span><span><i className="legend-status attention" />Attention</span><span><i className="legend-status critical" />Critical</span><span><i className="legend-status inactive" />Inactive</span></div> }
function DevicePanel({ device, onClose }) { const meta = typeMeta[device.moduleKey]; const Icon = meta.Icon; const status = displayStatus(device); const hasAlert = status === 'Critical'; return <aside className="device-detail-panel" aria-label={`${deviceName(device)} details`}><button className="device-panel-close" type="button" onClick={onClose} aria-label="Close device details"><X size={18} /></button><div className="device-panel-heading"><span className="device-type-icon" style={{ '--type-color': meta.color }}><Icon size={19} /></span><div><p>{meta.label}</p><h3>{deviceName(device)}</h3><span>{device.device_id}</span></div></div><dl><div><dt><MapPin size={15} /> Location</dt><dd>{device.location_name}</dd></div><div><dt>Current reading</dt><dd>{panelValue(device)}</dd></div><div><dt>Status</dt><dd><span className={`map-status ${status.toLowerCase().replace(' ', '-')}`}>{status}</span></dd></div><div><dt>State</dt><dd>{device.is_active ? 'Active' : 'Inactive'}</dd></div><div><dt>Last updated</dt><dd>{formatTime(device.latestReading?.recordedAt)}</dd></div></dl>{hasAlert && <p className="device-alert"><AlertTriangle size={16} /> Active alert: critical reading requires attention.</p>}</aside> }
