import { useId } from 'react'
import './DustbinVisual.css'

export function DustbinVisual({ percentage, status }) {
  const clipId = useId()
  const hasReading = typeof percentage === 'number'
  const level = hasReading ? Math.max(0, Math.min(100, percentage)) : 0
  return <div className={`dustbin-visual ${status.toLowerCase().replace(' ', '-')}`} role="img" aria-label={hasReading ? `Waste fill level ${level}%` : 'No waste-fill reading available'}><svg viewBox="0 0 160 210" aria-hidden="true"><defs><clipPath id={clipId}><path d="M36 47h88l-8 141H44z" /></clipPath></defs><path className="bin-outline" d="M36 47h88l-8 141H44z" /><path className="bin-lid" d="M28 43h104M58 35h44" /><g clipPath={`url(#${clipId})`}><rect className="waste-fill" x="36" y="47" width="88" height="141" style={{ transform: `translateY(${141 - (level * 1.41)}px)` }} /></g><path className="bin-outline" d="M36 47h88l-8 141H44z" /></svg><span className="bin-percentage">{hasReading ? `${Math.round(level)}%` : '—'}</span></div>
}
