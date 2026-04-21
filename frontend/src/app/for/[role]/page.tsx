import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { MarketingShell } from "@/components/marketing-shell";
import {
  Code2, LineChart, BarChart3, Briefcase, Stethoscope, GraduationCap,
  ArrowRight, CheckCircle2,
} from "lucide-react";

type RoleKey = "engineers" | "product" | "data" | "business" | "healthcare" | "academic";

const ROLES: Record<RoleKey, {
  icon: typeof Code2;
  headline: string;
  sub: string;
  title: string;
  description: string;
  keywords: string[];
  documents: string[];
  advantages: { title: string; body: string }[];
  roles: string[];
}> = {
  engineers: {
    icon: Code2,
    headline: "Built for engineers",
    sub: "Shipping matters. Your résumé should prove it.",
    title: "HireStack AI for software engineers",
    description:
      "The career intelligence platform for backend, frontend, mobile, platform, and ML engineers. ATS-tuned for FAANG, scale-ups, and enterprise stacks.",
    keywords: ["Python","Go","TypeScript","Rust","Kubernetes","AWS","GCP","CI/CD","Terraform","GraphQL"],
    documents: ["ATS-optimised CV", "Tailored cover letter", "Portfolio brief with GitHub evidence", "System design talking points", "Onsite cheat sheet"],
    advantages: [
      { title: "Impact-first bullets", body: "We rewrite every line around metrics, scale, and outcomes — the language senior ICs actually use." },
      { title: "Keyword density for the real stack", body: "The JD says 'AWS'. We also surface 'IAM', 'CloudFront', 'Step Functions' — the words the ATS weighs more." },
      { title: "System design prep", body: "Predict likely design rounds from the JD and seed talking points grounded in your actual projects." },
    ],
    roles: ["Senior SWE","Staff Engineer","Engineering Manager","Platform Engineer","SRE","ML Engineer","Full-stack","Mobile (iOS/Android)"],
  },
  product: {
    icon: LineChart,
    headline: "Built for PMs & Designers",
    sub: "Your work is strategy. Your résumé should read like one.",
    title: "HireStack AI for product managers & designers",
    description:
      "Turn product launches and design systems into crisp, metric-driven narratives. Tuned for PM, UX, and product-ops interviews.",
    keywords: ["Roadmapping","OKRs","Figma","Design Systems","A/B Testing","North Star Metric","JTBD","User Research"],
    documents: ["Product-led CV", "Narrative cover letter", "Case study portfolio", "Product sense prep", "Metric framework crib sheet"],
    advantages: [
      { title: "Launch-to-impact narrative", body: "Every bullet framed as problem → hypothesis → experiment → outcome. No more 'collaborated with stakeholders.'" },
      { title: "Portfolio-grade case studies", body: "We pull structure from your own work and turn it into interview-ready case studies." },
      { title: "Strategy & sense prep", body: "Predicted product-sense and strategy questions with frameworks grounded in your domain." },
    ],
    roles: ["Product Manager","Senior PM","Principal PM","Product Designer","UX Researcher","Product Ops"],
  },
  data: {
    icon: BarChart3,
    headline: "Built for data & ML",
    sub: "From SQL to foundation models — show it all.",
    title: "HireStack AI for data, analytics, and ML",
    description:
      "Tailored for data scientists, analytics engineers, and ML researchers. Built to surface the right statistical and modelling signal.",
    keywords: ["SQL","Python","dbt","Spark","Airflow","PyTorch","LangChain","Vector DBs","MLOps","Causal Inference"],
    documents: ["Data-led CV", "Research statement", "Portfolio of dashboards and models", "Case interview primer", "SQL take-home prep"],
    advantages: [
      { title: "Signal over buzzwords", body: "We favour 'reduced model cost 38%' over 'leveraged LLMs'. Every metric sourced from your real work." },
      { title: "Research framing for ML roles", body: "Convert projects into publications-style narratives with hypotheses, methods, and results." },
      { title: "SQL & case prep", body: "Predicted SQL patterns and case questions from the JD, seeded with your own schema." },
    ],
    roles: ["Data Scientist","Analytics Engineer","ML Engineer","Data Engineer","Research Scientist","Applied Scientist"],
  },
  business: {
    icon: Briefcase,
    headline: "Built for Business & Ops",
    sub: "Operators get operator-grade résumés.",
    title: "HireStack AI for business, ops, and GTM",
    description:
      "For strategy, operations, finance, sales, and marketing roles. We surface the metrics recruiters actually screen for.",
    keywords: ["GTM","Revenue Ops","Forecasting","SQL","Tableau","Salesforce","Churn","Pipeline","ARR","CAC/LTV"],
    documents: ["Operator CV", "Executive summary cover letter", "Case study deck outline", "Revenue case prep", "Negotiation brief"],
    advantages: [
      { title: "Metric-forward framing", body: "Every bullet tied to revenue, efficiency, or headcount impact with precise numbers." },
      { title: "Deck-style evidence", body: "Portfolio brief structured like the one-pagers used in consulting case rooms." },
      { title: "Exec-ready narrative", body: "Tone and structure tuned for VP / Director / Head-of roles." },
    ],
    roles: ["Strategy & Ops","RevOps","Finance & FP&A","GTM Lead","Marketing Lead","Business Development"],
  },
  healthcare: {
    icon: Stethoscope,
    headline: "Built for healthcare",
    sub: "Licenses, rotations, and outcomes — all mapped.",
    title: "HireStack AI for clinicians and healthcare professionals",
    description:
      "For physicians, nurses, pharmacists, and allied health professionals. Preserves regulatory language while optimising for hiring systems.",
    keywords: ["Board certification","Licensure","Epic","CPT","ICD-10","HIPAA","Clinical Research","Rotation"],
    documents: ["Clinical CV", "Personal statement", "Research statement", "Licensure brief", "Interview scenario prep"],
    advantages: [
      { title: "Licensure & cert integrity", body: "We preserve board and licensure formatting exactly — critical for credentialing systems." },
      { title: "Outcomes-driven framing", body: "Patient outcomes, volume, and quality metrics surfaced in the language hospitals screen for." },
      { title: "Personal-statement coach", body: "Structured narrative support for residency, fellowship, and specialty applications." },
    ],
    roles: ["Physician","Nurse Practitioner","RN","Pharmacist","PT / OT","Clinical Researcher","Allied Health"],
  },
  academic: {
    icon: GraduationCap,
    headline: "Built for academics",
    sub: "Grants, teaching, service — every panel gets the right version.",
    title: "HireStack AI for academic job seekers",
    description:
      "Tenure-track, post-doc, and research roles. Produces research statements, teaching statements, diversity statements, and CVs in a single run.",
    keywords: ["Tenure-track","Post-doc","Grants","NSF","NIH","Teaching Portfolio","Diversity Statement","Research Agenda"],
    documents: ["Academic CV (long-form)", "Research statement", "Teaching statement", "Diversity statement", "Cover letter for search committee"],
    advantages: [
      { title: "Long-form CV done right", body: "Publication formatting (Chicago / APA / numerical), grants, service — formatted to panel expectations." },
      { title: "Three-statement coordination", body: "Research, teaching, and diversity statements that reinforce one coherent scholarly identity." },
      { title: "Committee-tuned language", body: "We match tone and signal to R1, SLAC, teaching-intensive, or industry-adjacent positions." },
    ],
    roles: ["Assistant Professor","Associate Professor","Post-doc","Lecturer","Research Scientist","Program Director"],
  },
};

export async function generateStaticParams() {
  return Object.keys(ROLES).map((role) => ({ role }));
}

export async function generateMetadata(
  { params }: { params: { role: string } }
): Promise<Metadata> {
  const role = ROLES[params.role as RoleKey];
  if (!role) return {};
  return {
    title: role.title,
    description: role.description,
    alternates: { canonical: `/for/${params.role}` },
    openGraph: {
      title: role.title,
      description: role.description,
      url: `/for/${params.role}`,
    },
  };
}

export default function RoleLandingPage({ params }: { params: { role: string } }) {
  const role = ROLES[params.role as RoleKey];
  if (!role) notFound();

  const Icon = role.icon;
  return (
    <MarketingShell
      kicker={<><Icon className="h-3.5 w-3.5" /> {role.headline}</>}
      title={role.sub}
      description={role.description}
    >
      {/* Keyword pills */}
      <div className="flex flex-wrap items-center justify-center gap-2 -mt-4 mb-12">
        {role.keywords.map((kw) => (
          <span
            key={kw}
            className="rounded-full border bg-card px-3 py-1 text-xs font-medium text-muted-foreground"
          >
            {kw}
          </span>
        ))}
      </div>

      {/* Advantages */}
      <div className="grid gap-5 md:grid-cols-3 mb-14">
        {role.advantages.map((a, i) => (
          <div key={i} className="rounded-2xl border bg-card p-6">
            <h3 className="text-base font-semibold">{a.title}</h3>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{a.body}</p>
          </div>
        ))}
      </div>

      {/* Documents */}
      <div className="rounded-2xl border bg-card/50 p-6 mb-14">
        <h2 className="text-xl font-bold">Documents we generate for this path</h2>
        <ul className="mt-5 grid gap-2.5 sm:grid-cols-2">
          {role.documents.map((d) => (
            <li key={d} className="flex items-start gap-2 text-sm">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <span>{d}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Roles supported */}
      <div className="mb-14">
        <h2 className="text-xl font-bold">Roles we&rsquo;ve helped people land</h2>
        <div className="mt-4 flex flex-wrap gap-2">
          {role.roles.map((r) => (
            <span key={r} className="rounded-lg border bg-card px-3 py-1.5 text-xs font-medium">
              {r}
            </span>
          ))}
        </div>
      </div>

      <div className="text-center">
        <Link
          href="/login?mode=register&redirect=/new"
          className="inline-flex items-center gap-2 rounded-2xl bg-primary px-7 py-3.5 text-sm font-bold text-primary-foreground btn-glow hover:shadow-glow-md transition-all hover:brightness-110"
        >
          Start with a real job description <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </MarketingShell>
  );
}
