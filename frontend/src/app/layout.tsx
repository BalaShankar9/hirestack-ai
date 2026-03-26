import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Toaster } from "@/components/ui/toaster";
import { ErrorBoundary } from "@/components/error-boundary";
import { ibmPlexMono } from "@/fonts/ibm-plex-mono";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "HireStack AI — AI-Powered Career Intelligence Platform",
    template: "%s | HireStack AI",
  },
  description:
    "Build interview-winning applications with 6 AI agents. ATS-optimized CV, tailored cover letter, gap analysis, company intel — all in under 3 minutes. Try free, no signup required.",
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
    description: "6 AI agents build your perfect application package. ATS-optimized CV, tailored cover letter, company intel, gap analysis. Try free.",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "HireStack AI" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "HireStack AI — AI-Powered Career Intelligence",
    description: "Build interview-winning applications with 6 AI agents. Try free, no signup required.",
    images: ["/og-image.png"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-video-preview": -1, "max-image-preview": "large", "max-snippet": -1 },
  },
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
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
