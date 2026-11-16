"use client";

import { Check, ClipboardList, Info, Loader2, Pencil, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { FormField } from "@/components/shared/form-field";
import { QueryState } from "@/components/shared/query-state";
import { RecommendationStatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, formatQty } from "@/lib/format";
import type { Recommendation, RecommendationStatus } from "@/types/api";

const INVALIDATE = ["recommendations", "dashboard", "purchase-orders"];
const ACTIONABLE: RecommendationStatus[] = ["APPROVED", "MODIFIED"];

interface CreatedPO {
  purchase_order_id: string;
  display_number: string;
  supplier_name: string;
  recommendation_ids: string[];
}

interface GenerateResult {
  created: Recommendation[];
  superseded: number;
  skipped_without_need: number;
  notes: string[];
}

export function RecommendationsPanel() {
  const { can } = useAuth();
  const reviewer = can("recommendations:review");
  const [status, setStatus] = useState("open");
  const [reviewPeriod, setReviewPeriod] = useState("3");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [explaining, setExplaining] = useState<Recommendation | null>(null);
  const [modifying, setModifying] = useState<Recommendation | null>(null);
  const [rejecting, setRejecting] = useState<Recommendation | null>(null);
  const [created, setCreated] = useState<CreatedPO[] | null>(null);
  const statuses = status === "open" ? ["PENDING", "APPROVED", "MODIFIED"] : status ? [status] : undefined;
  const query = useApi<Recommendation[]>(["recommendations", "list"], "/recommendations", { status: statuses });

  const generate = useApiMutation(
    () => api<GenerateResult>("/recommendations/generate", { method: "POST", body: { review_period_days: Number(reviewPeriod) || 3 } }),
    {
      invalidate: INVALIDATE,
      success: (r) =>
        `${r.created.length} suggestion(s) created` +
        (r.superseded ? `, ${r.superseded} older pending replaced` : "") +
        (r.skipped_without_need ? `, ${r.skipped_without_need} ingredient(s) need nothing` : ""),
    },
  );
  const approve = useApiMutation((id: string) => api(`/recommendations/${id}/approve`, { method: "POST", body: {} }), {
    invalidate: INVALIDATE,
    success: "Suggestion approved",
  });
  const createPOs = useApiMutation(
    () => api<CreatedPO[]>("/recommendations/purchase-orders", { method: "POST", body: { recommendation_ids: [...selected] } }),
    {
      invalidate: INVALIDATE,
      success: (pos) => `Created ${pos.length} draft purchase order(s)`,
      onSuccess: (pos) => {
        setCreated(pos);
        setSelected(new Set());
      },
    },
  );

  const list = query.data ?? [];
  const selectable = list.filter((r) => ACTIONABLE.includes(r.status) && !r.purchase_order_id && r.supplier_id);
  const toggle = (id: string, on: boolean) =>
    setSelected((s) => {
      const next = new Set(s);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  return (
    <div className="grid gap-4">
      <Card className="border-primary/30 bg-primary/5 py-4">
        <CardContent className="flex gap-3 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
          <p>
            Suggestions are calculated from the forecast, current stock, open purchase orders, safety stock and supplier lead
            time. Nothing is ordered automatically: a manager approves or edits each one, and approved suggestions only become{" "}
            <strong>draft</strong> purchase orders that still need to be submitted.
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Reorder suggestions</CardTitle>
          <CardDescription>Review, then turn approved suggestions into draft purchase orders.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <NativeSelect aria-label="Status" className="w-60" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="open">Open (pending + approved)</option>
              <option value="PENDING">Pending</option>
              <option value="APPROVED">Approved</option>
              <option value="MODIFIED">Modified</option>
              <option value="REJECTED">Rejected</option>
              <option value="COMPLETED">Completed</option>
              <option value="">All</option>
            </NativeSelect>
            {reviewer ? (
              <div className="flex flex-wrap items-end gap-2">
                <FormField label="Next order opportunity (days)" htmlFor="rec-review" className="w-52">
                  <Input id="rec-review" type="number" min={1} max={28} value={reviewPeriod} onChange={(e) => setReviewPeriod(e.target.value)} />
                </FormField>
                <Button variant="outline" disabled={generate.isPending} onClick={() => generate.mutate(undefined)}>
                  {generate.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />} Recalculate from latest forecast
                </Button>
                {can("purchasing:write") ? (
                  <Button disabled={!selected.size || createPOs.isPending} onClick={() => createPOs.mutate(undefined)}>
                    <ClipboardList /> Create draft POs ({selected.size})
                  </Button>
                ) : null}
              </div>
            ) : null}
          </div>
          {generate.data?.notes.length ? (
            <ul className="list-disc pl-5 text-xs text-muted-foreground">
              {generate.data.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          ) : null}
          {created?.length ? (
            <div className="rounded-lg border bg-muted/40 p-3 text-sm">
              <p className="font-medium">Draft purchase orders created (not submitted):</p>
              <ul className="mt-1 flex flex-wrap gap-3">
                {created.map((po) => (
                  <li key={po.purchase_order_id}>
                    <Link className="underline underline-offset-4" href={`/purchase-orders/${po.purchase_order_id}`}>
                      {po.display_number}
                    </Link>{" "}
                    <span className="text-muted-foreground">· {po.supplier_name}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <QueryState query={query}>
            {(recs) =>
              recs.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      {reviewer ? (
                        <TableHead className="w-8">
                          <Checkbox
                            aria-label="Select all approved"
                            checked={selectable.length > 0 && selectable.every((r) => selected.has(r.id))}
                            disabled={!selectable.length}
                            onCheckedChange={(v) => setSelected(v ? new Set(selectable.map((r) => r.id)) : new Set())}
                          />
                        </TableHead>
                      ) : null}
                      <TableHead>Ingredient</TableHead>
                      <TableHead>Supplier</TableHead>
                      <TableHead className="text-right">In stock</TableHead>
                      <TableHead className="text-right">Forecast use</TableHead>
                      <TableHead className="text-right">Suggested</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {recs.map((r) => {
                      const canSelect = selectable.includes(r);
                      const qty = r.approved_quantity ?? r.suggested_quantity;
                      return (
                        <TableRow key={r.id}>
                          {reviewer ? (
                            <TableCell>
                              <Checkbox
                                aria-label={`Select ${r.ingredient_name}`}
                                checked={selected.has(r.id)}
                                disabled={!canSelect}
                                onCheckedChange={(v) => toggle(r.id, !!v)}
                              />
                            </TableCell>
                          ) : null}
                          <TableCell>
                            <p className="font-medium">{r.ingredient_name}</p>
                            <p className="max-w-80 text-xs text-muted-foreground">{r.reason}</p>
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {r.supplier_name ?? <span className="text-status-critical">No supplier</span>}
                            <p className="text-xs">{r.lead_time_days}-day lead time</p>
                          </TableCell>
                          <TableCell className="text-right tabular">{formatQty(r.current_stock, r.unit)}</TableCell>
                          <TableCell className="text-right tabular">
                            {formatQty(r.forecast_demand, r.unit)}
                            <p className="text-xs text-muted-foreground">over {r.coverage_days} days</p>
                          </TableCell>
                          <TableCell className="text-right font-medium tabular">
                            {formatQty(qty, r.unit)}
                            {r.approved_quantity !== null && r.approved_quantity !== r.suggested_quantity ? (
                              <p className="text-xs font-normal text-muted-foreground line-through">{formatQty(r.suggested_quantity, r.unit)}</p>
                            ) : null}
                          </TableCell>
                          <TableCell>
                            <RecommendationStatusBadge status={r.status} />
                            {r.purchase_order_id ? (
                              <Link href={`/purchase-orders/${r.purchase_order_id}`} className="mt-1 block text-xs underline underline-offset-4">
                                View PO
                              </Link>
                            ) : null}
                          </TableCell>
                          <TableCell className="text-right whitespace-nowrap">
                            <Button variant="ghost" size="icon-sm" aria-label={`How ${r.ingredient_name} was calculated`} onClick={() => setExplaining(r)}>
                              <Info />
                            </Button>
                            {reviewer && r.status === "PENDING" ? (
                              <>
                                <Button variant="ghost" size="icon-sm" aria-label={`Approve ${r.ingredient_name}`} disabled={approve.isPending} onClick={() => approve.mutate(r.id)}>
                                  <Check />
                                </Button>
                                <Button variant="ghost" size="icon-sm" aria-label={`Change quantity for ${r.ingredient_name}`} onClick={() => setModifying(r)}>
                                  <Pencil />
                                </Button>
                                <Button variant="ghost" size="icon-sm" aria-label={`Reject ${r.ingredient_name}`} onClick={() => setRejecting(r)}>
                                  <X />
                                </Button>
                              </>
                            ) : null}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              ) : (
                <EmptyState
                  icon={Sparkles}
                  title="No suggestions"
                  description={reviewer ? "Run a forecast, then recalculate to see what needs reordering." : "Nothing to review right now."}
                />
              )
            }
          </QueryState>
        </CardContent>
      </Card>
      {explaining ? <ExplainDialog rec={explaining} onClose={() => setExplaining(null)} /> : null}
      {modifying ? <ModifyDialog rec={modifying} onClose={() => setModifying(null)} /> : null}
      {rejecting ? <RejectDialog rec={rejecting} onClose={() => setRejecting(null)} /> : null}
    </div>
  );
}

function ExplainDialog({ rec, onClose }: { rec: Recommendation; onClose: () => void }) {
  const c = rec.calculation as Record<string, string | number | null>;
  const rows: [string, string][] = [
    [`Forecast use over ${rec.coverage_days} days`, `+ ${formatQty(rec.forecast_demand, rec.unit)}`],
    ["Safety stock", `+ ${formatQty(rec.safety_stock, rec.unit)}`],
    ["Current stock", `− ${formatQty(rec.current_stock, rec.unit)}`],
    ["Already on order", `− ${formatQty(rec.incoming_quantity, rec.unit)}`],
    ["Shortfall", `= ${formatQty(rec.raw_quantity, rec.unit)}`],
  ];
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>How {rec.ingredient_name} was calculated</DialogTitle>
          <DialogDescription>{rec.reason}</DialogDescription>
        </DialogHeader>
        <dl className="grid gap-1 text-sm">
          {rows.map(([label, value]) => (
            <div key={label} className="flex justify-between gap-4 border-b py-1.5 last:border-0">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="font-medium tabular">{value}</dd>
            </div>
          ))}
          <div className="flex justify-between gap-4 py-1.5">
            <dt className="text-muted-foreground">
              Suggested{rec.min_order_quantity ? ` (rounded up to multiples of ${formatQty(rec.min_order_quantity, rec.unit)})` : ""}
            </dt>
            <dd className="font-semibold tabular">{formatQty(rec.suggested_quantity, rec.unit)}</dd>
          </div>
        </dl>
        <ul className="grid gap-1 text-xs text-muted-foreground">
          <li>
            Coverage = lead time {rec.lead_time_days} day(s) (from {String(c.lead_time_source ?? "defaults")}) + review period{" "}
            {String(c.review_period_days ?? "—")} day(s).
          </li>
          <li>
            Forecast model: {String(c.forecast_model ?? "—")}; {String(c.forecast_days_used ?? "—")} forecast day(s) used
            {Number(c.extrapolated_days) > 0 ? `, ${c.extrapolated_days} extrapolated from the daily average` : ""}.
          </li>
          <li>Created {formatDateTime(rec.created_at)}.</li>
          {rec.reviewed_at ? (
            <li>
              Reviewed by {rec.reviewer_name ?? "a manager"} on {formatDateTime(rec.reviewed_at)}
              {rec.review_note ? `: "${rec.review_note}"` : ""}.
            </li>
          ) : null}
        </ul>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ModifyDialog({ rec, onClose }: { rec: Recommendation; onClose: () => void }) {
  const [quantity, setQuantity] = useState(String(rec.suggested_quantity));
  const [note, setNote] = useState("");
  const modify = useApiMutation(
    () => api(`/recommendations/${rec.id}/modify`, { method: "POST", body: { quantity, unit: rec.unit, note: note.trim() || null } }),
    { invalidate: INVALIDATE, success: "Quantity changed and approved", onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Change quantity · {rec.ingredient_name}</DialogTitle>
          <DialogDescription>Suggested {formatQty(rec.suggested_quantity, rec.unit)}. Saving approves the suggestion with your quantity.</DialogDescription>
        </DialogHeader>
        <FormField label={`Quantity (${rec.unit})`} htmlFor="mod-qty">
          <Input id="mod-qty" inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} autoFocus />
        </FormField>
        <FormField label="Note (optional)" htmlFor="mod-note">
          <Textarea id="mod-note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </FormField>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!(Number(quantity) > 0) || modify.isPending} onClick={() => modify.mutate(undefined)}>
            Save and approve
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RejectDialog({ rec, onClose }: { rec: Recommendation; onClose: () => void }) {
  const [note, setNote] = useState("");
  const reject = useApiMutation(
    () => api(`/recommendations/${rec.id}/reject`, { method: "POST", body: { note: note.trim() || null } }),
    { invalidate: INVALIDATE, success: "Suggestion rejected", onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Reject · {rec.ingredient_name}</DialogTitle>
          <DialogDescription>The suggestion is kept for the record but will not be ordered.</DialogDescription>
        </DialogHeader>
        <FormField label="Reason (optional)" htmlFor="rej-note">
          <Textarea id="rej-note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} autoFocus />
        </FormField>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="destructive" disabled={reject.isPending} onClick={() => reject.mutate(undefined)}>
            Reject
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
