/**
 * Schematic pitch markings in metres for a pitch of the given Match dimensions.
 * Standard (IFAB) sizes are capped so markings stay proportional on smaller
 * pitches; they are drawing guides only, never measured landmarks.
 */
export interface PitchMarkings {
  line: number
  spot: number
  centreRadius: number
  corner: number
  penalty: { depth: number; width: number; spot: number; arc: { reach: number; half: number } | null }
  goal: { depth: number; width: number }
}

export function pitchMarkings(length: number, width: number): PitchMarkings {
  const centreRadius = Math.min(9.15, length / 6, width / 4)
  const depth = Math.min(16.5, length / 4)
  const spot = depth * (11 / 16.5)
  // The penalty arc is the part of the centre-circle radius around the spot outside the area.
  const reach = depth - spot
  return {
    line: Math.min(length, width) / 200,
    spot: Math.min(length, width) / 150,
    centreRadius,
    corner: Math.min(1, length / 40, width / 40),
    penalty: { depth, width: Math.min(40.32, width * 0.8), spot,
      arc: centreRadius > reach ? { reach, half: Math.sqrt(centreRadius ** 2 - reach ** 2) } : null },
    goal: { depth: Math.min(5.5, length / 10), width: Math.min(18.32, width * 0.45) },
  }
}
