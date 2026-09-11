import type { Metadata } from "next";
import Link from "next/link";

import ThemeToggle from "@/components/ThemeToggle";
import { ORIGIN } from "@/lib/site";
import "./globals.css";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/* Search Console ownership, by the HTML-tag method — the only one that works
 * for a URL-prefix property on a project Pages site, where the origin root is
 * not ours. The token is public by design (it sits in the page), so it comes
 * from a repository *variable*, not a secret, and an unset one emits nothing. */
const GOOGLE_VERIFICATION = process.env.GOOGLE_SITE_VERIFICATION?.trim() || undefined;

export const metadata: Metadata = {
  metadataBase: new URL(ORIGIN),
  title: {
    default: "Vidhana — what the rule actually is",
    template: "%s · Vidhana",
  },
  description:
    "Search Sri Lankan Inland Revenue tax and VAT gazettes, resolved into what the rule " +
    "currently is rather than the documents that mention it.",
  verification: GOOGLE_VERIFICATION ? { google: GOOGLE_VERIFICATION } : undefined,
  openGraph: {
    title: "Vidhana",
    description: "Sri Lankan IRD tax and VAT gazettes, resolved into what the rule currently is.",
    type: "website",
  },
};

/* Applied before first paint. Without it a viewer who chose light gets a frame
 * of dark while React hydrates, which on a full-bleed dark UI is a flash you
 * cannot miss. Inline and tiny on purpose — it must not wait for a network
 * round trip. */
const THEME_SCRIPT = `try{var t=localStorage.getItem("vidhana-theme");
if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}`;

function Logo() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="1.5" y="1.5" width="21" height="21" rx="6" fill="currentColor" />
      <path d="M7 8.5h10M7 12h10M7 15.5h6" stroke="var(--panel)" strokeWidth="1.9"
            strokeLinecap="round" />
    </svg>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap"
        />
        <link rel="icon" href={`${BASE}/favicon.svg`} type="image/svg+xml" />
        <link rel="alternate" type="application/atom+xml"
              title="Vidhana — all IRD gazettes" href={`${BASE}/feeds/all.xml`} />
      </head>
      <body className="h-screen overflow-hidden">
        <div className="flex h-full flex-col">
          <header className="topbar flex shrink-0 items-center gap-2 px-3">
            <Link href="/" className="flex items-center gap-2 pr-2">
              <Logo />
              <span className="text-[14px] font-bold tracking-tight">Vidhana</span>
            </Link>
            <span className="mx-1 h-4 w-px" style={{ background: "var(--line)" }} />
            <nav className="flex items-center gap-1">
              <Link className="navlink" href="/">Search</Link>
              <Link className="navlink" href="/rules/">Rules</Link>
              <Link className="navlink" href="/feeds/">Feeds</Link>
            </nav>
            <span className="grow" />
            <span className="mono hidden text-[11px] md:inline" style={{ color: "var(--faint)" }}>
              144 gazettes · 2006–2026
            </span>
            <span className="mx-1 hidden h-4 w-px md:inline-block" style={{ background: "var(--line)" }} />
            <ThemeToggle />
          </header>
          <div className="min-h-0 grow">{children}</div>
        </div>
      </body>
    </html>
  );
}
