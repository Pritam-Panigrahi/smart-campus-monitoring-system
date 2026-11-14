import { useId } from 'react'
import './WaterTankVisual.css'

export function WaterTankVisual({ percentage, status }) {
  const clipId = useId()
  const hasReading = typeof percentage === 'number'
  const level = hasReading ? Math.max(0, Math.min(100, percentage)) : 0
  return <div className={`tank-visual ${status.toLowerCase().replace(' ', '-')}`} role="img" aria-label={hasReading ? `Water level ${level}%` : 'No water-level reading available'}><svg viewBox="0 0 160 210" aria-hidden="true"><defs><clipPath id={clipId}><rect x="27" y="18" width="106" height="170" rx="13" /></clipPath></defs><rect className="tank-outline" x="27" y="18" width="106" height="170" rx="13" /><g clipPath={`url(#${clipId})`}><rect className="water-fill" x="27" y="18" width="106" height="170" style={{ transform: `translateY(${170 - (level * 1.7)}px)` }} /></g><path className="tank-top" d="M45 18v-7h70v7" /></svg><span className="tank-percentage">{hasReading ? `${Math.round(level)}%` : '—'}</span></div>
}
