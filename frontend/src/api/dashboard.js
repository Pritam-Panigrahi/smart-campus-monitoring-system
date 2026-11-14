import { apiUrl } from './config'
export async function fetchDashboardSummary(signal) { const response = await fetch(apiUrl('/api/dashboard/summary'), { signal, headers: { Accept: 'application/json' } }); if (!response.ok) throw new Error(`Dashboard request failed (${response.status}).`); return response.json() }
