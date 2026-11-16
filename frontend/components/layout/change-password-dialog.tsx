"use client";

import { useState } from "react";

import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, useApiMutation } from "@/hooks/use-api";
import { passwordProblems } from "@/lib/password";

export function ChangePasswordDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const problems = passwordProblems(next);
  const mismatch = confirm.length > 0 && confirm !== next;
  const close = () => {
    setCurrent("");
    setNext("");
    setConfirm("");
    onOpenChange(false);
  };
  const save = useApiMutation(
    () => api("/auth/change-password", { method: "POST", body: { current_password: current, new_password: next } }),
    { success: "Password changed. Your other sessions were signed out.", onSuccess: close },
  );
  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : close())}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Change password</DialogTitle>
          <DialogDescription>You stay signed in here; other devices are signed out.</DialogDescription>
        </DialogHeader>
        <form
          className="grid gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (current && !problems.length && !mismatch && confirm) save.mutate(undefined);
          }}
        >
          <FormField label="Current password" htmlFor="cp-current">
            <Input id="cp-current" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} autoFocus />
          </FormField>
          <FormField
            label="New password"
            htmlFor="cp-new"
            hint="At least 8 characters, mixing letters with numbers or symbols."
            error={next && problems.length ? problems.join(" ") : undefined}
          >
            <Input id="cp-new" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
          </FormField>
          <FormField label="Confirm new password" htmlFor="cp-confirm" error={mismatch ? "The passwords do not match." : undefined}>
            <Input id="cp-confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </FormField>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={close}>
              Cancel
            </Button>
            <Button type="submit" disabled={!current || !confirm || problems.length > 0 || mismatch || save.isPending}>
              Change password
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
