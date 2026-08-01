/**
 * Parse a datetime string returned by the backend.
 *
 * The backend stores datetimes in MySQL as naive UTC (no timezone suffix).
 * `new Date('2026-08-01T16:29:00')` treats it as LOCAL time, causing an
 * offset equal to the UTC offset (e.g. 8h in China). Appending 'Z' makes JS
 * parse it correctly as UTC.
 */
export function parseBackendDate(iso: string): Date {
  if (!iso) return new Date(NaN)
  // Already has a timezone designator (Z or ±hh:mm) → parse as-is.
  if (/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso)) return new Date(iso)
  return new Date(iso + 'Z')
}

export function formatBackendDate(iso: string): string {
  const d = parseBackendDate(iso)
  if (isNaN(d.getTime())) return iso || ''
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export function relTime(iso: string): string {
  const d = parseBackendDate(iso)
  if (isNaN(d.getTime())) return ''
  const diff = Date.now() - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
