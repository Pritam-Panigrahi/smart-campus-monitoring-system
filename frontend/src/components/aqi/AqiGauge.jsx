import { clampAqi } from '../../lib/aqiData'
import './AqiGauge.css'

const CIRCUMFERENCE = 327
export function AqiGauge({ value, category }) {
  const aqi = clampAqi(value)
  const offset = aqi === null ? CIRCUMFERENCE : CIRCUMFERENCE * (1 - (aqi / 500))
  return <div className={`aqi-gauge ${category.toLowerCase().replace(' ', '-')}`} role="img" aria-label={aqi === null ? 'No AQI reading available' : `AQI ${aqi}, ${category}`}><svg viewBox="0 0 140 140" aria-hidden="true"><circle className="gauge-track" cx="70" cy="70" r="52" /><circle className="gauge-value" cx="70" cy="70" r="52" strokeDasharray={CIRCUMFERENCE} strokeDashoffset={offset} /></svg><div className="gauge-value-label"><strong>{aqi ?? '—'}</strong><span>AQI</span></div></div>
}
