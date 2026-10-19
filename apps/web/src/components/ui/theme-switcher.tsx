"use client";
import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import Icon, { type IconName } from "./icon";

const subscribe = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;
const choices: { value: string; label: string; icon: IconName }[] = [
  { value: "light", label: "Light", icon: "sun" },
  { value: "dark", label: "Dark", icon: "moon" },
  { value: "system", label: "System", icon: "monitor" },
];
export default function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    subscribe,
    clientSnapshot,
    serverSnapshot,
  );
  const preference =
    mounted && (theme === "light" || theme === "dark") ? theme : "system";
  return (
    <div className="theme-switcher" role="group" aria-label="Color theme">
      {choices.map((choice) => (
        <button
          key={choice.value}
          type="button"
          aria-label={`${choice.label} theme`}
          title={`${choice.label} theme`}
          aria-pressed={preference === choice.value}
          disabled={!mounted}
          onClick={() => setTheme(choice.value)}
        >
          <Icon name={choice.icon} />
          <span>{choice.label}</span>
        </button>
      ))}
    </div>
  );
}
