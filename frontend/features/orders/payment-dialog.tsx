"use client";

import { Banknote, CreditCard, Info, Loader2, QrCode, Wallet } from "lucide-react";
import { useMemo, useState } from "react";

import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useApi, useApiMutation } from "@/hooks/use-api";
import { api, newIdempotencyKey } from "@/lib/api";
import { formatMoney, minorToInput, parseMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { Order, PaymentMethod, PaymentMethodKind } from "@/types/api";

const ICONS: Record<PaymentMethodKind, typeof Banknote> = {
  CASH: Banknote,
  CARD: CreditCard,
  QR: QrCode,
  OTHER: Wallet,
};

const QUICK_CASH = [10000, 50000, 100000];

export function PaymentDialog({
  order,
  open,
  onOpenChange,
  onPaid,
}: {
  order: Pick<Order, "id" | "display_number" | "balance_due_minor" | "total_minor">;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPaid?: (order: Order) => void;
}) {
  const { t } = useI18n();
  const methods = useApi<PaymentMethod[]>(["payment-methods"], "/payments/methods");
  const [methodId, setMethodId] = useState<string | null>(null);
  const [amount, setAmount] = useState(minorToInput(order.balance_due_minor));
  const [tendered, setTendered] = useState("");
  const [reference, setReference] = useState("");
  // One key per dialog session: double clicks and retries cannot record twice.
  const [idempotencyKey] = useState(() => newIdempotencyKey("pay"));

  const method = methods.data?.find((m) => m.id === methodId) ?? methods.data?.[0];
  const amountMinor = parseMoney(amount);
  const tenderedMinor = tendered ? parseMoney(tendered) : amountMinor;
  const change = method?.kind === "CASH" && amountMinor !== null && tenderedMinor !== null ? tenderedMinor - amountMinor : 0;

  const problems = useMemo(() => {
    const list: string[] = [];
    if (amountMinor === null || amountMinor <= 0) list.push("Enter a valid amount.");
    else if (amountMinor > order.balance_due_minor) list.push("The amount is more than the balance due.");
    if (method?.kind === "CASH" && tenderedMinor !== null && amountMinor !== null && tenderedMinor < amountMinor) {
      list.push("Cash tendered is less than the amount.");
    }
    return list;
  }, [amountMinor, tenderedMinor, method, order.balance_due_minor]);

  const pay = useApiMutation(
    () =>
      api<Order>(`/orders/${order.id}/payments`, {
        method: "POST",
        idempotencyKey,
        body: {
          payment_method_id: method!.id,
          amount_minor: amountMinor,
          amount_tendered_minor: method?.kind === "CASH" ? tenderedMinor : undefined,
          reference: reference.trim() || undefined,
        },
      }),
    {
      invalidate: ["orders", "order", "tables", "dashboard", "kitchen"],
      success: (o) => (o.payment_status === "PAID" ? `Order #${o.display_number} is paid` : "Payment recorded"),
      onSuccess: (o) => {
        // With onPaid the parent decides what happens next (and closes the dialog);
        // onOpenChange(false) alone means "dismissed without paying".
        if (onPaid) onPaid(o);
        else onOpenChange(false);
      },
    },
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !pay.isPending && onOpenChange(next)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {t("Pay")} · #{order.display_number}
          </DialogTitle>
          <DialogDescription>
            Balance due <span className="font-semibold text-foreground">{formatMoney(order.balance_due_minor)}</span>
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Payment method">
          {(methods.data ?? []).map((m) => {
            const Icon = ICONS[m.kind];
            const selected = method?.id === m.id;
            return (
              <button
                key={m.id}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => setMethodId(m.id)}
                className={cn(
                  "flex flex-col items-center gap-1 rounded-lg border px-2 py-3 text-xs font-medium transition-colors hover:bg-accent",
                  selected && "border-primary bg-accent text-accent-foreground ring-2 ring-primary/30",
                )}
              >
                <Icon className="size-5" aria-hidden />
                <span className="line-clamp-2 text-center">{m.name}</span>
              </button>
            );
          })}
        </div>
        <FormField label="Amount (฿)" htmlFor="pay-amount">
          <Input id="pay-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </FormField>
        {method?.kind === "CASH" ? (
          <div className="grid gap-2">
            <FormField label="Cash received (฿)" htmlFor="pay-tendered" hint="Leave empty for the exact amount.">
              <Input
                id="pay-tendered"
                inputMode="decimal"
                placeholder={amount}
                value={tendered}
                onChange={(e) => setTendered(e.target.value)}
              />
            </FormField>
            <div className="flex flex-wrap gap-2">
              {QUICK_CASH.map((v) => (
                <Button key={v} type="button" variant="outline" size="sm" onClick={() => setTendered(minorToInput(v))}>
                  {formatMoney(v)}
                </Button>
              ))}
            </div>
            {change > 0 ? (
              <p className="rounded-md bg-accent px-3 py-2 text-sm">
                Change to give: <span className="font-semibold">{formatMoney(change)}</span>
              </p>
            ) : null}
          </div>
        ) : method ? (
          <FormField label="Reference (optional)" htmlFor="pay-ref" hint="Slip or transaction number from the terminal.">
            <Input id="pay-ref" value={reference} maxLength={100} onChange={(e) => setReference(e.target.value)} />
          </FormField>
        ) : null}
        {method?.is_simulated ? (
          <p className="flex gap-2 rounded-md border px-3 py-2 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            SmartPOS records this payment locally (simulated). No money is transferred and no payment provider confirms
            it — collect the payment on your cash drawer, card terminal or QR app.
          </p>
        ) : null}
        {problems.length && amount ? (
          <p role="alert" className="text-sm text-status-critical">
            {problems[0]}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pay.isPending}>
            {t("Cancel")}
          </Button>
          <Button onClick={() => pay.mutate(undefined)} disabled={!method || problems.length > 0 || pay.isPending}>
            {pay.isPending ? <Loader2 className="animate-spin" /> : null}
            Record {amountMinor ? formatMoney(amountMinor) : "payment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
