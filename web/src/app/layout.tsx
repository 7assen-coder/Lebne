import type { Metadata, Viewport } from "next";
import { Fraunces, Syne, Outfit } from "next/font/google";
import "./globals.css";

const brand = Syne({
  subsets: ["latin"],
  variable: "--font-brand",
  weight: ["700", "800"],
  display: "swap",
});

const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600"],
  display: "swap",
});

const sans = Outfit({
  subsets: ["latin"],
  variable: "--font-sans",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Lebne",
  description: "Mauritanian voice for a digital wallet.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#05080c",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${brand.variable} ${display.variable} ${sans.variable}`}
    >
      <body className="antialiased">
        <div className="atmosphere" aria-hidden>
          <div className="horizon" />
          <div className="dune" />
        </div>
        <div className="app-root">{children}</div>
      </body>
    </html>
  );
}
