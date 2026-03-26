import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pricing — Simple, Transparent Plans",
  description: "Start free with 5 exports. Upgrade to Starter ($19/mo), Pro ($49/mo), or Agency ($149/mo) for unlimited access. No credit card required.",
};

export default function PricingLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
