import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] }); // theme reads --font-sans
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

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
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
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
