import { statusLevel } from '../../lib/dashboardData'
export function StatusBadge({ status, hasReading = true }) { const level = statusLevel(status, hasReading); return <span className={`status-badge ${level}`}>{status || 'Unavailable'}</span> }
