"use client";

import { Loader2, Printer } from "lucide-react";
import { useParams } from "next/navigation";

import { ErrorState } from "@/components/shared/query-state";
import { Button } from "@/components/ui/button";
import { useApi } from "@/hooks/use-api";
import { AuthProvider } from "@/lib/auth";
import { formatDateTime, formatMoney, formatPercentBps } from "@/lib/format";
import type { Receipt } from "@/types/api";

export function ReceiptScreen() {
  return (
    <AuthProvider>
      <ReceiptView />
    </AuthProvider>
  );
}

function Line({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className={`flex justify-between gap-3 ${bold ? "text-base font-bold" : ""}`}>
      <span>{label}</span>
      <span className="tabular">{value}</span>
    </div>
  );
}

function ReceiptView() {
  const { id } = useParams<{ id: string }>();
  const query = useApi<Receipt>(["receipt", id], `/orders/${id}/receipt`);
  if (query.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 size-5 animate-spin" /> Loading receipt…
      </div>
    );
  }
  if (query.isError || !query.data) {
    return (
      <div className="mx-auto max-w-md py-16">
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      </div>
    );
  }
  const r = query.data;
  const tz = r.timezone;
  return (
    <div className="min-h-dvh bg-muted/40 py-8">
      <div className="no-print mx-auto mb-4 flex max-w-[340px] justify-end">
        <Button onClick={() => window.print()}>
          <Printer /> Print
        </Button>
      </div>
      <article className="print-area mx-auto w-[302px] bg-white p-4 font-sans text-[12px] tabular leading-relaxed text-black shadow-md">
        <header className="text-center">
          <p className="text-[15px] font-bold">{r.restaurant_name}</p>
          {r.branch_name ? <p>{r.branch_name}</p> : null}
          {r.legal_name ? <p>{r.legal_name}</p> : null}
          {r.address ? <p className="whitespace-pre-line">{r.address}</p> : null}
          {r.phone ? <p>Tel {r.phone}</p> : null}
          {r.tax_id ? <p>Tax ID / เลขประจำตัวผู้เสียภาษี {r.tax_id}</p> : null}
          {r.header ? <p className="mt-1 whitespace-pre-line">{r.header}</p> : null}
        </header>
        <hr className="my-2 border-dashed border-black" />
        <Line label="Receipt / ใบเสร็จ" value={`#${r.display_number}`} />
        <Line label="Date" value={formatDateTime(r.paid_at ?? r.created_at, tz)} />
        <Line label={r.order_type === "DINE_IN" ? "Table / โต๊ะ" : "Order type"} value={r.table_name ?? "Takeaway / กลับบ้าน"} />
        {r.cashier_name ? <Line label="Cashier" value={r.cashier_name} /> : null}
        {r.customer_name ? <Line label="Customer" value={r.customer_name} /> : null}
        <hr className="my-2 border-dashed border-black" />
        {r.lines.map((line, i) => (
          <div key={i} className="mb-1">
            <div className="flex justify-between gap-2">
              <span>
                {line.quantity} × {line.name}
              </span>
              <span className="tabular">{formatMoney(line.line_total_minor)}</span>
            </div>
            {line.modifiers.length ? <p className="pl-4 text-[11px]">{line.modifiers.join(", ")}</p> : null}
            {line.quantity > 1 ? <p className="pl-4 text-[11px]">@ {formatMoney(line.unit_price_minor)}</p> : null}
          </div>
        ))}
        <hr className="my-2 border-dashed border-black" />
        <Line label="Subtotal / ยอดรวม" value={formatMoney(r.subtotal_minor)} />
        {r.discount_minor ? <Line label={r.discount_label ?? "Discount"} value={`-${formatMoney(r.discount_minor)}`} /> : null}
        {r.loyalty_discount_minor ? (
          <Line label={`Points (${r.loyalty_points_redeemed})`} value={`-${formatMoney(r.loyalty_discount_minor)}`} />
        ) : null}
        {r.service_charge_minor ? (
          <Line label={`Service ${formatPercentBps(r.service_charge_bps)}`} value={formatMoney(r.service_charge_minor)} />
        ) : null}
        {!r.prices_include_tax ? <Line label={`${r.tax_label} ${formatPercentBps(r.tax_rate_bps)}`} value={formatMoney(r.tax_minor)} /> : null}
        <Line label="TOTAL / ยอดสุทธิ" value={formatMoney(r.total_minor)} bold />
        {r.prices_include_tax ? (
          <p className="text-[11px]">
            Includes {r.tax_label} {formatPercentBps(r.tax_rate_bps)}: {formatMoney(r.tax_minor)}
          </p>
        ) : null}
        <hr className="my-2 border-dashed border-black" />
        {r.payments.map((p, i) => (
          <div key={i}>
            <Line label={p.method_name} value={formatMoney(p.amount_minor)} />
            {p.amount_tendered_minor && p.change_minor ? (
              <>
                <Line label="  Received" value={formatMoney(p.amount_tendered_minor)} />
                <Line label="  Change / เงินทอน" value={formatMoney(p.change_minor)} />
              </>
            ) : null}
          </div>
        ))}
        <Line label="Payment status" value={r.payment_status.replace("_", " ")} />
        {r.amount_refunded_minor ? <Line label="Refunded" value={`-${formatMoney(r.amount_refunded_minor)}`} /> : null}
        {r.balance_due_minor ? <Line label="Balance due" value={formatMoney(r.balance_due_minor)} bold /> : null}
        {r.loyalty_points_earned ? <p className="mt-1">Points earned: {r.loyalty_points_earned}</p> : null}
        {r.simulated_payment_notice ? <p className="mt-2 text-[10px]">{r.simulated_payment_notice}</p> : null}
        {r.footer ? <p className="mt-3 text-center whitespace-pre-line">{r.footer}</p> : null}
        <p className="mt-2 text-center text-[10px]">Powered by SmartPOS AI</p>
      </article>
    </div>
  );
}
