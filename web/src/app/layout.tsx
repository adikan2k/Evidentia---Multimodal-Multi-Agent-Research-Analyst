import type { Metadata } from "next";
import { Geist, Geist_Mono, Newsreader } from "next/font/google";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

const sans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
// The reading serif. Used only for the audited answer and for quotes from cited pages.
const serif = Newsreader({
  variable: "--font-newsreader",
  subsets: ["latin"],
  style: ["normal", "italic"],
});

const DESCRIPTION =
  "Paste an AI answer with its sources. Evidentia reads every cited page and shows whether each citation backs its claim.";

export const metadata: Metadata = {
  metadataBase: new URL("https://evidentia-green.vercel.app"),
  title: { default: "Evidentia · Do the citations say what the answer says?", template: "%s · Evidentia" },
  description: DESCRIPTION,
  openGraph: {
    title: "Evidentia",
    description: DESCRIPTION,
    siteName: "Evidentia",
    type: "website",
  },
  twitter: { card: "summary_large_image", title: "Evidentia", description: DESCRIPTION },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${sans.variable} ${mono.variable} ${serif.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <a href="#main" className="skip-link label">
          Skip to the content
        </a>
        <SiteHeader />
        <main id="main" className="flex-1">
          {children}
        </main>
        <SiteFooter />
      </body>
    </html>
  );
}
