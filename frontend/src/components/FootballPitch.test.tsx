import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FootballPitch } from './FootballPitch'
import { pitchMarkings } from './pitchGeometry'

describe('football pitch', () => {
  it('uses standard marking sizes on a full pitch and caps them on small pitches', () => {
    const full = pitchMarkings(105, 68)
    expect([full.centreRadius, full.penalty.depth, full.penalty.width, full.penalty.spot, full.goal.depth, full.goal.width, full.corner])
      .toEqual([9.15, 16.5, 40.32, 11, 5.5, 18.32, 1])
    expect(full.penalty.arc?.half).toBeCloseTo(Math.sqrt(9.15 ** 2 - 5.5 ** 2))
    const small = pitchMarkings(40, 20)
    expect([small.centreRadius, small.penalty.depth, small.penalty.width, small.goal.depth, small.goal.width, small.corner]).toEqual([5, 10, 16, 4, 9, 0.5])
    expect(small.penalty.spot).toBeCloseTo(20 / 3)
  })
  it('keeps the coordinate system exact and draws data between grass and markings', () => {
    const { container } = render(<FootballPitch length={60} width={36} overlay={<rect data-testid="overlay" />}><circle data-testid="child" /></FootballPitch>)
    const pitch = screen.getByRole('img', { name: 'Football pitch, 60 metres long and 36 metres wide' })
    expect(pitch).toHaveAttribute('viewBox', '0 0 60 36')
    // No SVG text: the first <text> inside a selection surface must be a landmark number.
    expect(container.querySelector('text')).toBeNull()
    const order = [...pitch.querySelectorAll('[data-testid], g[stroke]')].map((node) => node.getAttribute('data-testid') ?? 'markings')
    expect(order).toEqual(['overlay', 'markings', 'child'])
    expect(pitch.querySelectorAll('path')).toHaveLength(2)
  })
})
