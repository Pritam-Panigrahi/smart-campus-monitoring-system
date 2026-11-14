export function wasteBinStatus(value) {
  if (typeof value !== 'number') return 'No reading'
  if (value <= 25) return 'Low'
  if (value <= 50) return 'Medium'
  if (value <= 80) return 'Almost Full'
  return 'Full'
}
