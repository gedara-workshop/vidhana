import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const metadata: Metadata = {
  metadataBase: new URL("https://gedara-workshop.github.io"),
  title: {
    default: "Vidhana — what the rule actually is",
    template: "%s · Vidhana",
  },
  description:
    "Search Sri Lankan Inland Revenue tax and VAT gazettes, resolved into what the rule " +
    "currently is rather than the documents that mention it.",
  openGraph: {
    title: "Vidhana",
    description: "Sri Lankan IRD tax and VAT gazettes, resolved into what the rule currently is.",
    type: "website",
  },
};

/** The masthead, set the way the gazette sets its own: a double rule, the
 *  imprint line above, the title centred. It is the one piece of pure costume
 *  in the design, and it earns its place by telling a first-time reader what
 *  kind of document they are looking at before they read a word of it. */
function Masthead() {
  return (
    <header className="border-b-[3px] border-double px-6 pb-5 pt-7 text-center md:px-14"
            style={{ borderColor: "var(--ink)" }}>
      <p className="label">Inland Revenue · 2006–2026 · 144 documents</p>
      <Link href="/" className="mt-2 block text-[38px] font-bold leading-none tracking-[0.01em] md:text-[44px]">
        Vidhana
      </Link>
      <p className="mt-[6px] text-[15.5px] italic opacity-70">What the rule actually is</p>
    </header>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,300;0,400;0,600;0,700;1,400;1,600&family=IBM+Plex+Mono:wght@400;500&display=swap"
        />
        <link rel="icon" href={`${BASE}/favicon.svg`} type="image/svg+xml" />
        <link
          rel="alternate"
          type="application/atom+xml"
          title="Vidhana — all IRD gazettes"
          href={`${BASE}/feeds/all.xml`}
        />
      </head>
      <body className="min-h-screen">
        <Masthead />
        {children}
        <footer className="mx-auto max-w-[820px] px-6 pb-12 md:px-14">
          <p className="border-t pt-4 text-[13px] italic leading-relaxed opacity-60"
             style={{ borderColor: "var(--hair)" }}>
            Summaries are machine-written; the gazette is the source of truth, and every result
            links to the original PDF. “In force” means not rescinded by another gazette in this
            corpus — weaker than a legal determination. Not legal advice.{" "}
            <Link className="link" href="/feeds/">Feeds</Link> ·{" "}
            <a className="link" href="https://github.com/gedara-workshop/vidhana" rel="noopener">
              Source and method
            </a>
          </p>
        </footer>
      </body>
    </html>
  );
}
