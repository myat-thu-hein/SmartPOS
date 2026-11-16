"use client";

import { KeyRound, Pencil, Plus, UserCog } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { QueryState } from "@/components/shared/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, humanize } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { passwordProblems } from "@/lib/password";
import type { RestaurantRole, Staff } from "@/types/api";

const ROLE_HELP: Record<RestaurantRole, string> = {
  MANAGER: "Everything in this restaurant: menu, stock, purchasing, reports, forecasts, staff (cashiers and kitchen).",
  CASHIER: "POS, orders, payments, tables and customers. Discounts up to the configured limit; no refunds.",
  KITCHEN: "Kitchen display only: see tickets and mark them preparing, ready and completed.",
};

export default function UsersPage() {
  const { t } = useI18n();
  const { me } = useAuth();
  const isAdmin = !!me?.user.is_platform_admin;
  const [editing, setEditing] = useState<Staff | "new" | null>(null);
  const [resetting, setResetting] = useState<Staff | null>(null);
  const query = useApi<Staff[]>(["staff"], "/users");
  // Only administrators may grant or change the manager role.
  const manageable = (s: Staff) => isAdmin || s.role !== "MANAGER";

  return (
    <>
      <PageHeader
        title={t("User Management")}
        description="Staff accounts for this restaurant. Each person signs in with their own account; roles decide what they can do."
        actions={
          <Button onClick={() => setEditing("new")}>
            <Plus /> Add staff
          </Button>
        }
      />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Card>
          <CardContent>
            <QueryState query={query}>
              {(staff) =>
                staff.length ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Name</TableHead>
                        <TableHead>Role</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Last sign-in</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {staff.map((s) => {
                        const active = s.membership_active && s.user_active;
                        const self = s.user_id === me?.user.id;
                        return (
                          <TableRow key={s.membership_id} className={active ? undefined : "opacity-60"}>
                            <TableCell>
                              <p className="font-medium">
                                {s.full_name}
                                {self ? <span className="ml-1 text-xs font-normal text-muted-foreground">(you)</span> : null}
                              </p>
                              <p className="text-xs text-muted-foreground">{s.email}</p>
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline">{humanize(s.role)}</Badge>
                            </TableCell>
                            <TableCell>
                              {active ? (
                                <Badge variant="success">Active</Badge>
                              ) : (
                                <Badge variant="secondary">{s.user_active ? "Deactivated here" : "Account disabled"}</Badge>
                              )}
                            </TableCell>
                            <TableCell className="text-muted-foreground">{s.last_login_at ? formatDateTime(s.last_login_at) : "Never"}</TableCell>
                            <TableCell className="text-right whitespace-nowrap">
                              {manageable(s) ? (
                                <>
                                  <Button variant="ghost" size="icon-sm" aria-label={`Edit ${s.full_name}`} onClick={() => setEditing(s)}>
                                    <Pencil />
                                  </Button>
                                  {!self ? (
                                    <Button variant="ghost" size="icon-sm" aria-label={`Set password for ${s.full_name}`} onClick={() => setResetting(s)}>
                                      <KeyRound />
                                    </Button>
                                  ) : null}
                                </>
                              ) : (
                                <span className="text-xs text-muted-foreground">Admin only</span>
                              )}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                ) : (
                  <EmptyState icon={UserCog} title="No staff yet" description="Add the cashiers and kitchen staff who use SmartPOS." />
                )
              }
            </QueryState>
          </CardContent>
        </Card>
        <Card className="content-start">
          <CardHeader>
            <CardTitle>Roles</CardTitle>
            <CardDescription>Permissions are enforced by the server, not just hidden in the interface.</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-3 text-sm">
              {(Object.keys(ROLE_HELP) as RestaurantRole[]).map((role) => (
                <div key={role}>
                  <dt className="font-medium">{humanize(role)}</dt>
                  <dd className="text-muted-foreground">{ROLE_HELP[role]}</dd>
                </div>
              ))}
              <div>
                <dt className="font-medium">Administrator</dt>
                <dd className="text-muted-foreground">Platform-wide: restaurants, all users, audit logs, and the manager role.</dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      </div>
      {editing ? <StaffDialog staff={editing === "new" ? null : editing} isAdmin={isAdmin} selfId={me?.user.id} onClose={() => setEditing(null)} /> : null}
      {resetting ? <PasswordDialog staff={resetting} onClose={() => setResetting(null)} /> : null}
    </>
  );
}

function StaffDialog({
  staff,
  isAdmin,
  selfId,
  onClose,
}: {
  staff: Staff | null;
  isAdmin: boolean;
  selfId?: string;
  onClose: () => void;
}) {
  const [fullName, setFullName] = useState(staff?.full_name ?? "");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<RestaurantRole>(staff?.role ?? "CASHIER");
  const [active, setActive] = useState(staff?.membership_active ?? true);
  const self = staff?.user_id === selfId;
  const problems = staff ? [] : passwordProblems(password);
  const save = useApiMutation(
    () =>
      staff
        ? api(`/users/${staff.user_id}`, {
            method: "PATCH",
            body: { full_name: fullName.trim(), ...(self ? {} : { role, is_active: active }) },
          })
        : api("/users", { method: "POST", body: { full_name: fullName.trim(), email: email.trim(), password, role } }),
    { invalidate: ["staff"], success: staff ? "Staff member updated" : "Staff account created", onSuccess: onClose },
  );
  const roles: RestaurantRole[] = isAdmin ? ["MANAGER", "CASHIER", "KITCHEN"] : ["CASHIER", "KITCHEN"];
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{staff ? `Edit ${staff.full_name}` : "Add staff"}</DialogTitle>
          {!staff ? (
            <DialogDescription>
              Share the initial password privately. They can change it after signing in, from the account menu.
            </DialogDescription>
          ) : null}
        </DialogHeader>
        <div className="grid gap-3">
          <FormField label="Full name" htmlFor="st-name">
            <Input id="st-name" value={fullName} onChange={(e) => setFullName(e.target.value)} autoFocus />
          </FormField>
          {!staff ? (
            <>
              <FormField label="Email" htmlFor="st-email">
                <Input id="st-email" type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} />
              </FormField>
              <FormField label="Initial password" htmlFor="st-password" hint="At least 8 characters, mixing letters with numbers or symbols." error={password && problems.length ? problems.join(" ") : undefined}>
                <Input id="st-password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </FormField>
            </>
          ) : null}
          <FormField label="Role" htmlFor="st-role" hint={self ? "You cannot change your own role." : ROLE_HELP[role]}>
            <NativeSelect id="st-role" value={role} disabled={self} onChange={(e) => setRole(e.target.value as RestaurantRole)}>
              {roles.map((r) => (
                <option key={r} value={r}>
                  {humanize(r)}
                </option>
              ))}
            </NativeSelect>
          </FormField>
          {staff && !self ? (
            <Label className="font-normal">
              <Switch checked={active} onCheckedChange={setActive} /> Can sign in to this restaurant
            </Label>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!fullName.trim() || (!staff && (!email.trim() || problems.length > 0)) || save.isPending}
            onClick={() => save.mutate(undefined)}
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PasswordDialog({ staff, onClose }: { staff: Staff; onClose: () => void }) {
  const [password, setPassword] = useState("");
  const problems = passwordProblems(password);
  const save = useApiMutation(
    () => api(`/users/${staff.user_id}/password`, { method: "POST", body: { new_password: password } }),
    { invalidate: ["staff"], success: "Password updated; their existing sessions were signed out", onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Set password · {staff.full_name}</DialogTitle>
          <DialogDescription>This signs {staff.full_name} out everywhere. Share the new password privately.</DialogDescription>
        </DialogHeader>
        <FormField label="New password" htmlFor="pw-new" error={password && problems.length ? problems.join(" ") : undefined}>
          <Input id="pw-new" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
        </FormField>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={problems.length > 0 || save.isPending} onClick={() => save.mutate(undefined)}>
            Set password
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
