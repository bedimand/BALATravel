import type { Metadata } from "next";
import { Outfit, Inter } from "next/font/google";
import "maplibre-gl/dist/maplibre-gl.css";

import "./globals.css";

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-display"
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-body"
});

export const metadata: Metadata = {
  title: "BALATravel",
  description: "Copiloto de planejamento de viagens com mapa, agenda e chat."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body className={`${outfit.variable} ${inter.variable}`}>{children}</body>
    </html>
  );
}
