import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingRows } from "@/components/shared/query-state";

import { ForecastingScreen } from "./forecasting-screen";

export const metadata: Metadata = { title: "Forecasting" };

export default function ForecastingPage() {
  return (
    <Suspense fallback={<LoadingRows rows={8} />}>
      <ForecastingScreen />
    </Suspense>
  );
}
