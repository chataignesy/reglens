import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import Link from "next/link";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

// Fonts ship with the `geist` package (self-hosted): the build needs no network access.
// They define --font-geist-sans / --font-geist-mono; globals.css maps the theme to them.

export const metadata: Metadata = {
  title: "RegLens",
  description: "Grounded answers on EU credit risk regulation, with paragraph-level citations.",
};

const DISCLAIMER =
  "Personal open-source project — not affiliated with any employer, supervisor or regulator. " +
  "Not legal or regulatory advice; always check the official texts.";

// Follow the operating system's light/dark setting before first paint.
const THEME_SCRIPT = `
  (function () {
    var m = window.matchMedia("(prefers-color-scheme: dark)");
    var set = function () { document.documentElement.classList.toggle("dark", m.matches); };
    set(); m.addEventListener("change", set);
  })();`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <TooltipProvider>
          <header className="border-b">
            <div className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
              <Link href="/" className="text-lg font-semibold tracking-tight">
                RegLens
              </Link>
              <nav className="flex gap-4 text-sm text-muted-foreground">
                <Link href="/" className="hover:text-foreground">
                  Ask
                </Link>
                <Link href="/gap" className="hover:text-foreground">
                  Policy gap analysis
                </Link>
              </nav>
              <span className="ml-auto hidden text-xs text-muted-foreground sm:block">
                EU credit risk regulation · CRR3 · RTS · EBA · ECB
              </span>
            </div>
          </header>
          <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">{children}</main>
          <footer className="border-t">
            <p className="mx-auto max-w-5xl px-4 py-4 text-xs text-muted-foreground">
              {DISCLAIMER}
            </p>
          </footer>
        </TooltipProvider>
      </body>
    </html>
  );
}
