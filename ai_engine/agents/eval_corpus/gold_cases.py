"""
Gold evaluation corpus — realistic test cases for major pipelines.

Covers: strong profiles, sparse profiles, noisy JDs, adversarial inputs,
hallucination-prone cases, and edge cases for tone/structure/evidence.
"""
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════
#  Reusable profile fixtures
# ═══════════════════════════════════════════════════════════════════════

STRONG_PROFILE = {
    "name": "Sarah Chen",
    "title": "Senior Software Engineer",
    "summary": "Full-stack engineer with 7 years building cloud-native SaaS platforms. Reduced P95 latency by 40% at Stripe.",
    "skills": [
        {"name": "Python", "years": 7},
        {"name": "TypeScript", "years": 5},
        {"name": "React", "years": 4},
        {"name": "AWS", "years": 6},
        {"name": "PostgreSQL", "years": 7},
        {"name": "Docker", "years": 5},
        {"name": "Kubernetes", "years": 3},
        {"name": "GraphQL", "years": 2},
        {"name": "Redis", "years": 4},
        {"name": "CI/CD", "years": 5},
    ],
    "experience": [
        {
            "title": "Senior Software Engineer",
            "company": "Stripe",
            "start_date": "2021-03",
            "end_date": "present",
            "description": (
                "Led migration of payments API to event-driven architecture serving 50M+ daily transactions. "
                "Reduced P95 latency by 40% through Redis caching layer. Mentored 3 junior engineers. "
                "Built internal CLI tool adopted by 200+ engineers."
            ),
        },
        {
            "title": "Software Engineer",
            "company": "Amplitude",
            "start_date": "2018-06",
            "end_date": "2021-02",
            "description": (
                "Built real-time analytics pipeline processing 2B events/day using Kafka and Flink. "
                "Designed customer-facing dashboard used by 500+ enterprise clients. "
                "Reduced data ingestion costs by 30% through batch optimization."
            ),
        },
        {
            "title": "Junior Developer",
            "company": "Acme Corp",
            "start_date": "2016-09",
            "end_date": "2018-05",
            "description": "Developed REST APIs in Python/Flask. Wrote unit tests. Participated in code reviews.",
        },
    ],
    "education": [
        {
            "degree": "B.S. Computer Science",
            "institution": "UC Berkeley",
            "year": 2016,
        },
    ],
    "certifications": [
        {"name": "AWS Solutions Architect - Associate"},
    ],
}

SPARSE_PROFILE = {
    "name": "Alex Kim",
    "title": "Developer",
    "summary": "",
    "skills": [
        {"name": "JavaScript"},
        {"name": "HTML"},
        {"name": "CSS"},
    ],
    "experience": [
        {
            "title": "Web Developer",
            "company": "Local Agency",
            "start_date": "2023-01",
            "end_date": "present",
            "description": "Build websites for clients.",
        },
    ],
    "education": [],
    "certifications": [],
}

CAREER_CHANGER_PROFILE = {
    "name": "Maria Gonzalez",
    "title": "Marketing Manager transitioning to Product Management",
    "summary": "10 years in B2B marketing with data-driven campaign optimization. Seeking PM roles.",
    "skills": [
        {"name": "Market Research", "years": 10},
        {"name": "SQL", "years": 3},
        {"name": "Google Analytics", "years": 8},
        {"name": "A/B Testing", "years": 5},
        {"name": "Figma", "years": 1},
        {"name": "Jira", "years": 2},
    ],
    "experience": [
        {
            "title": "Marketing Manager",
            "company": "HubSpot",
            "start_date": "2019-01",
            "end_date": "present",
            "description": (
                "Managed $2M annual marketing budget. Led 15-person cross-functional campaign team. "
                "Increased MQL-to-SQL conversion by 35% through funnel optimization. "
                "Launched product-led growth initiative reaching 50K free-tier signups."
            ),
        },
        {
            "title": "Marketing Specialist",
            "company": "Salesforce",
            "start_date": "2014-06",
            "end_date": "2018-12",
            "description": "Executed B2B demand gen campaigns. Managed CRM data for 10K+ leads. Built dashboards in Tableau.",
        },
    ],
    "education": [
        {"degree": "MBA", "institution": "Northwestern Kellogg", "year": 2014},
        {"degree": "B.A. Communications", "institution": "UCLA", "year": 2012},
    ],
    "certifications": [
        {"name": "Google Analytics Certified"},
        {"name": "Product Management Certificate - Product School"},
    ],
}

# ═══════════════════════════════════════════════════════════════════════
#  Job description fixtures
# ═══════════════════════════════════════════════════════════════════════

STRONG_JD = (
    "Senior Software Engineer — FinTech Payments\n\n"
    "About the Role:\n"
    "We're looking for a Senior Software Engineer to join our Payments Infrastructure team. "
    "You'll design and build highly available, low-latency payment processing systems serving "
    "millions of transactions daily.\n\n"
    "Requirements:\n"
    "- 5+ years of software engineering experience\n"
    "- Strong proficiency in Python and/or Go\n"
    "- Experience with distributed systems and event-driven architectures\n"
    "- Familiarity with AWS (ECS, Lambda, DynamoDB, SQS)\n"
    "- Experience with PostgreSQL or similar RDBMS\n"
    "- Understanding of payment processing, PCI compliance is a plus\n\n"
    "Nice to Have:\n"
    "- Experience with Kubernetes, Terraform\n"
    "- Contributions to open-source projects\n"
    "- Experience with real-time data pipelines (Kafka, Flink)\n\n"
    "What You'll Do:\n"
    "- Design payment APIs for reliability and scalability\n"
    "- Build monitoring and alerting for transaction health\n"
    "- Collaborate with product, security, and compliance teams\n"
    "- Mentor junior engineers and lead code reviews\n"
)

NOISY_JD = (
    "🚀 We're HIRING!!! 🚀\n\n"
    "Looking for a ROCKSTAR developer who can do EVERYTHING!!!\n\n"
    "Must know: React, Angular, Vue, Svelte, Next.js, Nuxt, Remix, Astro, "
    "Node.js, Deno, Bun, Python, Go, Rust, Java, C#, PHP, Ruby, Swift, Kotlin, "
    "SQL, NoSQL, MongoDB, PostgreSQL, MySQL, Redis, Elasticsearch, "
    "AWS, GCP, Azure, Docker, Kubernetes, Terraform, Ansible, "
    "CI/CD, GitHub Actions, Jenkins, CircleCI, "
    "React Native, Flutter, Electron, "
    "Machine Learning, AI, LLMs, GPT, Claude, "
    "Blockchain, Web3, Smart Contracts\n\n"
    "Salary: Competitive\n"
    "Location: Anywhere!!!\n\n"
    "We're a fast-paced startup disrupting the industry! "
    "Must be a team player with excellent communication skills. "
    "Please apply ASAP this role won't last!!!\n"
)

VAGUE_JD = (
    "Software Developer\n\n"
    "We need someone to help with our software. "
    "You should know how to code. "
    "Experience preferred but not required. "
    "Good attitude is a must.\n"
)

PM_JD = (
    "Product Manager — Growth & Engagement\n\n"
    "About the Role:\n"
    "Join our Product team to drive user growth and engagement for our B2B SaaS platform. "
    "You'll own the product roadmap for activation, retention, and expansion.\n\n"
    "Requirements:\n"
    "- 3+ years of product management experience\n"
    "- Strong analytical skills, experience with SQL and data tools\n"
    "- Experience with A/B testing and experimentation frameworks\n"
    "- Understanding of PLG (product-led growth) strategies\n"
    "- Experience with B2B SaaS metrics (MRR, churn, NPS)\n"
    "- Excellent cross-functional collaboration skills\n\n"
    "Nice to Have:\n"
    "- MBA or equivalent experience\n"
    "- Background in marketing or growth engineering\n"
    "- Experience with Jira, Figma, Amplitude\n"
)


# ═══════════════════════════════════════════════════════════════════════
#  Gold test cases
# ═══════════════════════════════════════════════════════════════════════

GOLD_CASES: list[dict] = [
    # ── Case 1: Strong profile + strong JD (happy path) ────────────
    {
        "id": "cv_strong_happy",
        "pipeline": "cv_generation",
        "description": "Strong engineer profile targeting a well-matched senior role",
        "inputs": {
            "user_profile": STRONG_PROFILE,
            "jd_text": STRONG_JD,
            "job_title": "Senior Software Engineer",
            "company": "FinTech Startup",
        },
        "expected": {
            "must_contain_skills": ["Python", "AWS", "PostgreSQL", "Kubernetes"],
            "must_contain_companies": ["Stripe", "Amplitude"],
            "must_contain_metrics": True,  # Should have quantified achievements
            "min_keyword_overlap": 0.3,
            "readability_range": (50, 85),
            "html_valid": True,
            "min_length": 800,
            "max_length": 12000,
            "no_fabricated_claims": True,
        },
        "failure_conditions": [
            "missing_key_skills",         # Doesn't mention top JD keywords
            "fabricated_company",         # Invents a company not in profile
            "fabricated_credential",      # Invents a degree or cert
            "empty_html",                 # Returns empty content
            "no_quantified_achievements", # No numbers/percentages
        ],
        "scoring_rules": {
            "keyword_coverage": {"weight": 0.25, "threshold": 0.3},
            "evidence_grounding": {"weight": 0.30, "threshold": 0.8},
            "readability": {"weight": 0.15, "threshold": 50},
            "structure_completeness": {"weight": 0.15, "threshold": 0.9},
            "fact_accuracy": {"weight": 0.15, "threshold": 0.95},
        },
    },

    # ── Case 2: Sparse profile + strong JD (stress test) ──────────
    {
        "id": "cv_sparse_stress",
        "pipeline": "cv_generation",
        "description": "Sparse profile — must not hallucinate experience",
        "inputs": {
            "user_profile": SPARSE_PROFILE,
            "jd_text": STRONG_JD,
            "job_title": "Software Engineer",
            "company": "Tech Corp",
        },
        "expected": {
            "must_contain_skills": ["JavaScript"],
            "must_not_fabricate": True,
            "html_valid": True,
            "min_length": 300,
            "max_length": 8000,
            "no_fabricated_claims": True,
            "should_be_honest_about_gaps": True,
        },
        "failure_conditions": [
            "fabricated_experience",       # Invents roles/companies
            "fabricated_skills",           # Claims Python, AWS etc.
            "fabricated_metrics",          # Invents achievement numbers
            "fabricated_education",        # Invents degrees
        ],
        "scoring_rules": {
            "fact_accuracy": {"weight": 0.40, "threshold": 1.0},
            "honesty": {"weight": 0.25, "threshold": 0.9},
            "keyword_coverage": {"weight": 0.15, "threshold": 0.1},
            "structure_completeness": {"weight": 0.20, "threshold": 0.7},
        },
    },

    # ── Case 3: Strong profile + noisy JD (resilience) ────────────
    {
        "id": "cv_noisy_jd",
        "pipeline": "cv_generation",
        "description": "Noisy buzzword-heavy JD — must not keyword-stuff",
        "inputs": {
            "user_profile": STRONG_PROFILE,
            "jd_text": NOISY_JD,
            "job_title": "Full-Stack Developer",
            "company": "Stealth Startup",
        },
        "expected": {
            "must_contain_skills": ["Python", "React", "AWS"],
            "must_not_contain_unrelated": ["Blockchain", "Web3", "Smart Contracts", "Flutter"],
            "html_valid": True,
            "no_fabricated_claims": True,
            "should_filter_noise": True,
        },
        "failure_conditions": [
            "keyword_stuffing",           # Lists skills not in profile
            "fabricated_skills",
            "unreadable_output",          # Readability < 30
        ],
        "scoring_rules": {
            "noise_filtering": {"weight": 0.30, "threshold": 0.8},
            "fact_accuracy": {"weight": 0.30, "threshold": 0.95},
            "readability": {"weight": 0.20, "threshold": 50},
            "keyword_coverage": {"weight": 0.20, "threshold": 0.15},
        },
    },

    # ── Case 4: Cover letter — career changer ────────────────────
    {
        "id": "cl_career_change",
        "pipeline": "cover_letter",
        "description": "Career changer from marketing to PM — must bridge the gap",
        "inputs": {
            "user_profile": CAREER_CHANGER_PROFILE,
            "jd_text": PM_JD,
            "job_title": "Product Manager",
            "company": "GrowthCo",
        },
        "expected": {
            "must_bridge_gap": True,       # Connect marketing skills to PM
            "must_contain_transferable": ["A/B Testing", "cross-functional", "data"],
            "html_valid": True,
            "min_length": 400,
            "max_length": 4000,
            "professional_tone": True,
            "no_fabricated_claims": True,
        },
        "failure_conditions": [
            "ignores_career_change",      # Treats as PM with PM experience
            "fabricated_pm_experience",    # Invents PM roles
            "too_long",                   # > 4000 chars
            "generic_template",           # No company-specific content
        ],
        "scoring_rules": {
            "gap_bridging": {"weight": 0.30, "threshold": 0.7},
            "fact_accuracy": {"weight": 0.25, "threshold": 0.95},
            "tone_match": {"weight": 0.20, "threshold": 0.7},
            "keyword_coverage": {"weight": 0.25, "threshold": 0.25},
        },
    },

    # ── Case 5: ATS scan — strong profile, well-matched ──────────
    {
        "id": "ats_strong_match",
        "pipeline": "ats_scanner",
        "description": "Well-matched profile for ATS scoring accuracy",
        "inputs": {
            "user_profile": STRONG_PROFILE,
            "jd_text": STRONG_JD,
            "job_title": "Senior Software Engineer",
            "company": "FinTech",
            "document_content": (
                "<h1>Sarah Chen</h1>"
                "<h2>Senior Software Engineer</h2>"
                "<p>Full-stack engineer with 7 years building cloud-native SaaS platforms at Stripe and Amplitude.</p>"
                "<h3>Skills</h3><p>Python, TypeScript, React, AWS, PostgreSQL, Docker, Kubernetes, GraphQL, Redis, CI/CD</p>"
                "<h3>Experience</h3>"
                "<p><strong>Senior Software Engineer — Stripe</strong> (2021–present)</p>"
                "<p>Led migration of payments API to event-driven architecture serving 50M+ daily transactions. "
                "Reduced P95 latency by 40% through Redis caching layer.</p>"
            ),
        },
        "expected": {
            "overall_score_range": (60, 100),
            "keyword_matches_min": 5,
            "should_identify_strengths": True,
            "should_identify_gaps": True,
        },
        "failure_conditions": [
            "score_too_low",              # < 60 for well-matched profile
            "no_keyword_analysis",
            "missing_suggestions",
        ],
        "scoring_rules": {
            "score_accuracy": {"weight": 0.35, "threshold": 0.7},
            "keyword_detection": {"weight": 0.30, "threshold": 0.8},
            "suggestion_quality": {"weight": 0.35, "threshold": 0.6},
        },
    },

    # ── Case 6: Benchmark generation ──────────────────────────────
    {
        "id": "benchmark_senior_eng",
        "pipeline": "benchmark",
        "description": "Benchmark for senior engineer role — must be specific and actionable",
        "inputs": {
            "jd_text": STRONG_JD,
            "job_title": "Senior Software Engineer",
            "company": "FinTech Startup",
        },
        "expected": {
            "must_have_ideal_candidate": True,
            "must_have_skills_with_weights": True,
            "must_be_jd_specific": True,
            "should_differentiate_must_nice": True,
        },
        "failure_conditions": [
            "generic_benchmark",          # Not specific to JD
            "missing_ideal_candidate",
            "no_skill_weights",
            "missing_experience_expectations",
        ],
        "scoring_rules": {
            "specificity": {"weight": 0.30, "threshold": 0.7},
            "completeness": {"weight": 0.30, "threshold": 0.8},
            "actionability": {"weight": 0.20, "threshold": 0.6},
            "jd_alignment": {"weight": 0.20, "threshold": 0.7},
        },
    },

    # ── Case 7: Interview prep ────────────────────────────────────
    {
        "id": "interview_senior_eng",
        "pipeline": "interview",
        "description": "Interview prep for senior engineer — must be role-specific",
        "inputs": {
            "user_profile": STRONG_PROFILE,
            "jd_text": STRONG_JD,
            "job_title": "Senior Software Engineer",
            "company": "FinTech Startup",
        },
        "expected": {
            "must_have_questions": True,
            "min_questions": 5,
            "must_be_role_specific": True,
            "must_have_sample_answers": True,
            "should_reference_profile": True,
        },
        "failure_conditions": [
            "generic_questions",          # Not specific to role/JD
            "too_few_questions",          # < 5
            "no_sample_answers",
            "no_technical_questions",
        ],
        "scoring_rules": {
            "question_quality": {"weight": 0.30, "threshold": 0.7},
            "role_specificity": {"weight": 0.30, "threshold": 0.7},
            "answer_helpfulness": {"weight": 0.20, "threshold": 0.6},
            "profile_grounding": {"weight": 0.20, "threshold": 0.5},
        },
    },

    # ── Case 8: Gap analysis — career changer ────────────────────
    {
        "id": "gap_career_change",
        "pipeline": "gap_analysis",
        "description": "Gap analysis for marketing→PM transition",
        "inputs": {
            "user_profile": CAREER_CHANGER_PROFILE,
            "jd_text": PM_JD,
            "job_title": "Product Manager",
            "company": "GrowthCo",
        },
        "expected": {
            "must_identify_gaps": True,
            "must_identify_strengths": True,
            "must_have_compatibility_score": True,
            "score_range": (40, 80),  # Partial match, not 0 or 100
            "should_suggest_actions": True,
        },
        "failure_conditions": [
            "no_gaps_identified",
            "no_strengths_identified",
            "score_out_of_range",         # Perfect score for career changer
            "generic_suggestions",
        ],
        "scoring_rules": {
            "gap_accuracy": {"weight": 0.30, "threshold": 0.7},
            "strength_accuracy": {"weight": 0.25, "threshold": 0.7},
            "score_reasonableness": {"weight": 0.20, "threshold": 0.8},
            "action_specificity": {"weight": 0.25, "threshold": 0.6},
        },
    },

    # ── Case 9: Career roadmap — sparse profile ──────────────────
    {
        "id": "roadmap_sparse",
        "pipeline": "career_roadmap",
        "description": "Career roadmap for sparse/early-career profile",
        "inputs": {
            "user_profile": SPARSE_PROFILE,
            "jd_text": STRONG_JD,
            "job_title": "Software Engineer",
            "company": "Tech Corp",
        },
        "expected": {
            "must_have_milestones": True,
            "must_be_realistic": True,
            "should_not_assume_skills": True,
            "must_have_timeline": True,
        },
        "failure_conditions": [
            "unrealistic_timeline",
            "assumes_senior_skills",
            "generic_advice",
            "no_milestones",
        ],
        "scoring_rules": {
            "realism": {"weight": 0.30, "threshold": 0.7},
            "specificity": {"weight": 0.25, "threshold": 0.6},
            "actionability": {"weight": 0.25, "threshold": 0.6},
            "profile_awareness": {"weight": 0.20, "threshold": 0.7},
        },
    },

    # ── Case 10: Hallucination-prone — fabrication bait ──────────
    {
        "id": "cv_hallucination_bait",
        "pipeline": "cv_generation",
        "description": "Sparse profile with tempting JD — must NOT fabricate",
        "inputs": {
            "user_profile": {
                "name": "Pat Doe",
                "title": "Intern",
                "summary": "Recent bootcamp graduate",
                "skills": [{"name": "Python"}, {"name": "HTML"}],
                "experience": [
                    {
                        "title": "Software Engineering Intern",
                        "company": "SmallCo",
                        "start_date": "2024-06",
                        "end_date": "2024-08",
                        "description": "Wrote Python scripts to automate data entry.",
                    },
                ],
                "education": [
                    {"degree": "Certificate, Full-Stack Development", "institution": "App Academy"},
                ],
                "certifications": [],
            },
            "jd_text": (
                "Staff Engineer — AI/ML Platform\n\n"
                "Requirements:\n"
                "- 10+ years of software engineering, 5+ in ML infrastructure\n"
                "- PhD in CS, ML, or related field strongly preferred\n"
                "- Expert in PyTorch, TensorFlow, distributed training\n"
                "- Published papers in top-tier ML conferences\n"
                "- Experience managing teams of 20+\n"
            ),
            "job_title": "Staff Engineer",
            "company": "AI Megacorp",
        },
        "expected": {
            "no_fabricated_claims": True,
            "must_not_claim": [
                "PhD", "10 years", "PyTorch", "TensorFlow",
                "published", "managing teams", "ML infrastructure",
            ],
            "html_valid": True,
        },
        "failure_conditions": [
            "fabricated_degree",
            "fabricated_years_experience",
            "fabricated_ml_skills",
            "fabricated_publications",
            "fabricated_management_experience",
        ],
        "scoring_rules": {
            "fact_accuracy": {"weight": 0.50, "threshold": 1.0},
            "honesty": {"weight": 0.30, "threshold": 0.95},
            "structure_completeness": {"weight": 0.20, "threshold": 0.5},
        },
    },
]


# ═══════════════════════════════════════════════════════════════════════
#  Per-agent evaluation cases (for unit-level agent testing)
# ═══════════════════════════════════════════════════════════════════════

RESEARCHER_CASES: list[dict] = [
    {
        "id": "research_strong",
        "inputs": {
            "jd_text": STRONG_JD,
            "job_title": "Senior Software Engineer",
            "company": "FinTech Startup",
            "user_profile": STRONG_PROFILE,
        },
        "expected": {
            "min_coverage": 0.6,
            "must_identify_keywords": ["Python", "AWS", "distributed", "payments"],
            "must_identify_industry": True,
            "min_key_signals": 2,
        },
    },
    {
        "id": "research_noisy",
        "inputs": {
            "jd_text": NOISY_JD,
            "job_title": "Developer",
            "company": "Stealth",
            "user_profile": STRONG_PROFILE,
        },
        "expected": {
            "should_filter_noise": True,
            "must_not_prioritize_all": True,  # Can't prioritize 40+ technologies
            "max_critical_keywords": 10,
        },
    },
]

CRITIC_CASES: list[dict] = [
    {
        "id": "critic_strong_draft",
        "draft": {
            "html": (
                "<h1>Sarah Chen</h1><h2>Senior Software Engineer</h2>"
                "<p>7 years building cloud-native platforms. Reduced P95 latency 40% at Stripe. "
                "Built analytics pipeline processing 2B events/day at Amplitude.</p>"
                "<h3>Skills</h3><p>Python, TypeScript, React, AWS, PostgreSQL, Kubernetes</p>"
            ),
        },
        "expected": {
            "impact_range": (70, 100),
            "clarity_range": (70, 100),
            "completeness_range": (60, 100),
            "needs_revision": False,
        },
    },
    {
        "id": "critic_weak_draft",
        "draft": {
            "html": "<p>I am good at coding. I like computers. Please hire me.</p>",
        },
        "expected": {
            "impact_range": (0, 40),
            "clarity_range": (30, 70),
            "needs_revision": True,
            "must_have_critical_issues": True,
        },
    },
]

FACT_CHECKER_CASES: list[dict] = [
    {
        "id": "fc_accurate_claims",
        "draft": {
            "html": (
                "Led migration of payments API at Stripe serving 50M+ daily transactions. "
                "Reduced P95 latency by 40% through Redis caching. "
                "Built analytics pipeline processing 2B events/day at Amplitude. "
                "B.S. Computer Science from UC Berkeley. AWS Solutions Architect certified."
            ),
        },
        "user_profile": STRONG_PROFILE,
        "expected": {
            "verified_min": 3,
            "fabricated_max": 0,
            "confidence_min": 0.7,
        },
    },
    {
        "id": "fc_fabricated_claims",
        "draft": {
            "html": (
                "Led a team of 50 engineers at Google. "
                "PhD in Machine Learning from MIT. "
                "Published 12 papers in NeurIPS. "
                "Generated $50M in revenue at my startup."
            ),
        },
        "user_profile": STRONG_PROFILE,
        "expected": {
            "fabricated_min": 3,
            "must_flag": ["Google", "PhD", "MIT", "NeurIPS", "$50M", "startup"],
            "confidence_min": 0.6,
        },
    },
    {
        "id": "fc_enhanced_claims",
        "draft": {
            "html": (
                "Spearheaded company-wide migration to event-driven architecture at Stripe. "
                "Championed engineering excellence through mentorship of team members. "
                "Transformed data pipeline efficiency, achieving 30% cost reduction at Amplitude."
            ),
        },
        "user_profile": STRONG_PROFILE,
        "expected": {
            "enhanced_min": 2,
            "fabricated_max": 0,
            "confidence_min": 0.6,
        },
    },
]

OPTIMIZER_CASES: list[dict] = [
    {
        "id": "opt_low_ats",
        "draft": {
            "html": (
                "<p>I worked at a company doing software things. "
                "Made stuff better. Used computers.</p>"
            ),
        },
        "jd_text": STRONG_JD,
        "expected": {
            "ats_score_range": (0, 30),
            "must_suggest_keywords": True,
            "min_suggestions": 3,
        },
    },
    {
        "id": "opt_high_ats",
        "draft": {
            "html": (
                "<p>Senior Software Engineer with 7 years experience in Python, AWS, "
                "PostgreSQL. Built distributed systems and event-driven architectures "
                "for payment processing. Led Kubernetes deployments, CI/CD pipelines, "
                "and real-time data pipelines with Kafka.</p>"
            ),
        },
        "jd_text": STRONG_JD,
        "expected": {
            "ats_score_range": (40, 100),
            "keyword_overlap_min": 0.3,
        },
    },
]
