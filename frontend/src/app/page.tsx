import Link from "next/link";
import { ArrowRight, Target, Sparkles, FileText, TrendingUp } from "lucide-react";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white">
      {/* Header */}
      <header className="container mx-auto px-4 py-6">
        <nav className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Target className="h-8 w-8 text-blue-600" />
            <span className="text-2xl font-bold text-gray-900">HireStack AI</span>
          </div>
          <div className="flex items-center space-x-4">
            <Link
              href="/login"
              className="text-gray-600 hover:text-gray-900 font-medium"
            >
              Sign In
            </Link>
            <Link
              href="/login?mode=register"
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium"
            >
              Get Started
            </Link>
          </div>
        </nav>
      </header>

      {/* Hero Section */}
      <main className="container mx-auto px-4 py-20">
        <div className="text-center max-w-4xl mx-auto">
          <h1 className="text-5xl md:text-6xl font-bold text-gray-900 mb-6">
            Build{" "}
            <span className="text-blue-600">Interview-Winning</span>{" "}
            Applications
          </h1>
          <p className="text-xl text-gray-600 mb-8 max-w-2xl mx-auto">
            AI-powered career intelligence that benchmarks you against elite
            candidates, identifies your gaps, and builds personalized
            application packages.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href="/login?mode=register"
              className="bg-blue-600 text-white px-8 py-4 rounded-lg hover:bg-blue-700 font-semibold text-lg flex items-center"
            >
              Start Free Analysis
              <ArrowRight className="ml-2 h-5 w-5" />
            </Link>
            <Link
              href="#features"
              className="text-gray-600 hover:text-gray-900 font-medium px-8 py-4"
            >
              Learn More
            </Link>
          </div>
        </div>

        {/* Features */}
        <div id="features" className="mt-32 grid md:grid-cols-3 gap-8">
          <FeatureCard
            icon={<Target className="h-8 w-8 text-blue-600" />}
            title="Benchmark Generation"
            description="See what a winning application looks like. We generate a complete benchmark package representing the ideal candidate for any role."
          />
          <FeatureCard
            icon={<Sparkles className="h-8 w-8 text-purple-600" />}
            title="Gap Analysis"
            description="Understand exactly where you stand. Our AI compares your profile to the benchmark and calculates a precise compatibility score."
          />
          <FeatureCard
            icon={<TrendingUp className="h-8 w-8 text-green-600" />}
            title="Career Roadmap"
            description="Get a personalized improvement plan. Learn what skills to develop, certifications to pursue, and projects to build."
          />
        </div>

        {/* How It Works */}
        <div className="mt-32">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-12">
            How It Works
          </h2>
          <div className="grid md:grid-cols-4 gap-8">
            <StepCard
              number="1"
              title="Upload Resume"
              description="Upload your resume and add the job description you're targeting."
            />
            <StepCard
              number="2"
              title="View Benchmark"
              description="See the complete application package of an ideal candidate."
            />
            <StepCard
              number="3"
              title="Analyze Gaps"
              description="Get your compatibility score and detailed gap analysis."
            />
            <StepCard
              number="4"
              title="Build & Export"
              description="Generate tailored documents and export your application package."
            />
          </div>
        </div>

        {/* CTA */}
        <div className="mt-32 bg-blue-600 rounded-2xl p-12 text-center">
          <h2 className="text-3xl font-bold text-white mb-4">
            Ready to Transform Your Job Search?
          </h2>
          <p className="text-blue-100 mb-8 max-w-2xl mx-auto">
            Join thousands of professionals who have improved their applications
            and landed their dream jobs.
          </p>
          <Link
            href="/login?mode=register"
            className="bg-white text-blue-600 px-8 py-4 rounded-lg hover:bg-blue-50 font-semibold text-lg inline-flex items-center"
          >
            Get Started for Free
            <ArrowRight className="ml-2 h-5 w-5" />
          </Link>
        </div>
      </main>

      {/* Footer */}
      <footer className="container mx-auto px-4 py-12 mt-20 border-t">
        <div className="flex flex-col md:flex-row items-center justify-between">
          <div className="flex items-center space-x-2 mb-4 md:mb-0">
            <Target className="h-6 w-6 text-blue-600" />
            <span className="text-lg font-bold text-gray-900">HireStack AI</span>
          </div>
          <p className="text-gray-600 text-sm">
            Powered by Claude AI. Built for career success.
          </p>
        </div>
      </footer>
    </div>
  );
}

function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="bg-white p-8 rounded-xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow">
      <div className="mb-4">{icon}</div>
      <h3 className="text-xl font-semibold text-gray-900 mb-2">{title}</h3>
      <p className="text-gray-600">{description}</p>
    </div>
  );
}

function StepCard({
  number,
  title,
  description,
}: {
  number: string;
  title: string;
  description: string;
}) {
  return (
    <div className="text-center">
      <div className="w-12 h-12 bg-blue-600 text-white rounded-full flex items-center justify-center text-xl font-bold mx-auto mb-4">
        {number}
      </div>
      <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
      <p className="text-gray-600 text-sm">{description}</p>
    </div>
  );
}
