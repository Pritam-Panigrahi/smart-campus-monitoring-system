import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Download, FileSpreadsheet, Play, RefreshCw, RotateCcw, Square, Upload } from 'lucide-react'
import { exportReadings, fetchSimulationStatus, fetchStoredReadings, importCsv, previewCsv, resetReadings, updateSimulation, updateSimulationMode } from '../api/dataManagement'
import { modules } from '../api/readings'
import { useMonitoring } from '../context/MonitoringContext'
import { formatTime, statusLevel } from '../lib/dashboardData'
import './DataManagementPage.css'

const moduleOptions = [{ key: 'water_tanks', label: 'Water Tanks' }, { key: 'waste_bins', label: 'Waste Bins' }, { key: 'aqi_stations', label: 'AQI Stations' }]
const sources = ['', 'CSV_UPLOAD', 'SENSOR', 'SIMULATED']
const storedPageSize = 8
// datetime-local values deliberately have no timezone.  Convert them from the
// browser's local timezone to UTC before sending them to the API.  An end value
// selected to minute precision represents the whole selected minute, so a
// reading at (for example) 15:31:42 is not accidentally excluded.
function toApiDate(value, isEnd = false) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  if (isEnd && !/T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value)) date.setSeconds(59, 999)
  return date.toISOString()
}
function storedDataFilters(filters) {
  return { device_id: filters.device_id, start_date: toApiDate(filters.start_date), end_date: toApiDate(filters.end_date, true), source: filters.source }
}
function exportFilename(response, module) {
  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="?([^";]+)"?/i)
  return match?.[1] || `${module}-readings.csv`
}
function readingStatus(module, value) { if (module === 'water_tanks') return value >= 50 ? 'Normal' : value >= 25 ? 'Attention' : 'Critical'; if (module === 'waste_bins') return value <= 25 ? 'Normal' : value <= 80 ? 'Attention' : 'Critical'; return value <= 100 ? 'Normal' : value <= 200 ? 'Attention' : 'Critical' }
function ModuleSelect({ value, onChange, label = 'Module' }) { return <label className="dm-field">{label}<select value={value} onChange={(event) => onChange(event.target.value)}>{moduleOptions.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}</select>
</label> }

export function DataManagementPage() {
  const { latestReadingEvent, dashboardUpdateCount } = useMonitoring()
  const [simulation, setSimulation] = useState(null); const [simulationError, setSimulationError] = useState(''); const [simulationBusy, setSimulationBusy] = useState(false)
  const [uploadModule, setUploadModule] = useState('water_tanks'); const [uploadFile, setUploadFile] = useState(null); const [preview, setPreview] = useState(null); const [uploadBusy, setUploadBusy] = useState(false); const [uploadError, setUploadError] = useState(''); const [uploadSuccess, setUploadSuccess] = useState(''); const [mode, setMode] = useState('ADD'); const [importConfirmed, setImportConfirmed] = useState(false)
  const [storedModule, setStoredModule] = useState('water_tanks'); const [filters, setFilters] = useState({ device_id: '', start_date: '', end_date: '', source: '', page: 1 }); const [stored, setStored] = useState(null); const [storedLoading, setStoredLoading] = useState(true); const [storedError, setStoredError] = useState(''); const [autoRefresh, setAutoRefresh] = useState(true); const [exportBusy, setExportBusy] = useState(false); const [exportMessage, setExportMessage] = useState(''); const [exportNoMatches, setExportNoMatches] = useState(false)
  const [resetBusy, setResetBusy] = useState(false); const [resetResult, setResetResult] = useState(null); const [resetError, setResetError] = useState('')

  const loadSimulation = useCallback(async () => { try { setSimulation(await fetchSimulationStatus()); setSimulationError('') } catch (error) { setSimulationError(error.message || 'Could not load simulation status.') } }, [])
  const loadStored = useCallback(async () => { setStoredLoading(true); try { const data = await fetchStoredReadings(storedModule, { ...filters, ...storedDataFilters(filters), pageSize: storedPageSize }); setStored(data); setStoredError('') } catch (error) { setStoredError(error.message || 'Could not load stored readings.') } finally { setStoredLoading(false) } }, [filters, storedModule])
  useEffect(() => { const timer = window.setTimeout(loadSimulation, 0); return () => window.clearTimeout(timer) }, [loadSimulation])
  useEffect(() => { const timer = window.setTimeout(loadStored, 0); return () => window.clearTimeout(timer) }, [loadStored])
  useEffect(() => { if (!autoRefresh) return undefined; const timer = window.setInterval(loadStored, 15000); return () => window.clearInterval(timer) }, [autoRefresh, loadStored])
  useEffect(() => { if (!autoRefresh || !latestReadingEvent) return undefined; const timer = window.setTimeout(loadStored, 0); return () => window.clearTimeout(timer) }, [autoRefresh, latestReadingEvent, loadStored])
  useEffect(() => { if (!dashboardUpdateCount) return undefined; const timer = window.setTimeout(loadSimulation, 0); return () => window.clearTimeout(timer) }, [dashboardUpdateCount, loadSimulation])

  const simulationAction = async (action) => { setSimulationBusy(true); setSimulationError(''); try { setSimulation(await updateSimulation(action)) } catch (error) { setSimulationError(error.message || 'Simulation request failed.') } finally { setSimulationBusy(false) } }
  const setSimulationMode = async (nextMode) => { setSimulationBusy(true); setSimulationError(''); try { setSimulation(await updateSimulationMode(nextMode)) } catch (error) { setSimulationError(error.message || 'Could not update simulation mode.') } finally { setSimulationBusy(false) } }
  const changeFile = (file) => { setUploadFile(file || null); setPreview(null); setUploadError(''); setUploadSuccess(''); setImportConfirmed(false) }
  const runPreview = async () => { if (!uploadFile) { setUploadError('Choose a CSV file before previewing.'); return } setUploadBusy(true); setUploadError(''); setUploadSuccess(''); try { setPreview(await previewCsv(uploadModule, uploadFile)) } catch (error) { setPreview(null); setUploadError(error.message || 'CSV preview failed.') } finally { setUploadBusy(false) } }
  const runImport = async () => { if (!preview || preview.invalid_rows) return; if (mode === 'REPLACE' && simulation?.running) { setUploadError('Stop simulation before a REPLACE import. Simulation will not be stopped automatically.'); return } if (!importConfirmed) { setUploadError('Confirm the import before continuing.'); return } if (!window.confirm(`${mode} ${preview.valid_rows} validated readings for ${modules[uploadModule].label}?`)) return; setUploadBusy(true); setUploadError(''); try { const result = await importCsv(uploadModule, mode, uploadFile); setUploadSuccess(`${result.imported_rows} readings imported successfully.`); setPreview(null); setImportConfirmed(false); await loadStored() } catch (error) { setUploadError(error.message || 'Import failed.') } finally { setUploadBusy(false) } }
  const reset = async () => { if (!window.confirm('Delete all historical readings? Devices, locations, settings, and configurations will remain.')) return; setResetBusy(true); setResetError(''); try { const result = await resetReadings(); setResetResult(result.deleted); await loadStored() } catch (error) { setResetError(error.message || 'Reset failed.') } finally { setResetBusy(false) } }
  const downloadExport = async (allModuleReadings = false) => { setExportBusy(true); setExportMessage(''); setExportNoMatches(false); try { const exportFilters = allModuleReadings ? {} : storedDataFilters(filters); const response = await exportReadings(storedModule, exportFilters); const recordCount = Number(response.headers.get('X-Export-Record-Count') || 0); if (response.status === 204 || recordCount === 0) { const hasFilters = Boolean(filters.device_id || filters.start_date || filters.end_date || filters.source); setExportMessage(allModuleReadings ? 'No readings are stored for this module; no CSV file was created.' : 'No readings match the current Stored Data filters; zero records were returned.'); setExportNoMatches(!allModuleReadings && hasFilters); return } if (!response.headers.get('Content-Type')?.toLowerCase().includes('text/csv')) throw new Error('Export returned an unexpected file type.')
    const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = exportFilename(response, storedModule); document.body.appendChild(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 0); setExportMessage(`CSV download started (${recordCount} records).`) } catch (error) { setExportMessage(error.message || 'Export failed.') } finally { setExportBusy(false) } }
  const valueLabel = modules[storedModule].valueKey; const storedRows = stored?.readings || []
  const previewRows = useMemo(() => preview?.preview || [], [preview])

  return <>
<section className="page-heading">
<h2>Data Management</h2>
<p>Control simulation and safely manage historical monitoring readings.</p>
</section>
<section className="dm-grid">
<section className="card dm-section">
<div className="dm-section-title">
<div>
<h3>Simulation Control</h3>
<p>Current collection remains separate from stored-data refresh.</p>
</div>
<span className={`status-badge ${simulation?.running ? 'normal' : 'unavailable'}`}>{simulation?.running ? 'Running' : 'Stopped'}</span>
</div>{simulationError && <p className="inline-error">{simulationError}</p>}<div className="dm-simulation-controls">
<label className="dm-field">Mode<select disabled={simulationBusy} value={simulation?.mode || 'DEMO'} onChange={(event) => setSimulationMode(event.target.value)}>
<option value="DEMO">Demo</option>
<option value="REAL_TIME">Real-time</option>
</select>
</label>
<div className="dm-actions">
<button className="button" type="button" disabled={simulationBusy || simulation?.running} onClick={() => simulationAction('start')}>
<Play size={15} /> Start Simulation</button>
<button className="button dm-stop" type="button" disabled={simulationBusy || !simulation?.running} onClick={() => simulationAction('stop')}>
<Square size={14} /> Stop Simulation</button>
</div>
</div>
<div className="dm-intervals">{moduleOptions.map(({ key, label }) => <span key={key}>
<strong>{label}</strong>{simulation?.modules?.[key] ? `${simulation.modules[key].interval_seconds >= 60 ? `${simulation.modules[key].interval_seconds / 60}m` : `${simulation.modules[key].interval_seconds}s`}` : '—'}</span>)}</div>
</section>
<section className="card dm-section">
<div className="dm-section-title">
<div>
<h3>CSV Data Upload</h3>
<p>Preview validates every row before any reading is written.</p>
</div>
</div>
<div className="dm-form-row">
<ModuleSelect value={uploadModule} onChange={(value) => { setUploadModule(value); setPreview(null); setImportConfirmed(false) }} />
<label className="dm-field">Import mode<select value={mode} onChange={(event) => { setMode(event.target.value); setImportConfirmed(false) }}>
<option value="ADD">ADD — append readings</option>
<option value="REPLACE">REPLACE — module only</option>
</select>
</label>
<label className="dm-file">
<FileSpreadsheet size={18} />
<span>{uploadFile?.name || 'Choose CSV file'}</span>
<input type="file" accept=".csv,text/csv" onChange={(event) => changeFile(event.target.files?.[0])} />
</label>
</div>{mode === 'REPLACE' && <p className="dm-warning">
<AlertTriangle size={16} /> REPLACE removes readings only for this module. {simulation?.running ? 'Stop the running simulation before importing.' : 'Simulation is stopped.'}</p>}<div className="dm-actions">
<button className="button" type="button" disabled={uploadBusy || !uploadFile} onClick={runPreview}>
<FileSpreadsheet size={15} /> {uploadBusy ? 'Working…' : 'Preview CSV'}</button>{preview && <>
<label className="dm-confirm">
<input type="checkbox" checked={importConfirmed} onChange={(event) => setImportConfirmed(event.target.checked)} /> I confirm this {mode} import.</label>
<button className="button" type="button" disabled={uploadBusy || preview.invalid_rows > 0 || !importConfirmed || (mode === 'REPLACE' && simulation?.running)} onClick={runImport}>
<Upload size={15} /> Import {preview.valid_rows} rows</button>
</>}</div>{uploadError && <p className="inline-error">{uploadError}</p>}{uploadSuccess && <p className="dm-success">{uploadSuccess}</p>}{preview && <div className="dm-preview">
<p>
<strong>{preview.total_rows}</strong> rows scanned · <strong className="dm-valid">{preview.valid_rows}</strong> valid · <strong className="dm-invalid">{preview.invalid_rows}</strong> invalid</p>{preview.errors?.length > 0 && <ul className="dm-errors">{preview.errors.map((item) => <li key={`${item.row}-${item.reason}`}>Row {item.row}: {item.reason}</li>)}</ul>}{previewRows.length > 0 && <div className="table-scroll">
<table>
<thead>
<tr>
<th>Device</th>
<th>Value</th>
<th>Timestamp</th>
</tr>
</thead>
<tbody>{previewRows.map((row, index) => <tr key={`${row.device_id}-${index}`}>
<td>{row.device_id}</td>
<td>{row[modules[uploadModule].valueKey]} {modules[uploadModule].unit}</td>
<td>{formatTime(row.recorded_at)}</td>
</tr>)}</tbody>
</table>
</div>}</div>}</section>
<section className="card dm-section dm-full">
<div className="dm-section-title">
<div>
<h3>Stored Data</h3>
<p>{stored?.total ?? 0} stored readings. Auto-refresh only changes this table display.</p>
</div>
<div className="dm-stored-actions"><label className="dm-toggle">
<input type="checkbox" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} /> Auto-refresh {autoRefresh ? 'ON' : 'OFF'}</label>
<button className="button" type="button" disabled={exportBusy} onClick={downloadExport}>
<Download size={15} /> {exportBusy ? 'Preparing…' : 'Export CSV'}</button>
</div>
</div>
<div className="dm-filter-row">
<ModuleSelect value={storedModule} onChange={(value) => { setStoredModule(value); setFilters((current) => ({ ...current, page: 1 })) }} />
<label className="dm-field">Device ID<input value={filters.device_id} onChange={(event) => setFilters((current) => ({ ...current, device_id: event.target.value, page: 1 }))} />
</label>
<label className="dm-field">Start date<input type="datetime-local" value={filters.start_date} onChange={(event) => setFilters((current) => ({ ...current, start_date: event.target.value, page: 1 }))} />
</label>
<label className="dm-field">End date<input type="datetime-local" value={filters.end_date} onChange={(event) => setFilters((current) => ({ ...current, end_date: event.target.value, page: 1 }))} />
</label>
<label className="dm-field">Source<select value={filters.source} onChange={(event) => setFilters((current) => ({ ...current, source: event.target.value, page: 1 }))}>{sources.map((source) => <option key={source} value={source}>{source || 'All sources'}</option>)}</select>
</label>
<button className="icon-button" type="button" onClick={loadStored} aria-label="Refresh stored data">
<RefreshCw size={17} />
</button>
</div>{exportMessage && <p className={exportMessage.includes('failed') ? 'inline-error' : 'dm-success'}>{exportMessage}</p>}{exportNoMatches && <button className="button" type="button" disabled={exportBusy} onClick={() => downloadExport(true)}>Export all module readings</button>}{storedError ? <p className="inline-error">{storedError}</p> : storedLoading ? <div className="panel-state">Loading stored readings…</div> : <>
<div className="table-scroll dm-stored-table-scroll" aria-label="Stored data readings">
<table>
<thead>
<tr>
<th>Device</th>
<th>Module</th>
<th>Reading</th>
<th>Status</th>
<th>Source</th>
<th>Recorded</th>
</tr>
</thead>
<tbody>{storedRows.map((row) => { const currentStatus = readingStatus(storedModule, row[valueLabel]); return <tr key={row.reading_id}>
<td>
<strong>{row.device_id}</strong>
<span>{row.device_name}</span>
</td>
<td>{modules[storedModule].label}</td>
<td>{row[valueLabel]} {modules[storedModule].unit}</td>
<td>
<span className={`status-badge ${statusLevel(currentStatus)}`}>{currentStatus}</span>
</td>
<td>{row.source}</td>
<td>{formatTime(row.recorded_at)}</td>
</tr> })}</tbody>
</table>
</div>{storedRows.length === 0 && <div className="panel-state">No readings match the selected filters.</div>}<div className="dm-pagination">
<button className="filter-button" disabled={(filters.page || 1) === 1} onClick={() => setFilters((current) => ({ ...current, page: current.page - 1 }))}>Previous</button>
<span>Page {filters.page} of {Math.max(1, Math.ceil((stored?.total || 0) / storedPageSize))}</span>
<button className="filter-button" disabled={(filters.page || 1) * storedPageSize >= (stored?.total || 0)} onClick={() => setFilters((current) => ({ ...current, page: current.page + 1 }))}>Next</button>
</div>
</>}</section>
<section className="card dm-section dm-reset">
<div className="dm-section-title">
<div>
<h3>Reset Data</h3>
<p>Delete historical readings only.</p>
</div>
</div>
<p className="dm-warning">
<AlertTriangle size={17} /> Resetting deletes historical readings from Water Tanks, Waste Bins, and AQI Stations. Device records, device locations, settings, and configurations remain unchanged.</p>
<button className="button dm-danger" type="button" disabled={resetBusy} onClick={reset}>
<RotateCcw size={15} /> {resetBusy ? 'Resetting…' : 'Reset all readings'}</button>{resetError && <p className="inline-error">{resetError}</p>}{resetResult && <p className="dm-success">Reset complete — Water: {resetResult.water_tanks}, Waste: {resetResult.waste_bins}, AQI: {resetResult.aqi_stations} deleted. Simulation was not restarted.</p>}</section>
</section>
</>
}
