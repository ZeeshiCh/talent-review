import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../app/themes.css", import.meta.url), "utf8");
const palettes = [
  ...css.matchAll(/\[data-theme="(light|dark)"\]\s*\{([^}]+)\}/g),
];
function luminance(hex: string) {
  const rgb = hex.match(/[a-f0-9]{2}/gi)!.map((channel) => {
    const value = parseInt(channel, 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}
const pairs = [
  ["ink", "paper"],
  ["ink", "surface"],
  ["muted", "surface"],
  ["muted", "paper"],
  ["eyebrow", "paper"],
  ["green", "surface"],
  ["on-accent", "green"],
  ["on-accent", "accent-hover"],
  ["warning-text", "warning-bg"],
  ["badge-text", "badge-bg"],
];
assert.equal(palettes.length, 2, "Both theme palettes must be defined");
for (const [, theme, body] of palettes) {
  const tokens = Object.fromEntries(
    [...body.matchAll(/--([a-z-]+):\s*(#[a-f0-9]{6});/gi)].map(
      ([, name, value]) => [name, value],
    ),
  );
  for (const [foreground, background] of pairs) {
    test(`${theme} theme: ${foreground} text on ${background} stays readable`, () => {
      assert.ok(
        tokens[foreground] && tokens[background],
        "Both color tokens exist",
      );
      const a = luminance(tokens[foreground]);
      const b = luminance(tokens[background]);
      const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
      assert.ok(
        ratio >= 4.5,
        `Text contrast is ${ratio.toFixed(2)}:1; expected at least 4.5:1`,
      );
    });
  }
}
