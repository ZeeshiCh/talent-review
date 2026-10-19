"use client";
import type { ReactNode } from "react";
import { ThemeProvider as Provider } from "next-themes";

export default function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <Provider
      attribute="data-theme"
      defaultTheme="system"
      enableSystem
      storageKey="talent-review.theme"
      disableTransitionOnChange
    >
      {children}
    </Provider>
  );
}
