export function waterStatus(value) {
  if (typeof value !== 'number') return 'No reading'
  if (value >= 50) return 'Normal'
  if (value >= 25) return 'Attention'
  if (value >= 10) return 'Low'
  return 'Critical'
}
