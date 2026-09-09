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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
        />
        <link rel="icon" href={`${BASE}/favicon.svg`} type="image/svg+xml" />
        <link
          rel="alternate"
          type="application/atom+xml"
          title="Vidhana — all IRD gazettes"
          href={`${BASE}/feeds/all.xml`}
        />
      </head>
      <body className="min-h-screen antialiased text-[14px] leading-normal">
        {children}
        <footer
          className="px-6 py-6 text-[11.5px] leading-relaxed"
          style={{ color: "var(--dim)", borderTop: "1px solid var(--line)" }}
        >
          <div className="mx-auto max-w-5xl">
            Summaries are machine-written; the gazette is the source of truth, and every
            result links to the original PDF. “In force” means{" "}
            <em>not rescinded by another gazette in this corpus</em> — weaker than a legal
            determination. Not legal advice.{" "}
            <Link className="link" href="/feeds/">
              Feeds
            </Link>{" "}
            ·{" "}
            <a
              className="link"
              href="https://github.com/gedara-workshop/vidhana"
              rel="noopener"
            >
              Source and method
            </a>
          </div>
        </footer>
      </body>
    </html>
  );
}
