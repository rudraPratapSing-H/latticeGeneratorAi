/** Format a number with fixed decimals, using tabular-nums style */
export function fmt(value: number, decimals = 1): string {
  return value.toFixed(decimals)
}

/** Format percentage with 1 decimal */
export function fmtPct(value: number): string {
  return `${value.toFixed(1)}%`
}

/** Format a number as GPa */
export function fmtGpa(value: number): string {
  return `${value.toFixed(1)} GPa`
}

/** Format a number as MPa */
export function fmtMpa(value: number): string {
  return `${value.toFixed(0)} MPa`
}

/** Format mass in grams */
export function fmtMass(value: number): string {
  return `${value.toFixed(1)} g`
}

/** Format millimeters */
export function fmtMm(value: number): string {
  return `${value.toFixed(2)} mm`
}

/** Format a duration in seconds to "Xs" or "Xm Ys" */
export function fmtDuration(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}m ${s}s`
}

/** Format a relative density as percentage */
export function fmtRelDensity(rd: number): string {
  return `${(rd * 100).toFixed(1)}%`
}

/** Truncate a string with ellipsis */
export function truncate(str: string, maxLen: number): string {
  if (str.length <= maxLen) return str
  return str.slice(0, maxLen - 1) + '…'
}

/** Format a timestamp to a readable time */
export function fmtTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}
