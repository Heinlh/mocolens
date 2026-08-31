import { useState } from 'react'
import type { Hotspot } from '@/types/analytics'
import type { ReferenceLocation } from '@/data/mock/crashes'
import { projectToMapPoint } from './mapProjection'

interface CrashHotspotMapProps {
  hotspots: Hotspot[]
  referenceLocations?: ReferenceLocation[]
  onSelectHotspot?: (hotspot: Hotspot) => void
  showLegend?: boolean
  legendCaption?: string
  height?: number
}

// A rough, stylized county outline - not a survey-accurate boundary.
const COUNTY_OUTLINE = 'M30,5 L55,3 L70,18 L92,55 L88,78 L68,95 L45,92 L22,75 L8,45 L15,15 Z'

const HIGHWAYS = [
  { id: 'i270', label: 'I-270', d: 'M28,14 L58,58', labelPos: { x: 40, y: 22 } },
  { id: 'i495', label: 'I-495', d: 'M24,80 Q55,94 84,60', labelPos: { x: 55, y: 91 } },
  { id: 'i95', label: 'I-95', d: 'M90,42 L84,90', labelPos: { x: 92, y: 40 } },
]

function intensityColor(intensity: number): string {
  if (intensity > 0.66) return 'var(--color-danger)'
  if (intensity > 0.33) return 'var(--color-accent)'
  return 'var(--color-accent-dark)'
}

// Montgomery County's inner suburbs (Wheaton, Bethesda, Silver Spring, Aspen
// Hill, North Bethesda...) sit close together on a real map. Rather than
// invent false spacing, reference-town labels within this radius of a
// hotspot are dropped (the dot stays) so the hotspot's own label wins.
const REFERENCE_LABEL_SUPPRESS_RADIUS = 15

function distance(ax: number, ay: number, bx: number, by: number): number {
  return Math.hypot(ax - bx, ay - by)
}

/** Full county hotspot map: outline, highways, reference towns, and data-driven hotspot markers. */
export function CrashHotspotMap({
  hotspots,
  referenceLocations = [],
  onSelectHotspot,
  showLegend = true,
  legendCaption,
  height = 420,
}: CrashHotspotMapProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const hotspotPoints = hotspots.map((h) => ({ hotspot: h, ...projectToMapPoint(h.latitude, h.longitude) }))
  // Alternate label side in geographic (not array) order, so markers that
  // are actually close together on screen end up on opposite sides.
  const labelBelowById = new Map(
    [...hotspotPoints].sort((a, b) => a.y - b.y).map((p, i) => [p.hotspot.id, i % 2 === 1]),
  )

  return (
    <div>
      <div style={{ height }}>
        <svg
          viewBox="0 0 100 100"
          className="h-full w-full"
          role="img"
          aria-label={`Map of crash hotspots across ${hotspots.length} areas in Montgomery County. Brighter, larger markers indicate more crashes.`}
        >
          <path d={COUNTY_OUTLINE} fill="var(--color-surface-elevated)" stroke="var(--color-border)" strokeWidth={0.5} />

          {HIGHWAYS.map((hwy) => (
            <g key={hwy.id}>
              <path d={hwy.d} fill="none" stroke="var(--color-border)" strokeWidth={0.6} strokeDasharray="1.5 1.5" />
              <text x={hwy.labelPos.x} y={hwy.labelPos.y} fontSize={2.6} fill="var(--color-text-muted)">
                {hwy.label}
              </text>
            </g>
          ))}

          {referenceLocations.map((loc) => {
            const { x, y } = projectToMapPoint(loc.latitude, loc.longitude)
            const nearHotspot = hotspotPoints.some((p) => distance(x, y, p.x, p.y) < REFERENCE_LABEL_SUPPRESS_RADIUS)
            return (
              <g key={loc.id}>
                <circle cx={x} cy={y} r={0.6} fill="var(--color-text-muted)" />
                {!nearHotspot && (
                  <text x={x + 1.5} y={y + 1} fontSize={2.4} fill="var(--color-text-muted)">
                    {loc.name}
                  </text>
                )}
              </g>
            )
          })}

          {hotspotPoints.map(({ hotspot, x, y }) => {
            const radius = 2.5 + hotspot.intensity * 4
            const color = intensityColor(hotspot.intensity)
            const isHovered = hoveredId === hotspot.id
            const trendLabel = `${hotspot.trend >= 0 ? '+' : ''}${hotspot.trend}%`
            const labelAbove = !labelBelowById.get(hotspot.id)
            const labelY = labelAbove ? y - radius - 1.5 : y + radius + 3.5
            const hoverLabelY = labelAbove ? y - radius - 5 : y + radius + 7

            return (
              <g
                key={hotspot.id}
                tabIndex={0}
                role="button"
                aria-label={`${hotspot.area}: ${hotspot.crashCount} crashes, ${trendLabel} change`}
                onMouseEnter={() => setHoveredId(hotspot.id)}
                onMouseLeave={() => setHoveredId(null)}
                onFocus={() => setHoveredId(hotspot.id)}
                onBlur={() => setHoveredId(null)}
                onClick={() => onSelectHotspot?.(hotspot)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') onSelectHotspot?.(hotspot)
                }}
                className="cursor-pointer outline-none"
              >
                <circle cx={x} cy={y} r={radius * 1.8} fill={color} opacity={0.18} />
                <circle
                  cx={x}
                  cy={y}
                  r={radius}
                  fill={color}
                  opacity={isHovered ? 1 : 0.85}
                  stroke={isHovered ? 'var(--color-text)' : 'none'}
                  strokeWidth={0.4}
                />
                <text x={x} y={labelY} textAnchor="middle" fontSize={2.6} fontWeight={600} fill="var(--color-text)">
                  {hotspot.area}
                </text>
                {isHovered && (
                  <text x={x} y={hoverLabelY} textAnchor="middle" fontSize={2.4} fill="var(--color-text-muted)">
                    {hotspot.crashCount} crashes · {trendLabel}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </div>

      {showLegend && (
        <div className="mt-3 flex items-center gap-3 text-xs text-text-muted">
          <span>Fewer crashes</span>
          <div
            className="h-1.5 flex-1 rounded-full"
            style={{ background: 'linear-gradient(to right, var(--color-accent-dark), var(--color-accent), var(--color-danger))' }}
            aria-hidden="true"
          />
          <span>More crashes</span>
        </div>
      )}
      {legendCaption && <p className="mt-1 text-xs text-text-muted">{legendCaption}</p>}
    </div>
  )
}
