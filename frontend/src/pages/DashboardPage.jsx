import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchDashboardSummary } from '../api/dashboard'
import { fetchDeviceReadings, fetchSimulationStatus } from '../api/readings'
import { AlertsPanel, CampusStatus, DataHealth, RecentReadings } from '../components/dashboard/DashboardPanels'
import { TrendCharts } from '../components/dashboard/TrendCharts'
import { CampusLocationMap } from '../components/map/CampusLocationMap'
import { useMonitoring } from '../context/MonitoringContext'
import { eventReading, flattenDevices, makeReading, mergeReadings } from '../lib/dashboardData'
import './DashboardPage.css'

const metrics = [
  { key: 'total_water_tanks', active: 'active_water_tanks', label: 'Total Water Tanks' },
  { key: 'total_waste_bins', active: 'active_waste_bins', label: 'Total Waste Bins' },
  { key: 'total_aqi_stations', active: 'active_aqi_stations', label: 'Total AQI Stations' },
  { key: 'active_alert_count', label: 'Active Alerts' },
]

export function DashboardPage() {
  const { connectionStatus, dashboardUpdateCount, latestReadingEvent } = useMonitoring()
  const [summary, setSummary] = useState(null)
  const [summaryError, setSummaryError] = useState('')
  const [loading, setLoading] = useState(true)
  const [recentReadings, setRecentReadings] = useState([])
  const [recentState, setRecentState] = useState({ loading: true, error: '' })
  const [simulation, setSimulation] = useState(null)
  const [simulationError, setSimulationError] = useState('')

  const loadSummary = useCallback(async () => {
    setLoading(true)
    setSummaryError('')
    try { setSummary(await fetchDashboardSummary()) } catch (error) { setSummaryError(error.message || 'The dashboard could not be loaded.') } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchDashboardSummary().then((data) => { if (!cancelled) { setSummary(data); setSummaryError('') } }).catch((error) => { if (!cancelled) setSummaryError(error.message || 'The dashboard could not be loaded.') }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [dashboardUpdateCount])

  useEffect(() => {
    let cancelled = false
    fetchSimulationStatus().then((data) => { if (!cancelled) { setSimulation(data); setSimulationError('') } }).catch((error) => { if (!cancelled) setSimulationError(error.message || 'Could not load simulation status.') })
    return () => { cancelled = true }
  }, [dashboardUpdateCount])

  useEffect(() => {
    if (!summary) return undefined
    let cancelled = false
    const devices = flattenDevices(summary)
    Promise.all(devices.map(async (device) => ({ device, readings: await fetchDeviceReadings(device.moduleKey, device.device_id, { limit: 20 }) }))).then((groups) => {
      if (!cancelled) { setRecentReadings(mergeReadings([], groups.flatMap(({ device, readings }) => readings.map((reading) => makeReading(device.moduleKey, device, reading))))); setRecentState({ loading: false, error: '' }) }
    }).catch((error) => { if (!cancelled) setRecentState({ loading: false, error: error.message || 'Could not load recent readings.' }) })
    return () => { cancelled = true }
  }, [summary])

  const devices = useMemo(() => flattenDevices(summary), [summary])
  const displayedReadings = useMemo(() => {
    const liveReading = latestReadingEvent ? eventReading(latestReadingEvent, devices) : null
    return liveReading ? mergeReadings(recentReadings, [liveReading]) : recentReadings
  }, [devices, latestReadingEvent, recentReadings])

  if (loading && !summary) return <><section className="page-heading"><h2>Campus Overview</h2><p>Loading live campus monitoring data.</p></section><div className="card loading-state">Loading current campus summary…</div></>
  if (summaryError && !summary) return <><section className="page-heading"><h2>Campus Overview</h2><p>Live campus monitoring data.</p></section><div className="card error-state"><h3>Dashboard unavailable</h3><p>{summaryError} Check that the backend is running and the frontend API URL is configured correctly.</p><button className="button" type="button" onClick={loadSummary}>Try again</button></div></>

  return <><section className="page-heading"><h2>Campus Overview</h2><p>Live status for Gandhi Academy of Technology and Engineering.</p></section><section className="summary-grid">{metrics.map((metric) => <article className="card metric-card" key={metric.key}><p className="metric-label">{metric.label}</p><p className="metric-value">{summary?.[metric.key] ?? '—'}</p>{metric.active && <p className="metric-detail">{summary?.[metric.active] ?? 0} active devices</p>}</article>)}</section>{summaryError && <p className="inline-error">Could not refresh the latest summary: {summaryError}</p>}<CampusLocationMap /><CampusStatus summary={summary} /><AlertsPanel summary={summary} /><TrendCharts summary={summary} /><RecentReadings readings={displayedReadings} loading={recentState.loading} error={recentState.error} /><DataHealth summary={summary} connectionStatus={connectionStatus} simulation={simulation} error={simulationError} /></>
}
