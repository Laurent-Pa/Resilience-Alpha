"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";
import { formatMinute, formatPct, type ProberMinute } from "@/lib/admin-prober";

const SERIES = "var(--ra-chart-series)";
const MUTED = "var(--ra-input-text)";
const GRID = "var(--ra-border-primary)";
const SURFACE = "var(--ra-background)";

interface ProberSuccessChartProps {
  points: ProberMinute[];
}

/**
 * Taux de réussite par minute, une seule série : pas de légende, le titre de la page
 * nomme ce qui est tracé. Axe Y figé de 0 à 100 % : en échelle automatique, un passage
 * de 100 % à 92 % remplirait tout le graphique et se lirait comme un effondrement.
 */
export function ProberSuccessChart({ points }: ProberSuccessChartProps) {
  // Graduations sur les dizaines de minutes plutôt qu'à intervalle fixe depuis le début.
  const ticks = points
    .map((p) => p.minute)
    .filter((iso) => new Date(iso).getUTCMinutes() % 10 === 0);

  return (
    <figure
      aria-label="Taux de réussite de la sonde par minute, sur la dernière heure"
      className="w-full"
    >
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID} strokeWidth={1} />
          <XAxis
            dataKey="minute"
            ticks={ticks}
            tickFormatter={formatMinute}
            tickLine={false}
            axisLine={{ stroke: GRID }}
            tick={{ fill: MUTED, fontSize: 12 }}
          />
          <YAxis
            domain={[0, 100]}
            ticks={[0, 25, 50, 75, 100]}
            tickFormatter={(v: number) => formatPct(v)}
            tickLine={false}
            axisLine={false}
            width={56}
            tick={{ fill: MUTED, fontSize: 12 }}
          />
          <Tooltip
            content={ProberTooltip}
            cursor={{ stroke: MUTED, strokeWidth: 1 }}
            isAnimationActive={false}
          />
          <Area
            type="linear"
            dataKey="success_pct"
            stroke={SERIES}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            fill={SERIES}
            fillOpacity={0.1}
            dot={false}
            activeDot={{ r: 4, fill: SERIES, stroke: SURFACE, strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </figure>
  );
}

/** La valeur en premier, le contexte ensuite : au survol, on cherche le chiffre. */
function ProberTooltip({ active, payload }: TooltipContentProps) {
  const point = payload?.[0]?.payload as ProberMinute | undefined;
  if (!active || !point) return null;
  return (
    <div className="rounded-[4px] border border-[var(--ra-border-primary)] bg-[var(--ra-background)] px-3 py-2 shadow-sm">
      <div className="flex items-center gap-2">
        <span aria-hidden className="h-0.5 w-3 rounded-full bg-[var(--ra-chart-series)]" />
        <span className="text-sm font-semibold text-[var(--ra-foreground)]">
          {formatPct(point.success_pct)}
        </span>
      </div>
      <p className="mt-1 text-xs text-[var(--ra-input-text)]">
        {formatMinute(point.minute)} · {point.success_count} / {point.expected_count} virements
      </p>
    </div>
  );
}
