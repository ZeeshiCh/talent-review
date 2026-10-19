import type { Metadata } from "next";
import "./globals.css";
import "./themes.css";
import "../components/ui/controls.css";
import ThemeProvider from "../components/ui/theme-provider";
export const metadata: Metadata = {
  title: "Talent Review",
  description: "Human-led interview review",
  referrer: "no-referrer",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
