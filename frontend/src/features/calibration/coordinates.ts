import type { Point } from './types'

// Both selection surfaces fill their element with no letterboxing or padding.
export function displayToPoint(clientX: number, clientY: number, bounds: Pick<DOMRect, 'left' | 'top' | 'width' | 'height'>, width: number, height: number): Point | null {
  if (bounds.width <= 0 || bounds.height <= 0) return null
  const x = (clientX - bounds.left) / bounds.width
  const y = (clientY - bounds.top) / bounds.height
  if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || x > 1 || y < 0 || y > 1) return null
  return { x: x * width, y: y * height }
}
