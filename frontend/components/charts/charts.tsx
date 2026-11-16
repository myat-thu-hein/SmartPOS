"use client";

// Chart components following the data-viz spec: thin marks, 4px rounded
// data-ends, 2px lines, recessive hairline grid, hover tooltips, and a table
// view for every chart (identity never relies on colour alone).

import { useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

const AXIS_TICK = { fill: "var(--chart-ink-muted)", fontSize: 12 };

interface TooltipRow {
  label: string;
  value: string;
  swatch?: string;
  dashed?: boolean;
}

function TooltipBox({ title, rows }: { title: string; rows: TooltipRow[] }) {
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-popover-foreground">{title}</p>
      {rows.map((row) => (
        <p key={row.label} className="flex items-center gap-2 text-muted-foreground">
          {row.swatch ? (
            <span
              aria-hidden
              className="inline-block h-0.5 w-3"
              style={{ background: row.dashed ? "none" : row.swatch, borderTop: row.dashed ? `2px dashed ${row.swatch}` : undefined }}
            />
          ) : null}
          <span>{row.label}</span>
          <span className="ml-auto pl-4 font-medium text-popover-foreground tabular">{row.value}</span>
        </p>
      ))}
    </div>
  );
}

/** Card with a Chart / Table toggle so every chart has an accessible table view. */
export function ChartCard({
  title,
  description,
  chart,
  table,
  className,
}: {
  title: string;
  description?: ReactNode;
  chart: ReactNode;
  table: ReactNode;
  className?: string;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
        <CardAction>
          <div role="group" aria-label={`${title} view`} className="inline-flex rounded-md border p-0.5 text-xs">
            {(["chart", "table"] as const).map((v) => (
              <button
                key={v}
                type="button"
                aria-pressed={view === v}
                onClick={() => setView(v)}
                className={cn(
                  "rounded px-2 py-1 capitalize text-muted-foreground",
                  view === v && "bg-secondary font-medium text-foreground",
                )}
              >
                {v}
              </button>
            ))}
          </div>
        </CardAction>
      </CardHeader>
      <CardContent>{view === "chart" ? chart : table}</CardContent>
    </Card>
  );
}

export interface ColumnDatum {
  key: string;
  label: string;
  value: number;
  secondary?: string;
}

/** Single-series column chart (one hue; the title names the measure). */
export function ColumnChart({
  data,
  valueLabel,
  formatValue,
  formatTick,
  height = 240,
  highlightKey,
}: {
  data: ColumnDatum[];
  valueLabel: string;
  formatValue: (v: number) => string;
  formatTick?: (v: number) => string;
  height?: number;
  highlightKey?: string;
}) {
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }} barCategoryGap="20%">
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis
            dataKey="label"
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={{ stroke: "var(--chart-axis)" }}
            interval="preserveStartEnd"
            minTickGap={12}
          />
          <YAxis
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            width={56}
            tickFormatter={formatTick ?? ((v: number) => formatValue(v))}
            allowDecimals={false}
          />
          <Tooltip
            cursor={{ fill: "var(--muted)", opacity: 0.6 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload as ColumnDatum;
              const rows: TooltipRow[] = [{ label: valueLabel, value: formatValue(d.value), swatch: "var(--series-1)" }];
              if (d.secondary) rows.push({ label: "Detail", value: d.secondary });
              return <TooltipBox title={d.label} rows={rows} />;
            }}
          />
          <Bar
            dataKey="value"
            name={valueLabel}
            fill="var(--series-1)"
            radius={[4, 4, 0, 0]}
            maxBarSize={24}
            isAnimationActive={false}
            shape={(props: unknown) => {
              const p = props as { x: number; y: number; width: number; height: number; payload: ColumnDatum };
              const dim = highlightKey && p.payload.key !== highlightKey;
              const r = Math.min(4, p.width / 2, Math.max(p.height, 0));
              if (p.height <= 0) return <g />;
              return (
                <path
                  d={`M${p.x},${p.y + p.height} V${p.y + r} Q${p.x},${p.y} ${p.x + r},${p.y} H${p.x + p.width - r} Q${p.x + p.width},${p.y} ${p.x + p.width},${p.y + r} V${p.y + p.height} Z`}
                  fill="var(--series-1)"
                  opacity={dim ? 0.45 : 1}
                />
              );
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ColumnTable({
  data,
  labelHeader,
  valueHeader,
  formatValue,
}: {
  data: ColumnDatum[];
  labelHeader: string;
  valueHeader: string;
  formatValue: (v: number) => string;
}) {
  return (
    <div className="max-h-72 overflow-y-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{labelHeader}</TableHead>
            <TableHead className="text-right">{valueHeader}</TableHead>
            {data.some((d) => d.secondary) ? <TableHead className="text-right">Detail</TableHead> : null}
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((d) => (
            <TableRow key={d.key}>
              <TableCell>{d.label}</TableCell>
              <TableCell className="text-right tabular">{formatValue(d.value)}</TableCell>
              {data.some((x) => x.secondary) ? (
                <TableCell className="text-right text-muted-foreground tabular">{d.secondary}</TableCell>
              ) : null}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/** Horizontal bars in HTML with the value printed at each bar tip. */
export function BarList({
  items,
  formatValue,
  emptyText = "No data for this period.",
}: {
  items: { key: string; label: string; value: number; detail?: string }[];
  formatValue: (v: number) => string;
  emptyText?: string;
}) {
  const max = Math.max(...items.map((i) => i.value), 0);
  if (!items.length) return <p className="py-6 text-center text-sm text-muted-foreground">{emptyText}</p>;
  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.key} className="grid gap-1">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate" title={item.label}>
              {item.label}
            </span>
            <span className="shrink-0 font-medium tabular">
              {formatValue(item.value)}
              {item.detail ? <span className="ml-2 text-xs font-normal text-muted-foreground">{item.detail}</span> : null}
            </span>
          </div>
          <div className="h-2 rounded-full bg-muted" aria-hidden>
            <div
              className="h-2 rounded-full bg-series-1"
              style={{ width: `${max > 0 ? Math.max((item.value / max) * 100, item.value > 0 ? 2 : 0) : 0}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

export interface ForecastDatum {
  date: string;
  label: string;
  actual: number | null;
  predicted: number | null;
  isFuture: boolean;
}

/** Actual vs predicted demand. Two series: legend + line style (solid/dashed) carry identity. */
export function ForecastChart({ data, height = 280 }: { data: ForecastDatum[]; height?: number }) {
  const firstFuture = data.find((d) => d.isFuture)?.label;
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-4 text-xs text-muted-foreground" aria-label="Legend">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-0.5 w-4 bg-series-1" /> Actual sales
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block w-4 border-t-2 border-dashed border-series-2" /> Predicted
        </span>
      </div>
      <div style={{ height }} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis
              dataKey="label"
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={{ stroke: "var(--chart-axis)" }}
              interval="preserveStartEnd"
              minTickGap={16}
            />
            <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={40} allowDecimals={false} />
            {firstFuture ? (
              <ReferenceLine
                x={firstFuture}
                stroke="var(--chart-axis)"
                label={{ value: "Forecast →", position: "insideTopLeft", fill: "var(--chart-ink-muted)", fontSize: 11 }}
              />
            ) : null}
            <Tooltip
              cursor={{ stroke: "var(--chart-axis)", strokeWidth: 1 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload as ForecastDatum;
                return (
                  <TooltipBox
                    title={`${d.label}${d.isFuture ? " (forecast)" : ""}`}
                    rows={[
                      { label: "Actual", value: d.actual === null ? "—" : String(d.actual), swatch: "var(--series-1)" },
                      {
                        label: "Predicted",
                        value: d.predicted === null ? "—" : d.predicted.toFixed(1),
                        swatch: "var(--series-2)",
                        dashed: true,
                      },
                    ]}
                  />
                );
              }}
            />
            <Line
              type="monotone"
              dataKey="actual"
              name="Actual sales"
              stroke="var(--series-1)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, stroke: "var(--chart-surface)", strokeWidth: 2 }}
              connectNulls={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="predicted"
              name="Predicted"
              stroke="var(--series-2)"
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
              activeDot={{ r: 4, stroke: "var(--chart-surface)", strokeWidth: 2 }}
              connectNulls
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export interface SparkPoint {
  label: string;
  value: number;
}

/**
 * Stat-tile trend: a 2px line in the de-emphasis ink with the current period as an
 * accent dot. Hover shows each point; the full series is in the chart's table view.
 */
export function Sparkline({
  points,
  formatValue,
  height = 36,
  className,
}: {
  points: SparkPoint[];
  formatValue: (v: number) => string;
  height?: number;
  className?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return null;
  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 4; // keeps the dot and stroke inside the box
  const x = (i: number) => (i / (points.length - 1)) * 100;
  const y = (v: number) => pad + (1 - (v - min) / span) * (height - pad * 2);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(2)},${y(p.value).toFixed(2)}`).join(" ");
  const last = points.length - 1;
  const shown = hover ?? last;
  return (
    <div
      className={cn("relative w-full", className)}
      style={{ height }}
      onPointerMove={(e) => {
        const box = e.currentTarget.getBoundingClientRect();
        setHover(Math.round(((e.clientX - box.left) / box.width) * last));
      }}
      onPointerLeave={() => setHover(null)}
    >
      <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" className="absolute inset-0 size-full overflow-visible" aria-hidden>
        <path d={d} fill="none" stroke="var(--chart-ink-muted)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        {hover !== null ? (
          <line x1={x(hover)} x2={x(hover)} y1={0} y2={height} stroke="var(--chart-axis)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        ) : null}
      </svg>
      <span
        aria-hidden
        className="absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card"
        style={{
          left: `${x(shown)}%`,
          top: y(points[shown].value),
          background: shown === last ? "var(--series-1)" : "var(--chart-ink-muted)",
        }}
      />
      {hover !== null ? (
        <span
          className="pointer-events-none absolute -top-7 z-10 -translate-x-1/2 rounded-md border bg-popover px-2 py-0.5 text-[11px] whitespace-nowrap text-popover-foreground shadow-raised"
          style={{ left: `${Math.min(85, Math.max(15, x(hover)))}%` }}
        >
          {points[hover].label} · <span className="font-medium tabular">{formatValue(points[hover].value)}</span>
        </span>
      ) : null}
    </div>
  );
}
