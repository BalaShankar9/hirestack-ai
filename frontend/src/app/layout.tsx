import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Toaster } from "@/components/ui/toaster";
import { ErrorBoundary } from "@/components/error-boundary";
import { ibmPlexMono } from "@/fonts/ibm-plex-mono";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "HireStack AI - Career Intelligence Platform",
  description:
    "AI-powered career intelligence platform that helps you benchmark, analyze gaps, and build winning applications.",
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
