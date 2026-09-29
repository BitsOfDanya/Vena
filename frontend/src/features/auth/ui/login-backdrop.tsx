const LANES = [
  { y: 170, points: [70, 190, 250, 420, 520, 610], shape: "triangle" },
  { y: 220, points: [110, 300, 360, 470, 640], shape: "square" },
  { y: 270, points: [40, 160, 230, 330, 400, 560, 690], shape: "diamond" },
  { y: 320, points: [90, 210, 280, 380, 500, 590, 660], shape: "circle" },
]

const ALERTS = new Set(["170-420", "270-400", "320-590"])
const WATCH = new Set(["220-300", "320-210", "270-160"])

function Glyph({ shape, x, y, fill }: { shape: string; x: number; y: number; fill: string }) {
  if (shape === "triangle") return <path d={`M${x - 7},${y - 5} L${x + 7},${y - 5} L${x},${y + 7} Z`} fill={fill} />
  if (shape === "square") return <rect x={x - 5.5} y={y - 5.5} width={11} height={11} fill={fill} />
  if (shape === "diamond") return <path d={`M${x},${y - 7} L${x + 7},${y} L${x},${y + 7} L${x - 7},${y} Z`} fill={fill} />
  return <circle cx={x} cy={y} r={6} fill={fill} />
}

export function LoginBackdrop() {
  return (
    <svg aria-hidden viewBox="0 0 720 560" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 size-full [mask-image:linear-gradient(to_bottom,transparent_0%,black_14%,black_40%,transparent_58%)]">
      <defs>
        <pattern id="vena-grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M40 0H0V40" fill="none" stroke="currentColor" strokeOpacity="0.06" />
        </pattern>
      </defs>
      <rect width="720" height="560" fill="url(#vena-grid)" />
      <path d="M0 120H720" stroke="currentColor" strokeOpacity="0.35" strokeWidth="6" />
      {Array.from({ length: 19 }, (_, index) => 20 + index * 38).map((x, index) => (
        <g key={x}>
          <path d={`M${x} 110V130`} stroke="currentColor" strokeOpacity="0.3" />
          {index % 3 === 0 ? (
            <text x={x} y={100} textAnchor="middle" fontSize="11" fill="currentColor" fillOpacity="0.45" fontFamily="var(--font-plex-mono)">
              ПК{index * 10}
            </text>
          ) : null}
        </g>
      ))}
      {LANES.map((lane) => (
        <g key={lane.y}>
          <path d={`M0 ${lane.y}H720`} stroke="currentColor" strokeOpacity="0.14" strokeDasharray="2 6" />
          {lane.points.map((x) => {
            const key = `${lane.y}-${x}`
            const alert = ALERTS.has(key)
            const watch = WATCH.has(key)
            const fill = alert ? "var(--status-critical)" : watch ? "var(--status-attention)" : "currentColor"
            return (
              <g key={key} opacity={alert || watch ? 1 : 0.4}>
                {alert ? <circle cx={x} cy={lane.y} r={16} fill="var(--status-critical)" opacity={0.18} className="vena-breathe" /> : null}
                <Glyph shape={lane.shape} x={x} y={lane.y} fill={fill} />
              </g>
            )
          })}
        </g>
      ))}
    </svg>
  )
}
