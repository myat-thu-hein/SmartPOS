"use client";

import { useState } from "react";

import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, useApiMutation } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";

export function CustomerDialog({
  customer,
  onClose,
}: {
  customer?: { id: string; name: string; phone: string | null; email: string | null; notes: string | null };
  onClose: () => void;
}) {
  const { can } = useAuth();
  const [name, setName] = useState(customer?.name ?? "");
  const [phone, setPhone] = useState(customer?.phone ?? "");
  const [email, setEmail] = useState(customer?.email ?? "");
  const [notes, setNotes] = useState(customer?.notes ?? "");
  const full = can("customers:write");
  const save = useApiMutation(
    () =>
      api(customer ? `/customers/${customer.id}` : "/customers", {
        method: customer ? "PATCH" : "POST",
        body: {
          name: name.trim(),
          phone: phone.trim() || null,
          ...(full ? { email: email.trim() || null, notes: notes.trim() || null } : {}),
        },
      }),
    { invalidate: ["customers", "customer"], success: customer ? "Customer updated" : "Customer added", onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{customer ? "Edit customer" : "New customer"}</DialogTitle>
          <DialogDescription>Only collect the details you need. Phone numbers must be unique.</DialogDescription>
        </DialogHeader>
        <form
          className="grid gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined);
          }}
        >
          <FormField label="Name" htmlFor="c-name">
            <Input id="c-name" required maxLength={150} value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </FormField>
          <FormField label="Phone" htmlFor="c-phone">
            <Input id="c-phone" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </FormField>
          {full ? (
            <>
              <FormField label="Email" htmlFor="c-email">
                <Input id="c-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </FormField>
              <FormField label="Notes" htmlFor="c-notes" hint="Visible to managers only.">
                <Textarea id="c-notes" value={notes} maxLength={5000} onChange={(e) => setNotes(e.target.value)} />
              </FormField>
            </>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || save.isPending}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
