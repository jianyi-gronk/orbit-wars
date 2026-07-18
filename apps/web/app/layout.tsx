import type { Metadata } from "next";
import { headers } from "next/headers";
import type { ReactNode } from "react";

import { GlobalInteractionFX } from "../components/product/GlobalInteractionFX";

import "@orbit-wars/design-tokens/tokens.css";
import "./globals.css";
import "./orbit-language.css";
import "./motion.css";
import "./product.css";
import "./game-ux.css";
import "./battle/demo/tactical.css";
import "./replay.css";

export const metadata: Metadata = {
  description: "人类与 Agent 共用同一片轨道战场。",
  title: {
    default: "Orbit Wars",
    template: "%s · Orbit Wars",
  },
};

export default async function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  const locale = (await headers()).get("x-orbit-locale") === "en" ? "en" : "zh-CN";
  return (
    <html lang={locale}>
      <body>
        <GlobalInteractionFX />
        {children}
      </body>
    </html>
  );
}
