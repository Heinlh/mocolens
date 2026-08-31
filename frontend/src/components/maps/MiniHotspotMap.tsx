import type { Hotspot } from '@/types/analytics'

interface MiniHotspotMapProps {
  hotspots: Hotspot[]
  centerLabel: string
  height?: number
}

/** Fits the given points to a local 15-85 window so any small cluster reads clearly, regardless of scale. */
function fitToLocalBounds(hotspots: Hotspot[]) {
  const lats = hotspots.map((h) => h.latitude)
  const longs = hotspots.map((h) => h.longitude)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const minLong = Math.min(...longs)
  const maxLong = Math.max(...longs)
  const latSpan = maxLat - minLat || 1
  const longSpan = maxLong - minLong || 1

  return hotspots.map((h) => ({
    ...h,
    x: 15 + ((h.longitude - minLong) / longSpan) * 70,
    y: 20 + ((maxLat - h.latitude) / latSpan) * 65,
  }))
}

/** Small, zoomed-in illustration of crash clusters within a single area (e.g. inside an Agent answer). */
export function MiniHotspotMap({ hotspots, centerLabel, height = 220 }: MiniHotspotMapProps) {
  const points = fitToLocalBounds(hotspots)

  return (
    <div className="rounded-card border border-border bg-surface-elevated-2 p-2" style={{ height }}>
      <svg viewBox="0 0 100 100" className="h-full w-full" role="img" aria-label={`Map of crash clusters within ${centerLabel}`}>
        <text x="50" y="10" textAnchor="middle" fontSize={5.5} fontWeight={700} fill="var(--color-text)">
          {centerLabel}
        </text>
        {points.map((point) => {
          const radius = 3 + point.intensity * 5
          const color = point.intensity > 0.66 ? 'var(--color-danger)' : 'var(--color-accent)'
          return (
            <g key={point.id}>
              <circle cx={point.x} cy={point.y} r={radius * 1.6} fill={color} opacity={0.2} />
              <circle cx={point.x} cy={point.y} r={radius} fill={color} opacity={0.9} />
            </g>
          )
        })}
      </svg>
      <div className="flex items-center gap-2 px-1 text-[10px] text-text-muted">
        <span>Lower</span>
        <div
          className="h-1 flex-1 rounded-full"
          style={{ background: 'linear-gradient(to right, var(--color-accent-dark), var(--color-danger))' }}
          aria-hidden="true"
        />
        <span>Higher</span>
      </div>
    </div>
  )
}
