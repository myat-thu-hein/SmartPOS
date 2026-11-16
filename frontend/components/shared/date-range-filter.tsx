"use client";

import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { localDate } from "@/lib/format";

export interface DateRange {
  start: string;
  end: string;
  preset: string;
}

const PRESETS: { id: string; label: string; days: [number, number] | null }[] = [
  { id: "today", label: "Today", days: [0, 0] },
  { id: "yesterday", label: "Yesterday", days: [-1, -1] },
  { id: "7d", label: "Last 7 days", days: [-6, 0] },
  { id: "30d", label: "Last 30 days", days: [-29, 0] },
  { id: "90d", label: "Last 90 days", days: [-89, 0] },
  { id: "custom", label: "Custom range", days: null },
];

export function rangeForPreset(preset: string, timeZone = "Asia/Bangkok"): DateRange {
  const spec = PRESETS.find((p) => p.id === preset) ?? PRESETS[2];
  const [a, b] = spec.days ?? [-6, 0];
  return { preset: spec.id, start: localDate(timeZone, a), end: localDate(timeZone, b) };
}

export function DateRangeFilter({
  value,
  onChange,
  timeZone,
}: {
  value: DateRange;
  onChange: (range: DateRange) => void;
  timeZone?: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <NativeSelect
        aria-label="Date range"
        className="w-40"
        value={value.preset}
        onChange={(e) =>
          e.target.value === "custom"
            ? onChange({ ...value, preset: "custom" })
            : onChange(rangeForPreset(e.target.value, timeZone))
        }
      >
        {PRESETS.map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}
          </option>
        ))}
      </NativeSelect>
      {value.preset === "custom" ? (
        <>
          <Input
            type="date"
            aria-label="Start date"
            className="w-40"
            value={value.start}
            max={value.end}
            onChange={(e) => e.target.value && onChange({ ...value, start: e.target.value })}
          />
          <span className="text-sm text-muted-foreground">to</span>
          <Input
            type="date"
            aria-label="End date"
            className="w-40"
            value={value.end}
            min={value.start}
            onChange={(e) => e.target.value && onChange({ ...value, end: e.target.value })}
          />
        </>
      ) : null}
    </div>
  );
}
