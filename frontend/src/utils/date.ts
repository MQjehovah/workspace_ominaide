/** Parse a backend datetime string (naive UTC in MySQL) correctly as UTC. */
export function parseBackendDate(iso: string): Date {
  if (!iso) return new Date(NaN)
  if (/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso)) return new Date(iso)
  return new Date(iso + 'Z')
}

/**
 * Parse a wall-clock field (schedule start/end, todo due date).
 * These columns intentionally store the user's local time, so a naive ISO
 * string must be interpreted as local, not UTC.
 */
export function parseLocalDate(iso: string): Date {
  if (!iso) return new Date(NaN)
  return new Date(iso)
}

export function formatLocalDate(iso: string): string {
  const d = parseLocalDate(iso)
  if (isNaN(d.getTime())) return iso || ''
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export function formatBackendDate(iso: string): string {
  const d = parseBackendDate(iso)
  if (isNaN(d.getTime())) return iso || ''
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export function relTime(iso: string): string {
  const d = parseBackendDate(iso)
  if (isNaN(d.getTime())) return ''
  const diff = Date.now() - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return `${d.getMonth() + 1}/${d.getDate()}`
}
