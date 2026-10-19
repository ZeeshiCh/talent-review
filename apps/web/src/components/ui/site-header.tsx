import type { ReactNode } from "react";
import Brand from "./brand";
import ThemeSwitcher from "./theme-switcher";
export default function SiteHeader({ children }: { children: ReactNode }) {
  return (
    <header className="site-header">
      <Brand />
      <div className="site-header-content">{children}</div>
      <ThemeSwitcher />
    </header>
  );
}
