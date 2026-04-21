import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Toaster } from "@/components/ui/toaster";
import { ErrorBoundary } from "@/components/error-boundary";
import { ibmPlexMono } from "@/fonts/ibm-plex-mono";

const inter = Inter({ subsets: ["latin"] });

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f7fa" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0c12" },
  ],
};

export const metadata: Metadata = {
  title: {
    default: "HireStack AI — AI-Powered Career Intelligence Platform",
    template: "%s | HireStack AI",
  },
  description:
    "Build interview-winning applications with 6 AI agents. ATS-optimized CV, tailored cover letter, gap analysis, company intel — all in under 3 minutes.",
  keywords: [
    "resume builder", "AI resume", "CV generator", "cover letter generator",
    "ATS scanner", "job application", "career intelligence", "interview prep",
    "gap analysis", "salary negotiation", "AI career coach",
  ],
  authors: [{ name: "HireStack AI" }],
  creator: "HireStack AI",
  metadataBase: new URL("https://hirestack.tech"),
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://hirestack.tech",
    siteName: "HireStack AI",
    title: "HireStack AI — Stop Applying. Start Landing.",
    description: "6 AI agents build your perfect application package. ATS-optimized CV, tailored cover letter, company intel, gap analysis.",
    images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: "HireStack AI" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "HireStack AI — AI-Powered Career Intelligence",
    description: "Build interview-winning applications with 6 AI agents. Get started today.",
    images: ["/opengraph-image"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-video-preview": -1, "max-image-preview": "large", "max-snippet": -1 },
  },
  alternates: {
    canonical: "/",
  },
  icons: {
    icon: "/favicon.ico",
  },
  manifest: "/manifest.json",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="manifest" href="/manifest.json" />
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
        <meta name="theme-color" content="#6366f1" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="apple-mobile-web-app-title" content="HireStack AI" />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@graph": [
                {
                  "@type": "SoftwareApplication",
                  "name": "HireStack AI",
                  "url": "https://hirestack.tech",
                  "applicationCategory": "BusinessApplication",
                  "operatingSystem": "Web",
                  "description": "Build interview-winning applications with 6 AI agents. ATS-optimized CV, tailored cover letter, gap analysis, company intel — all in under 3 minutes.",
                  "offers": { "@type": "Offer", "price": "0", "priceCurrency": "USD" },
                },
                {
                  "@type": "Organization",
                  "name": "HireStack AI",
                  "url": "https://hirestack.tech",
                  "logo": "https://hirestack.tech/opengraph-image",
                },
              ],
            }),
          }}
        />
      </head>
      <body className={`${inter.className} ${ibmPlexMono.variable}`}>
        <ErrorBoundary>
          <Providers>
            {children}
            <Toaster />
          </Providers>
        </ErrorBoundary>
      </body>
    </html>
  );
}
