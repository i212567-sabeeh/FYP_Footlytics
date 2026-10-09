export function metric(value: number | null | undefined, unit = '', digits = 1): string {
  return value === null || value === undefined || !Number.isFinite(value)
    ? 'Unavailable' : `${value.toLocaleString('en-GB', { minimumFractionDigits: digits, maximumFractionDigits: digits })}${unit ? `${unit === '%' ? '' : ' '}${unit}` : ''}`
}
export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return 'Unavailable'
  const rounded = Math.round(seconds)
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, '0')}`
}
/** How the saved result measured maximum speed; nothing for results without the field. */
export function speedBasis(window: number | undefined): string | undefined {
  if (window === undefined || !Number.isFinite(window)) return undefined
  return window > 0
    ? `Fastest movement window of at least ${window} s, not an instantaneous peak.`
    : 'Fastest interval between consecutive observations.'
}
