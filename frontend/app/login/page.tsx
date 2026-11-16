import type { Metadata } from "next";

import { AuthLayout } from "@/components/layout/auth-layout";
import { AuthProvider } from "@/lib/auth";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <AuthProvider>
      <AuthLayout title="Welcome back" subtitle="Sign in to your restaurant workspace.">
        <LoginForm showDemoHint={process.env.NODE_ENV !== "production"} />
      </AuthLayout>
    </AuthProvider>
  );
}
