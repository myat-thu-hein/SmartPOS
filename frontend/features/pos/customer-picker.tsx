"use client";

import { Loader2, Search, UserPlus, UserRound, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { useApi, useApiMutation } from "@/hooks/use-api";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import type { CustomerAny, Page } from "@/types/api";

export interface SelectedCustomer {
  id: string;
  name: string;
  loyaltyBalance: number;
}

function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

export function CustomerPicker({
  value,
  onChange,
}: {
  value: SelectedCustomer | null;
  onChange: (customer: SelectedCustomer | null) => void;
}) {
  const { t } = useI18n();
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const term = useDebounced(search.trim());
  const results = useApi<Page<CustomerAny>>(["customers", "lookup"], term.length >= 2 ? "/customers" : null, {
    search: term,
    page_size: 6,
  });

  if (value) {
    return (
      <div className="flex items-center gap-2 rounded-lg border bg-accent/60 px-3 py-2 text-sm">
        <UserRound className="size-4 text-muted-foreground" aria-hidden />
        <span className="flex-1 truncate font-medium">{value.name}</span>
        <span className="text-xs text-muted-foreground">{value.loyaltyBalance} pts</span>
        <Button variant="ghost" size="icon-sm" aria-label="Remove customer" onClick={() => onChange(null)}>
          <X />
        </Button>
      </div>
    );
  }
  return (
    <div className="relative grid gap-1">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" aria-hidden />
          <Input
            aria-label="Find customer"
            placeholder={`${t("Customer")}: name or phone (${t("Guest")} if empty)`}
            className="pl-8"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {can("customers:create") ? (
          <Button variant="outline" size="icon" aria-label="New customer" onClick={() => setCreating(true)}>
            <UserPlus />
          </Button>
        ) : null}
      </div>
      {term.length >= 2 ? (
        <div className="absolute top-10 z-20 w-full rounded-md border bg-popover p-1 shadow-md">
          {results.isPending ? (
            <p className="flex items-center gap-2 px-2 py-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Searching…
            </p>
          ) : results.data?.items.length ? (
            results.data.items.map((c) => (
              <button
                key={c.id}
                type="button"
                className="flex w-full items-center justify-between rounded-sm px-2 py-2 text-left text-sm hover:bg-accent"
                onClick={() => {
                  onChange({ id: c.id, name: c.name, loyaltyBalance: c.loyalty_balance });
                  setSearch("");
                }}
              >
                <span>
                  {c.name}
                  <span className="ml-2 text-xs text-muted-foreground">
                    {"phone_masked" in c ? c.phone_masked : c.phone}
                  </span>
                </span>
                <span className="text-xs text-muted-foreground">{c.loyalty_balance} pts</span>
              </button>
            ))
          ) : (
            <p className="px-2 py-2 text-sm text-muted-foreground">No customer found.</p>
          )}
        </div>
      ) : null}
      {creating ? (
        <NewCustomerDialog
          initial={search}
          onClose={() => setCreating(false)}
          onCreated={(c) => {
            onChange(c);
            setSearch("");
            setCreating(false);
          }}
        />
      ) : null}
    </div>
  );
}

function NewCustomerDialog({
  initial,
  onClose,
  onCreated,
}: {
  initial: string;
  onClose: () => void;
  onCreated: (c: SelectedCustomer) => void;
}) {
  const looksLikePhone = /^[+\d\s-]{6,}$/.test(initial);
  const [name, setName] = useState(looksLikePhone ? "" : initial);
  const [phone, setPhone] = useState(looksLikePhone ? initial : "");
  const [error, setError] = useState<string | null>(null);
  const create = useApiMutation(
    () => api<CustomerAny>("/customers", { method: "POST", body: { name, phone: phone || null } }),
    {
      silent: true,
      invalidate: ["customers"],
      success: "Customer added",
      onSuccess: (c) => onCreated({ id: c.id, name: c.name, loyaltyBalance: c.loyalty_balance }),
    },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>New customer</DialogTitle>
          <DialogDescription>Customers earn loyalty points on paid orders.</DialogDescription>
        </DialogHeader>
        <form
          className="grid gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            create.mutate(undefined, {
              onError: (err) => setError(err instanceof ApiError ? err.message : "Could not add customer."),
            });
          }}
        >
          <FormField label="Name" htmlFor="cust-name">
            <Input id="cust-name" required value={name} maxLength={150} onChange={(e) => setName(e.target.value)} autoFocus />
          </FormField>
          <FormField label="Phone" htmlFor="cust-phone" error={error ?? undefined}>
            <Input id="cust-phone" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </FormField>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              {create.isPending ? <Loader2 className="animate-spin" /> : null} Add customer
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
