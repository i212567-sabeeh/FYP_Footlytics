import type { ReviewSummary } from './types'

/**
 * Processed frames are first_frame + k × frame_stride for k = 0 … count − 1.
 * The backend currently reports first_frame = 0; offset arithmetic keeps any
 * other first frame correct and never yields a frame outside the saved range.
 */
export interface FrameRange { first: number; last: number; stride: number; count: number }

export function frameRange({ first_frame: first, last_frame: last, frame_stride: stride }: Pick<ReviewSummary, 'first_frame' | 'last_frame' | 'frame_stride'>): FrameRange | null {
  if (![first, last, stride].every(Number.isSafeInteger) || first < 0 || stride < 1 || last < first || (last - first) % stride !== 0) return null
  return { first, last, stride, count: (last - first) / stride + 1 }
}

/** The processed frame at a position, clamped to the first and last processed frames. */
export function frameAt(range: FrameRange, index: number): number {
  return range.first + Math.min(range.count - 1, Math.max(0, Math.round(index))) * range.stride
}

export const positionOf = (range: FrameRange, frame: number) => (frame - range.first) / range.stride

export function isProcessedFrame(range: FrameRange, frame: number): boolean {
  return Number.isSafeInteger(frame) && frame >= range.first && frame <= range.last && (frame - range.first) % range.stride === 0
}
