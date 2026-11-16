"use client";

import { AlertTriangle, FlaskConical, Info, Loader2, Play, TrendingUp } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { ChartCard, ForecastChart, type ForecastDatum } from "@/components/charts/charts";
import { EmptyState } from "@/components/shared/empty-state";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingRows, QueryState } from "@/components/shared/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RecommendationsPanel } from "@/features/forecasting/recommendations";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime, formatNumber, formatQty, formatShortDate } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { ForecastRun, Ingredient, ModelInfo, ProductHistory } from "@/types/api";

const TABS = ["overview", "products", "ingredients", "recommendations"] as const;

export function ForecastingScreen() {
  const { t } = useI18n();
  const { can } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const tab = TABS.find((x) => x === params.get("tab")) ?? "overview";
  const [running, setRunning] = useState(false);
  const latest = useApi<ForecastRun>(["forecast", "latest"], "/forecast/latest", undefined, { retry: false });
  const noRun = latest.error instanceof ApiError && latest.error.code === "no_forecast";

  return (
    <>
      <PageHeader
        title={t("Forecasting")}
        description="Daily demand forecasts per menu item, converted to ingredient needs through recipes, and the reorder suggestions built on them."
        actions={
          can("forecast:run") ? (
            <Button onClick={() => setRunning(true)}>
              <Play /> Run forecast
            </Button>
          ) : null
        }
      />
      <Tabs value={tab} onValueChange={(v) => router.replace(`/forecasting?tab=${v}`, { scroll: false })}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="products">Menu items</TabsTrigger>
          <TabsTrigger value="ingredients">Ingredients</TabsTrigger>
          {can("recommendations:read") ? <TabsTrigger value="recommendations">Reorder suggestions</TabsTrigger> : null}
        </TabsList>
        {tab === "recommendations" ? (
          <TabsContent value="recommendations">
            <RecommendationsPanel />
          </TabsContent>
        ) : noRun ? (
          <EmptyState
            icon={TrendingUp}
            title="No forecast yet"
            description="Run a forecast to backtest the models on your sales history and predict the coming days."
            action={
              can("forecast:run") ? (
                <Button onClick={() => setRunning(true)}>
                  <Play /> Run forecast
                </Button>
              ) : undefined
            }
          />
        ) : (
          <QueryState query={latest} loading={<LoadingRows rows={8} />}>
            {(run) => (
              <>
                <TabsContent value="overview">
                  <Overview run={run} />
                </TabsContent>
                <TabsContent value="products">
                  <Products run={run} />
                </TabsContent>
                <TabsContent value="ingredients">
                  <Ingredients run={run} />
                </TabsContent>
              </>
            )}
          </QueryState>
        )}
      </Tabs>
      {running ? <RunDialog onClose={() => setRunning(false)} /> : null}
    </>
  );
}

function RunDialog({ onClose }: { onClose: () => void }) {
  const models = useApi<ModelInfo[]>(["forecast", "models"], "/forecast/models");
  const [model, setModel] = useState("auto");
  const [horizon, setHorizon] = useState("7");
  const [history, setHistory] = useState("180");
  const [evalDays, setEvalDays] = useState("14");
  const run = useApiMutation(
    () =>
      api<ForecastRun>("/forecast/runs", {
        method: "POST",
        body: { model, horizon_days: Number(horizon), history_days: Number(history), eval_days: Number(evalDays) },
      }),
    {
      invalidate: ["forecast", "recommendations", "dashboard"],
      success: (r) => `Forecast ready · ${r.products_forecast} items with ${r.model_name}`,
      onSuccess: onClose,
    },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && !run.isPending && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Run forecast</DialogTitle>
          <DialogDescription>
            Each model is backtested on the most recent days of history (rolling origin: fitted only on data before each day,
            then scored on the days that followed), then the chosen model predicts ahead. This can take a few seconds.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Model" htmlFor="fc-model" className="sm:col-span-2">
            <NativeSelect id="fc-model" value={model} onChange={(e) => setModel(e.target.value)}>
              <option value="auto">Automatic (lowest backtest MAE)</option>
              {(models.data ?? []).map((m) => (
                <option key={m.name} value={m.name}>
                  {m.label}
                </option>
              ))}
            </NativeSelect>
          </FormField>
          <FormField label="Forecast days" htmlFor="fc-horizon" hint="1–14">
            <Input id="fc-horizon" type="number" min={1} max={14} value={horizon} onChange={(e) => setHorizon(e.target.value)} />
          </FormField>
          <FormField label="Backtest days" htmlFor="fc-eval" hint="3–60">
            <Input id="fc-eval" type="number" min={3} max={60} value={evalDays} onChange={(e) => setEvalDays(e.target.value)} />
          </FormField>
          <FormField label="History used (days)" htmlFor="fc-history" hint="14–730" className="sm:col-span-2">
            <Input id="fc-history" type="number" min={14} max={730} value={history} onChange={(e) => setHistory(e.target.value)} />
          </FormField>
        </div>
        {models.data ? (
          <ul className="grid gap-1 text-xs text-muted-foreground">
            {models.data.map((m) => (
              <li key={m.name}>
                <span className="font-medium text-foreground">{m.label}:</span> {m.description} (needs {m.min_history_days}+ days)
              </li>
            ))}
          </ul>
        ) : null}
        <DialogFooter>
          <Button variant="outline" disabled={run.isPending} onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={run.isPending} onClick={() => run.mutate(undefined)}>
            {run.isPending ? <Loader2 className="animate-spin" /> : <Play />} Run
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function fmtMetric(value: number | null, digits = 2) {
  return value === null ? "—" : formatNumber(value, digits);
}

function Overview({ run }: { run: ForecastRun }) {
  const ranked = [...run.metrics].sort((a, b) => (a.mae ?? Infinity) - (b.mae ?? Infinity));
  const selected = run.metrics.find((m) => m.is_selected);
  // The demo banner already says this; avoid repeating it in the warning list.
  const warnings = run.warnings.filter((w) => !(run.uses_demo_data && /demo/i.test(w)));
  return (
    <div className="grid gap-4">
      {run.is_stale ? (
        <Card role="status" className="border-status-warning/60 bg-status-warning/10 py-4">
          <CardContent className="flex gap-3 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-status-warning" aria-hidden />
            <p>
              <strong>This forecast is out of date.</strong> It was made on {formatDateTime(run.created_at)} and
              predicts up to {run.covers_until ? formatDate(run.covers_until) : "no future dates"}. Until a new forecast is
              run, reorder suggestions use it as is and stock-out estimates fall back to recent sales.
            </p>
          </CardContent>
        </Card>
      ) : null}
      {run.uses_demo_data ? (
        <Card className="border-status-warning/50 bg-status-warning/10 py-4">
          <CardContent className="flex gap-3 text-sm">
            <FlaskConical className="mt-0.5 size-4 shrink-0" aria-hidden />
            <p>
              This forecast was trained on <strong>synthetic demo sales</strong>. Its accuracy says nothing about a real
              restaurant.
            </p>
          </CardContent>
        </Card>
      ) : null}
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="gap-2 py-4">
          <p className="px-5 text-sm text-muted-foreground">Model in use</p>
          <p className="px-5 text-xl font-semibold">{run.model_name}</p>
          <p className="px-5 text-xs text-muted-foreground">
            {run.selection_strategy === "auto" ? "Chosen automatically by lowest backtest MAE" : "Chosen manually"}
          </p>
        </Card>
        <Card className="gap-2 py-4">
          <p className="px-5 text-sm text-muted-foreground">Backtest error (MAE)</p>
          <p className="px-5 text-xl font-semibold tabular">{selected ? fmtMetric(selected.mae) : "—"} portions/day</p>
          <p className="px-5 text-xs text-muted-foreground">Average absolute miss per menu item per day</p>
        </Card>
        <Card className="gap-2 py-4">
          <p className="px-5 text-sm text-muted-foreground">Data</p>
          <p className="px-5 text-xl font-semibold">
            {run.history_days} days → {run.horizon_days} ahead
          </p>
          <p className="px-5 text-xs text-muted-foreground">
            {formatDate(run.history_start)} – {formatDate(run.history_end)} · run {formatDateTime(run.created_at)}
          </p>
        </Card>
      </div>
      {warnings.length ? (
        <Card className="py-4">
          <CardContent>
            <ul className="grid gap-1 text-sm">
              {warnings.map((w) => (
                <li key={w} className="flex gap-2">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-status-warning" aria-hidden /> {w}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>Model comparison</CardTitle>
          <CardDescription>
            Rolling-origin backtest over the last {String(run.parameters.eval_days ?? "")} days of history, 1 to {run.horizon_days}{" "}
            days ahead. Lower is better for every metric.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Model</TableHead>
                <TableHead className="text-right">MAE</TableHead>
                <TableHead className="text-right">RMSE</TableHead>
                <TableHead className="text-right">MAPE</TableHead>
                <TableHead className="text-right">Points</TableHead>
                <TableHead>Notes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ranked.map((m) => (
                <TableRow key={m.model_name}>
                  <TableCell>
                    <span className="font-medium">{m.model_name}</span>
                    {m.is_selected ? (
                      <Badge variant="success" className="ml-2">
                        selected
                      </Badge>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-right tabular">{fmtMetric(m.mae)}</TableCell>
                  <TableCell className="text-right tabular">{fmtMetric(m.rmse)}</TableCell>
                  <TableCell className="text-right tabular">{m.mape === null ? "—" : `${formatNumber(m.mape, 1)}%`}</TableCell>
                  <TableCell className="text-right tabular">{m.evaluation_points}</TableCell>
                  <TableCell className="max-w-72 text-xs text-muted-foreground">{m.notes ?? ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="flex gap-2 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            MAE and RMSE are in portions per item per day. MAPE skips days where the actual was zero (it is undefined there);
            {selected ? ` for the selected model ${selected.zero_actual_points} of ${selected.evaluation_points} points were zero-sales days.` : ""}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function Products({ run }: { run: ForecastRun }) {
  const [productId, setProductId] = useState(run.products[0]?.product_id ?? "");
  const history = useApi<ProductHistory>(
    ["forecast", "history", productId],
    productId ? `/forecast/products/${productId}/history` : null,
    { days: 28 },
  );
  const data: ForecastDatum[] = (history.data?.points ?? []).map((p) => ({
    date: p.date,
    label: formatShortDate(p.date),
    actual: p.closed ? null : p.actual_quantity,
    predicted: p.predicted_quantity,
    isFuture: p.is_future,
  }));
  const sorted = [...run.products].sort((a, b) => b.total_predicted - a.total_predicted);
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
      <ChartCard
        title={history.data?.product_name ?? "Menu item"}
        description="Daily portions sold vs what earlier forecast runs predicted for those days, then the current forecast. Closed days are left blank."
        chart={
          <div className="grid gap-3">
            <NativeSelect aria-label="Menu item" className="w-64" value={productId} onChange={(e) => setProductId(e.target.value)}>
              {sorted.map((p) => (
                <option key={p.product_id} value={p.product_id}>
                  {p.product_name}
                </option>
              ))}
            </NativeSelect>
            {history.isPending ? <LoadingRows rows={6} /> : <ForecastChart data={data} />}
          </div>
        }
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead className="text-right">Actual</TableHead>
                <TableHead className="text-right">Predicted</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((d) => (
                <TableRow key={d.date}>
                  <TableCell>
                    {formatDate(d.date)} {d.isFuture ? <Badge variant="outline">forecast</Badge> : null}
                  </TableCell>
                  <TableCell className="text-right tabular">{d.actual ?? "—"}</TableCell>
                  <TableCell className="text-right tabular">{d.predicted === null ? "—" : formatNumber(d.predicted, 1)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
      />
      <Card>
        <CardHeader>
          <CardTitle>Next {run.horizon_days} days</CardTitle>
          <CardDescription>Predicted portions per menu item</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Item</TableHead>
                <TableHead className="text-right">Portions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((p) => (
                <TableRow
                  key={p.product_id}
                  className="cursor-pointer"
                  aria-selected={p.product_id === productId}
                  onClick={() => setProductId(p.product_id)}
                >
                  <TableCell className={p.product_id === productId ? "font-semibold" : undefined}>{p.product_name}</TableCell>
                  <TableCell className="text-right tabular">{formatNumber(p.total_predicted, 0)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function Ingredients({ run }: { run: ForecastRun }) {
  const stock = useApi<Ingredient[]>(["ingredients"], "/ingredients");
  const byId = new Map((stock.data ?? []).map((i) => [i.id, i]));
  const rows = run.ingredients
    .map((i) => {
      const ing = byId.get(i.ingredient_id);
      const daily = i.total_predicted / Math.max(run.horizon_days, 1);
      const cover = ing && daily > 0 ? ing.current_stock / daily : null;
      return { ...i, stock: ing?.current_stock ?? null, cover };
    })
    .sort((a, b) => (a.cover ?? Infinity) - (b.cover ?? Infinity));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Ingredient needs</CardTitle>
        <CardDescription>
          Forecast portions × current recipes for the next {run.horizon_days} days, against stock on hand. Sorted by days of
          cover, shortest first.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {rows.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ingredient</TableHead>
                <TableHead className="text-right">Forecast use</TableHead>
                <TableHead className="text-right">In stock</TableHead>
                <TableHead className="text-right">Days of cover</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.ingredient_id}>
                  <TableCell className="font-medium">{r.ingredient_name}</TableCell>
                  <TableCell className="text-right tabular">{formatQty(r.total_predicted, r.base_unit)}</TableCell>
                  <TableCell className="text-right tabular">{r.stock === null ? "—" : formatQty(r.stock, r.base_unit)}</TableCell>
                  <TableCell className="text-right tabular">
                    {r.cover === null ? (
                      "—"
                    ) : r.cover < run.horizon_days ? (
                      <span className="inline-flex items-center gap-1 font-medium">
                        <AlertTriangle className="size-3.5 text-status-warning" aria-hidden />
                        {formatNumber(r.cover, 1)}
                      </span>
                    ) : (
                      formatNumber(r.cover, 1)
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <EmptyState title="No ingredient forecast" description="Add recipes to menu items so forecasts can be converted to ingredients." />
        )}
      </CardContent>
    </Card>
  );
}
