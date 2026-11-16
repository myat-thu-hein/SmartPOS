"use client";

import { Building2, Plus, Search, ShieldCheck, UserPlus } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { QueryState } from "@/components/shared/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, useApiMutation, usePlatformApi } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime, humanize } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { passwordProblems } from "@/lib/password";
import type { AuditLog, Page, RestaurantRole, RestaurantSummary, User } from "@/types/api";

// "me" refreshes the restaurant switcher after restaurants change.
const INVALIDATE = ["admin-restaurants", "admin-users", "admin-audit", "me"];

export default function AdminPage() {
  const { t } = useI18n();
  return (
    <>
      <PageHeader title={t("Administration")} description="Platform-wide management. Only administrators see this page; every action here is audited." />
      <Tabs defaultValue="restaurants">
        <TabsList>
          <TabsTrigger value="restaurants">Restaurants</TabsTrigger>
          <TabsTrigger value="users">Users</TabsTrigger>
          <TabsTrigger value="audit">Audit log</TabsTrigger>
        </TabsList>
        <TabsContent value="restaurants">
          <Restaurants />
        </TabsContent>
        <TabsContent value="users">
          <Users />
        </TabsContent>
        <TabsContent value="audit">
          <Audit />
        </TabsContent>
      </Tabs>
    </>
  );
}

function Restaurants() {
  const query = usePlatformApi<RestaurantSummary[]>(["admin-restaurants"], "/restaurants");
  const [creating, setCreating] = useState(false);
  const [adding, setAdding] = useState<RestaurantSummary | null>(null);
  const [deactivating, setDeactivating] = useState<RestaurantSummary | null>(null);
  const toggle = useApiMutation(
    (r: RestaurantSummary) => api(`/restaurants/${r.id}/status`, { method: "PATCH", query: { is_active: !r.is_active }, noRestaurant: true }),
    { invalidate: INVALIDATE, success: "Restaurant status updated" },
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>Restaurants</CardTitle>
        <CardDescription>Each restaurant is a separate tenant: its staff, menu, stock and sales are isolated from the others.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <QueryState query={query}>
          {(list) =>
            list.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Restaurant</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {list.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell>
                        <span className="font-medium">{r.name}</span>
                        {r.branch_name ? <span className="text-muted-foreground"> · {r.branch_name}</span> : null}
                        {r.is_demo ? (
                          <Badge variant="warning" className="ml-2">
                            demo data
                          </Badge>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-muted-foreground">{formatDate(r.created_at)}</TableCell>
                      <TableCell>{r.is_active ? <Badge variant="success">Active</Badge> : <Badge variant="secondary">Deactivated</Badge>}</TableCell>
                      <TableCell className="text-right whitespace-nowrap">
                        <Button variant="ghost" size="sm" onClick={() => setAdding(r)}>
                          <UserPlus /> Add member
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={toggle.isPending}
                          onClick={() => (r.is_active ? setDeactivating(r) : toggle.mutate(r))}
                        >
                          {r.is_active ? "Deactivate" : "Activate"}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <EmptyState icon={Building2} title="No restaurants yet" description="Create the first restaurant to start selling." />
            )
          }
        </QueryState>
        <div>
          <Button onClick={() => setCreating(true)}>
            <Plus /> New restaurant
          </Button>
        </div>
      </CardContent>
      {creating ? <CreateRestaurantDialog onClose={() => setCreating(false)} /> : null}
      {adding ? <AddMemberDialog restaurant={adding} onClose={() => setAdding(null)} /> : null}
      <ConfirmDialog
        open={deactivating !== null}
        onOpenChange={(open) => !open && setDeactivating(null)}
        title={`Deactivate ${deactivating?.name ?? ""}?`}
        description="Its staff can no longer sign in to it. No data is deleted, and you can activate it again at any time."
        confirmLabel="Deactivate"
        destructive
        onConfirm={() => (deactivating ? toggle.mutateAsync(deactivating) : undefined)}
      />
    </Card>
  );
}

function CreateRestaurantDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [branch, setBranch] = useState("");
  const [timezone, setTimezone] = useState("Asia/Bangkok");
  const [managerEmail, setManagerEmail] = useState("");
  const save = useApiMutation(
    () =>
      api("/restaurants", {
        method: "POST",
        noRestaurant: true,
        body: { name: name.trim(), branch_name: branch.trim() || null, timezone, manager_email: managerEmail.trim() || null },
      }),
    { invalidate: INVALIDATE, success: "Restaurant created with default payment methods", onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New restaurant</DialogTitle>
          <DialogDescription>Currency THB. Tax, service charge and receipts can be configured in Settings afterwards.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <FormField label="Name" htmlFor="r-name">
            <Input id="r-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </FormField>
          <FormField label="Branch (optional)" htmlFor="r-branch">
            <Input id="r-branch" value={branch} onChange={(e) => setBranch(e.target.value)} />
          </FormField>
          <FormField label="Time zone" htmlFor="r-tz">
            <NativeSelect id="r-tz" value={timezone} onChange={(e) => setTimezone(e.target.value)}>
              {["Asia/Bangkok", "Asia/Ho_Chi_Minh", "Asia/Singapore", "Asia/Kuala_Lumpur", "Asia/Jakarta", "Asia/Tokyo", "UTC"].map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </NativeSelect>
          </FormField>
          <FormField label="Manager email (optional)" htmlFor="r-manager" hint="Must be an existing user; create them on the Users tab first.">
            <Input id="r-manager" type="email" value={managerEmail} onChange={(e) => setManagerEmail(e.target.value)} />
          </FormField>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!name.trim() || save.isPending} onClick={() => save.mutate(undefined)}>
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AddMemberDialog({ restaurant, onClose }: { restaurant: RestaurantSummary; onClose: () => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<RestaurantRole>("MANAGER");
  const save = useApiMutation(
    () => api(`/restaurants/${restaurant.id}/members`, { method: "POST", noRestaurant: true, body: { email: email.trim(), role } }),
    { invalidate: INVALIDATE, success: "Member added", onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add member · {restaurant.name}</DialogTitle>
          <DialogDescription>Gives an existing user access to this restaurant.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <FormField label="User email" htmlFor="m-email">
            <Input id="m-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
          </FormField>
          <FormField label="Role" htmlFor="m-role">
            <NativeSelect id="m-role" value={role} onChange={(e) => setRole(e.target.value as RestaurantRole)}>
              {(["MANAGER", "CASHIER", "KITCHEN"] as const).map((r) => (
                <option key={r} value={r}>
                  {humanize(r)}
                </option>
              ))}
            </NativeSelect>
          </FormField>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!email.trim() || save.isPending} onClick={() => save.mutate(undefined)}>
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Users() {
  const { me } = useAuth();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const query = usePlatformApi<Page<User>>(["admin-users"], "/users/all", { search: search.trim() || undefined, page, page_size: 25 });
  const update = useApiMutation(
    ({ id, ...body }: { id: string; is_active?: boolean; is_platform_admin?: boolean }) =>
      api(`/users/${id}/platform`, { method: "PATCH", noRestaurant: true, body }),
    { invalidate: INVALIDATE, success: "User updated" },
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>Users</CardTitle>
        <CardDescription>All accounts on this installation. Deactivating a user signs them out everywhere.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="relative w-72">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              aria-label="Search users"
              placeholder="Name or email"
              className="pl-9"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <Button onClick={() => setCreating(true)}>
            <Plus /> New user
          </Button>
        </div>
        <QueryState query={query}>
          {(data) => (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>User</TableHead>
                    <TableHead>Last sign-in</TableHead>
                    <TableHead>Administrator</TableHead>
                    <TableHead>Active</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((u) => {
                    const self = u.id === me?.user.id;
                    return (
                      <TableRow key={u.id}>
                        <TableCell>
                          <p className="font-medium">
                            {u.full_name}
                            {self ? <span className="ml-1 text-xs font-normal text-muted-foreground">(you)</span> : null}
                          </p>
                          <p className="text-xs text-muted-foreground">{u.email}</p>
                        </TableCell>
                        <TableCell className="text-muted-foreground">{u.last_login_at ? formatDateTime(u.last_login_at) : "Never"}</TableCell>
                        <TableCell>
                          <Switch
                            aria-label={`Administrator: ${u.email}`}
                            checked={u.is_platform_admin}
                            disabled={self || update.isPending}
                            onCheckedChange={(v) => update.mutate({ id: u.id, is_platform_admin: v })}
                          />
                        </TableCell>
                        <TableCell>
                          <Switch
                            aria-label={`Active: ${u.email}`}
                            checked={u.is_active}
                            disabled={self || update.isPending}
                            onCheckedChange={(v) => update.mutate({ id: u.id, is_active: v })}
                          />
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
              <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
            </>
          )}
        </QueryState>
      </CardContent>
      {creating ? <CreateUserDialog onClose={() => setCreating(false)} /> : null}
    </Card>
  );
}

function CreateUserDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [admin, setAdmin] = useState(false);
  const problems = passwordProblems(password);
  const save = useApiMutation(
    () =>
      api("/users/platform", {
        method: "POST",
        noRestaurant: true,
        body: { full_name: name.trim(), email: email.trim(), password, is_platform_admin: admin },
      }),
    { invalidate: INVALIDATE, success: "User created", onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New user</DialogTitle>
          <DialogDescription>Then add them to a restaurant from the Restaurants tab, or make them an administrator.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <FormField label="Full name" htmlFor="u-name">
            <Input id="u-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </FormField>
          <FormField label="Email" htmlFor="u-email">
            <Input id="u-email" type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} />
          </FormField>
          <FormField label="Initial password" htmlFor="u-password" error={password && problems.length ? problems.join(" ") : undefined} hint="Share it privately.">
            <Input id="u-password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </FormField>
          <Label className="font-normal">
            <Checkbox checked={admin} onCheckedChange={(v) => setAdmin(!!v)} /> Platform administrator
          </Label>
          {admin ? (
            <p className="flex gap-2 text-xs text-muted-foreground">
              <ShieldCheck className="size-4 shrink-0" aria-hidden /> Administrators can see and change every restaurant.
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!name.trim() || !email.trim() || problems.length > 0 || save.isPending} onClick={() => save.mutate(undefined)}>
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Audit() {
  const restaurants = usePlatformApi<RestaurantSummary[]>(["admin-restaurants"], "/restaurants");
  const [restaurantId, setRestaurantId] = useState("");
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const query = usePlatformApi<Page<AuditLog>>(["admin-audit"], "/audit-logs", {
    restaurant_id: restaurantId || undefined,
    action: action.trim() || undefined,
    page,
    page_size: 50,
  });
  const names = new Map((restaurants.data ?? []).map((r) => [r.id, r.name]));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Audit log</CardTitle>
        <CardDescription>Sign-ins, settings, menu and price changes, stock counts, purchasing, payments, refunds, cancellations and administrative actions. Every individual stock movement is also kept in the inventory ledger with who made it.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex flex-wrap gap-2">
          <NativeSelect
            aria-label="Restaurant"
            className="w-56"
            value={restaurantId}
            onChange={(e) => {
              setRestaurantId(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All restaurants</option>
            {(restaurants.data ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </NativeSelect>
          <Input
            aria-label="Action starts with"
            placeholder="Action, e.g. order. or auth."
            className="w-64"
            value={action}
            onChange={(e) => {
              setAction(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <QueryState query={query}>
          {(data) =>
            data.items.length ? (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Time</TableHead>
                      <TableHead>Action</TableHead>
                      <TableHead>Actor</TableHead>
                      <TableHead>Restaurant</TableHead>
                      <TableHead>Details</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((log) => (
                      <TableRow key={log.id}>
                        <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(log.created_at)}</TableCell>
                        <TableCell className="font-mono text-xs">{log.action}</TableCell>
                        <TableCell>{log.actor_email ?? (log.actor_user_id ? "Unknown user" : "System")}</TableCell>
                        <TableCell className="text-muted-foreground">{log.restaurant_id ? (names.get(log.restaurant_id) ?? "—") : "Platform"}</TableCell>
                        <TableCell className="max-w-96">
                          {log.details ? (
                            <code className="block truncate text-xs text-muted-foreground" title={JSON.stringify(log.details, null, 2)}>
                              {JSON.stringify(log.details)}
                            </code>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
              </>
            ) : (
              <p className="py-6 text-center text-sm text-muted-foreground">No audit entries match.</p>
            )
          }
        </QueryState>
      </CardContent>
    </Card>
  );
}
