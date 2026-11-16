"use client";

import { Pencil, Plus, Save } from "lucide-react";
import { useState, type ReactNode } from "react";

import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingRows, QueryState } from "@/components/shared/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { formatMoney, formatPercentBps, humanize, minorToInput, parseMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Discount, DiscountKind, PaymentMethod, PaymentMethodKind, Restaurant } from "@/types/api";

const TIMEZONES = ["Asia/Bangkok", "Asia/Ho_Chi_Minh", "Asia/Singapore", "Asia/Kuala_Lumpur", "Asia/Jakarta", "Asia/Tokyo", "UTC"];

const bpsToPercent = (bps: number) => String(bps / 100);
const percentToBps = (value: string) => Math.round(Number(value) * 100);
const validPercent = (value: string, max: number) => value.trim() !== "" && Number(value) >= 0 && Number(value) <= max;

export default function SettingsPage() {
  const { t } = useI18n();
  const query = useApi<Restaurant>(["restaurant"], "/restaurants/current");
  return (
    <>
      <PageHeader title={t("Settings")} description="Restaurant details, tax and service charge, receipts, loyalty, payment methods and discounts." />
      <Tabs defaultValue="business">
        <TabsList className="flex-wrap">
          <TabsTrigger value="business">Business &amp; receipts</TabsTrigger>
          <TabsTrigger value="pricing">Tax &amp; service</TabsTrigger>
          <TabsTrigger value="operations">Stock, discounts &amp; loyalty</TabsTrigger>
          <TabsTrigger value="payments">Payment methods</TabsTrigger>
          <TabsTrigger value="discounts">Preset discounts</TabsTrigger>
        </TabsList>
        <QueryState query={query} loading={<LoadingRows rows={6} />}>
          {(restaurant) => (
            <>
              <TabsContent value="business">
                <BusinessForm key={restaurant.id} restaurant={restaurant} />
              </TabsContent>
              <TabsContent value="pricing">
                <PricingForm key={restaurant.id} restaurant={restaurant} />
              </TabsContent>
              <TabsContent value="operations">
                <OperationsForm key={restaurant.id} restaurant={restaurant} />
              </TabsContent>
            </>
          )}
        </QueryState>
        <TabsContent value="payments">
          <PaymentMethods />
        </TabsContent>
        <TabsContent value="discounts">
          <Discounts />
        </TabsContent>
      </Tabs>
    </>
  );
}

function useSaveSettings() {
  return useApiMutation((body: Partial<Restaurant>) => api<Restaurant>("/restaurants/current", { method: "PATCH", body }), {
    // "me" refreshes the restaurant name shown in the switcher.
    invalidate: ["restaurant", "me", "dashboard"],
    success: "Settings saved",
  });
}

function SettingsCard({
  title,
  description,
  children,
  onSave,
  disabled,
  pending,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  onSave: () => void;
  disabled?: boolean;
  pending?: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">{children}</CardContent>
      <CardFooter className="justify-end">
        <Button disabled={disabled || pending} onClick={onSave}>
          <Save /> Save changes
        </Button>
      </CardFooter>
    </Card>
  );
}

function BusinessForm({ restaurant }: { restaurant: Restaurant }) {
  const [form, setForm] = useState({
    name: restaurant.name,
    branch_name: restaurant.branch_name ?? "",
    legal_name: restaurant.legal_name ?? "",
    tax_id: restaurant.tax_id ?? "",
    address: restaurant.address ?? "",
    phone: restaurant.phone ?? "",
    email: restaurant.email ?? "",
    timezone: restaurant.timezone,
    order_number_prefix: restaurant.order_number_prefix,
    receipt_header: restaurant.receipt_header ?? "",
    receipt_footer: restaurant.receipt_footer ?? "",
  });
  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const save = useSaveSettings();
  const zones = TIMEZONES.includes(restaurant.timezone) ? TIMEZONES : [restaurant.timezone, ...TIMEZONES];
  const nullable = (v: string) => v.trim() || null;
  return (
    <SettingsCard
      title="Business and receipts"
      description="Shown on printed receipts. The time zone decides which local day a sale belongs to in reports."
      disabled={!form.name.trim() || !/^[A-Za-z0-9-]*$/.test(form.order_number_prefix)}
      pending={save.isPending}
      onSave={() =>
        save.mutate({
          name: form.name.trim(),
          branch_name: nullable(form.branch_name),
          legal_name: nullable(form.legal_name),
          tax_id: nullable(form.tax_id),
          address: nullable(form.address),
          phone: nullable(form.phone),
          email: nullable(form.email),
          timezone: form.timezone,
          order_number_prefix: form.order_number_prefix.trim(),
          receipt_header: nullable(form.receipt_header),
          receipt_footer: nullable(form.receipt_footer),
        })
      }
    >
      <FormField label="Restaurant name" htmlFor="b-name">
        <Input id="b-name" value={form.name} onChange={(e) => set("name", e.target.value)} />
      </FormField>
      <FormField label="Branch" htmlFor="b-branch">
        <Input id="b-branch" value={form.branch_name} onChange={(e) => set("branch_name", e.target.value)} />
      </FormField>
      <FormField label="Registered business name" htmlFor="b-legal">
        <Input id="b-legal" value={form.legal_name} onChange={(e) => set("legal_name", e.target.value)} />
      </FormField>
      <FormField label="Tax ID" htmlFor="b-taxid" hint="Printed on receipts when set.">
        <Input id="b-taxid" value={form.tax_id} onChange={(e) => set("tax_id", e.target.value)} />
      </FormField>
      <FormField label="Phone" htmlFor="b-phone">
        <Input id="b-phone" value={form.phone} onChange={(e) => set("phone", e.target.value)} />
      </FormField>
      <FormField label="Email" htmlFor="b-email">
        <Input id="b-email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
      </FormField>
      <FormField label="Address" htmlFor="b-address" className="sm:col-span-2">
        <Textarea id="b-address" rows={2} value={form.address} onChange={(e) => set("address", e.target.value)} />
      </FormField>
      <FormField label="Time zone" htmlFor="b-tz" hint={`Currency: ${restaurant.currency} (fixed).`}>
        <NativeSelect id="b-tz" value={form.timezone} onChange={(e) => set("timezone", e.target.value)}>
          {zones.map((z) => (
            <option key={z} value={z}>
              {z}
            </option>
          ))}
        </NativeSelect>
      </FormField>
      <FormField label="Order number prefix" htmlFor="b-prefix" hint={`Letters, digits and dashes. Orders are numbered like ${form.order_number_prefix || ""}0042.`}>
        <Input id="b-prefix" maxLength={8} value={form.order_number_prefix} onChange={(e) => set("order_number_prefix", e.target.value)} />
      </FormField>
      <FormField label="Receipt header" htmlFor="b-rheader">
        <Textarea id="b-rheader" rows={2} value={form.receipt_header} onChange={(e) => set("receipt_header", e.target.value)} />
      </FormField>
      <FormField label="Receipt footer" htmlFor="b-rfooter">
        <Textarea id="b-rfooter" rows={2} value={form.receipt_footer} onChange={(e) => set("receipt_footer", e.target.value)} />
      </FormField>
    </SettingsCard>
  );
}

function PricingForm({ restaurant }: { restaurant: Restaurant }) {
  const [taxRate, setTaxRate] = useState(bpsToPercent(restaurant.tax_rate_bps));
  const [taxLabel, setTaxLabel] = useState(restaurant.tax_label);
  const [inclusive, setInclusive] = useState(restaurant.prices_include_tax);
  const [service, setService] = useState(bpsToPercent(restaurant.service_charge_bps));
  const [serviceTaxable, setServiceTaxable] = useState(restaurant.service_charge_taxable);
  const [dineInOnly, setDineInOnly] = useState(restaurant.service_charge_dine_in_only);
  const save = useSaveSettings();
  const valid = validPercent(taxRate, 50) && validPercent(service, 50) && taxLabel.trim();
  return (
    <SettingsCard
      title="Tax and service charge"
      description="Applied to new orders. Existing orders keep the amounts they were priced with."
      disabled={!valid}
      pending={save.isPending}
      onSave={() =>
        save.mutate({
          tax_rate_bps: percentToBps(taxRate),
          tax_label: taxLabel.trim(),
          prices_include_tax: inclusive,
          service_charge_bps: percentToBps(service),
          service_charge_taxable: serviceTaxable,
          service_charge_dine_in_only: dineInOnly,
        })
      }
    >
      <FormField label="Tax rate (%)" htmlFor="p-tax" hint="Thailand VAT is 7%.">
        <Input id="p-tax" inputMode="decimal" value={taxRate} onChange={(e) => setTaxRate(e.target.value)} />
      </FormField>
      <FormField label="Tax label" htmlFor="p-label" hint="Printed on receipts, e.g. VAT.">
        <Input id="p-label" value={taxLabel} onChange={(e) => setTaxLabel(e.target.value)} />
      </FormField>
      <Label className="font-normal sm:col-span-2">
        <Switch checked={inclusive} onCheckedChange={setInclusive} /> Menu prices already include tax
      </Label>
      <FormField label="Service charge (%)" htmlFor="p-service" hint="0 to turn off.">
        <Input id="p-service" inputMode="decimal" value={service} onChange={(e) => setService(e.target.value)} />
      </FormField>
      <div className="grid content-end gap-3">
        <Label className="font-normal">
          <Switch checked={dineInOnly} onCheckedChange={setDineInOnly} /> Service charge for dine-in only
        </Label>
        <Label className="font-normal">
          <Switch checked={serviceTaxable} onCheckedChange={setServiceTaxable} /> Tax is charged on the service charge
        </Label>
      </div>
    </SettingsCard>
  );
}

function OperationsForm({ restaurant }: { restaurant: Restaurant }) {
  const [maxDiscount, setMaxDiscount] = useState(bpsToPercent(restaurant.max_cashier_discount_bps));
  const [allowNegative, setAllowNegative] = useState(restaurant.allow_negative_stock);
  const [loyalty, setLoyalty] = useState(restaurant.loyalty_enabled);
  const [spendPerPoint, setSpendPerPoint] = useState(minorToInput(restaurant.loyalty_spend_per_point_minor));
  const [pointValue, setPointValue] = useState(minorToInput(restaurant.loyalty_point_value_minor));
  const save = useSaveSettings();
  const spend = parseMoney(spendPerPoint);
  const value = parseMoney(pointValue);
  const valid = validPercent(maxDiscount, 100) && spend !== null && spend > 0 && value !== null;
  return (
    <SettingsCard
      title="Stock, discounts and loyalty"
      disabled={!valid}
      pending={save.isPending}
      onSave={() =>
        save.mutate({
          max_cashier_discount_bps: percentToBps(maxDiscount),
          allow_negative_stock: allowNegative,
          loyalty_enabled: loyalty,
          loyalty_spend_per_point_minor: spend ?? undefined,
          loyalty_point_value_minor: value ?? undefined,
        })
      }
    >
      <FormField label="Largest discount a cashier may give (%)" htmlFor="o-maxdisc" hint="Larger discounts need a manager.">
        <Input id="o-maxdisc" inputMode="decimal" value={maxDiscount} onChange={(e) => setMaxDiscount(e.target.value)} />
      </FormField>
      <div className="grid content-end gap-1">
        <Label className="font-normal">
          <Switch checked={allowNegative} onCheckedChange={setAllowNegative} /> Allow selling when recipe stock is short
        </Label>
        <p className="text-xs text-muted-foreground">
          Off (recommended): confirming an order fails when ingredients are short. On: stock may go negative until counted.
        </p>
      </div>
      <Label className="font-normal sm:col-span-2">
        <Switch checked={loyalty} onCheckedChange={setLoyalty} /> Loyalty points enabled
      </Label>
      <FormField label="Spend per point (฿)" htmlFor="o-spend" hint={spend ? `Customers earn 1 point per ${formatMoney(spend)} paid.` : "Must be above 0."}>
        <Input id="o-spend" inputMode="decimal" disabled={!loyalty} value={spendPerPoint} onChange={(e) => setSpendPerPoint(e.target.value)} />
      </FormField>
      <FormField label="Value of one point (฿)" htmlFor="o-value" hint={value !== null ? `1 point = ${formatMoney(value)} off when redeemed.` : undefined}>
        <Input id="o-value" inputMode="decimal" disabled={!loyalty} value={pointValue} onChange={(e) => setPointValue(e.target.value)} />
      </FormField>
    </SettingsCard>
  );
}

function PaymentMethods() {
  const query = useApi<PaymentMethod[]>(["payment-methods"], "/payments/methods", { include_inactive: true });
  const [editing, setEditing] = useState<PaymentMethod | "new" | null>(null);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Payment methods</CardTitle>
        <CardDescription>
          SmartPOS records payments; it is not connected to a card terminal or bank. Every method is marked as simulated and
          receipts say so. Confirm card and QR payments on the terminal or banking app before recording them.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <QueryState query={query}>
          {(methods) => (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Code</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Order</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {methods.map((m) => (
                  <TableRow key={m.id} className={m.is_active ? undefined : "opacity-60"}>
                    <TableCell className="font-medium">
                      {m.name} {m.is_simulated ? <Badge variant="outline">simulated</Badge> : null}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{m.code}</TableCell>
                    <TableCell>{humanize(m.kind)}</TableCell>
                    <TableCell className="text-right tabular">{m.display_order}</TableCell>
                    <TableCell>{m.is_active ? <Badge variant="success">Active</Badge> : <Badge variant="secondary">Hidden</Badge>}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon-sm" aria-label={`Edit ${m.name}`} onClick={() => setEditing(m)}>
                        <Pencil />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </QueryState>
        <div>
          <Button variant="outline" size="sm" onClick={() => setEditing("new")}>
            <Plus /> Add payment method
          </Button>
        </div>
      </CardContent>
      {editing ? <PaymentMethodDialog method={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}
    </Card>
  );
}

function PaymentMethodDialog({ method, onClose }: { method: PaymentMethod | null; onClose: () => void }) {
  const [name, setName] = useState(method?.name ?? "");
  const [code, setCode] = useState(method?.code ?? "");
  const [kind, setKind] = useState<PaymentMethodKind>(method?.kind ?? "OTHER");
  const [order, setOrder] = useState(String(method?.display_order ?? 0));
  const [active, setActive] = useState(method?.is_active ?? true);
  const save = useApiMutation(
    () =>
      method
        ? api(`/payments/methods/${method.id}`, { method: "PATCH", body: { name: name.trim(), display_order: Number(order) || 0, is_active: active } })
        : api("/payments/methods", { method: "POST", body: { name: name.trim(), code, kind, display_order: Number(order) || 0 } }),
    { invalidate: ["payment-methods"], success: "Payment method saved", onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{method ? `Edit ${method.name}` : "Add payment method"}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3">
          <FormField label="Name" htmlFor="pm-name">
            <Input id="pm-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </FormField>
          {!method ? (
            <>
              <FormField label="Code" htmlFor="pm-code" hint="Capital letters, digits and _; used in reports. Cannot be changed later.">
                <Input id="pm-code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} />
              </FormField>
              <FormField label="Type" htmlFor="pm-kind">
                <NativeSelect id="pm-kind" value={kind} onChange={(e) => setKind(e.target.value as PaymentMethodKind)}>
                  {(["CASH", "CARD", "QR", "OTHER"] as const).map((k) => (
                    <option key={k} value={k}>
                      {humanize(k)}
                    </option>
                  ))}
                </NativeSelect>
              </FormField>
            </>
          ) : null}
          <FormField label="Display order" htmlFor="pm-order">
            <Input id="pm-order" type="number" min={0} max={1000} value={order} onChange={(e) => setOrder(e.target.value)} />
          </FormField>
          {method ? (
            <Label className="font-normal">
              <Switch checked={active} onCheckedChange={setActive} /> Offered at checkout
            </Label>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!name.trim() || (!method && !/^[A-Z0-9_]+$/.test(code)) || save.isPending} onClick={() => save.mutate(undefined)}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Discounts() {
  const query = useApi<Discount[]>(["discounts"], "/discounts", { include_inactive: true });
  const [editing, setEditing] = useState<Discount | "new" | null>(null);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Preset discounts</CardTitle>
        <CardDescription>Quick choices at the POS. Discounts above the cashier limit, or marked as manager-only, need a manager.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <QueryState query={query}>
          {(discounts) =>
            discounts.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                    <TableHead>Manager only</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {discounts.map((d) => (
                    <TableRow key={d.id} className={d.is_active ? undefined : "opacity-60"}>
                      <TableCell className="font-medium">{d.name}</TableCell>
                      <TableCell className="text-right tabular">{d.kind === "PERCENT" ? formatPercentBps(d.value) : formatMoney(d.value)}</TableCell>
                      <TableCell>{d.requires_manager ? "Yes" : "No"}</TableCell>
                      <TableCell>{d.is_active ? <Badge variant="success">Active</Badge> : <Badge variant="secondary">Hidden</Badge>}</TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="icon-sm" aria-label={`Edit ${d.name}`} onClick={() => setEditing(d)}>
                          <Pencil />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="text-sm text-muted-foreground">No preset discounts. Managers can still enter a one-off discount with a reason at the POS.</p>
            )
          }
        </QueryState>
        <div>
          <Button variant="outline" size="sm" onClick={() => setEditing("new")}>
            <Plus /> Add discount
          </Button>
        </div>
      </CardContent>
      {editing ? <DiscountDialog discount={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}
    </Card>
  );
}

function DiscountDialog({ discount, onClose }: { discount: Discount | null; onClose: () => void }) {
  const [name, setName] = useState(discount?.name ?? "");
  const [kind, setKind] = useState<DiscountKind>(discount?.kind ?? "PERCENT");
  const [value, setValue] = useState(discount ? (discount.kind === "PERCENT" ? bpsToPercent(discount.value) : minorToInput(discount.value)) : "");
  const [managerOnly, setManagerOnly] = useState(discount?.requires_manager ?? false);
  const [active, setActive] = useState(discount?.is_active ?? true);
  const amount = kind === "PERCENT" ? (validPercent(value, 100) && Number(value) > 0 ? percentToBps(value) : null) : parseMoney(value);
  const save = useApiMutation(
    () =>
      discount
        ? api(`/discounts/${discount.id}`, { method: "PATCH", body: { name: name.trim(), value: amount, requires_manager: managerOnly, is_active: active } })
        : api("/discounts", { method: "POST", body: { name: name.trim(), kind, value: amount, requires_manager: managerOnly } }),
    { invalidate: ["discounts"], success: "Discount saved", onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{discount ? `Edit ${discount.name}` : "Add discount"}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3">
          <FormField label="Name" htmlFor="d-name">
            <Input id="d-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Type" htmlFor="d-kind">
              <NativeSelect id="d-kind" value={kind} disabled={!!discount} onChange={(e) => setKind(e.target.value as DiscountKind)}>
                <option value="PERCENT">Percentage</option>
                <option value="FIXED">Fixed amount</option>
              </NativeSelect>
            </FormField>
            <FormField label={kind === "PERCENT" ? "Percent (%)" : "Amount (฿)"} htmlFor="d-value">
              <Input id="d-value" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} />
            </FormField>
          </div>
          <Label className="font-normal">
            <Switch checked={managerOnly} onCheckedChange={setManagerOnly} /> Requires a manager
          </Label>
          {discount ? (
            <Label className="font-normal">
              <Switch checked={active} onCheckedChange={setActive} /> Shown at the POS
            </Label>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!name.trim() || !amount || save.isPending} onClick={() => save.mutate(undefined)}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
