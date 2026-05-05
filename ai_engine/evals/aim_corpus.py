"""AIM \u2014 minimal eval corpus + harness.

Each entry is a small assignment brief plus the directive we expect the
parser to extract and the rubric criteria we expect to see represented.

Run via:  pytest ai_engine/evals/test_aim_parser_eval.py -m \"aim_eval\"

These tests hit a real Gemini key when AIM_EVAL_LIVE=1 is set; otherwise
they are skipped. CI runs them on a nightly cadence.
"""
from __future__ import annotations

AIM_PARSER_CORPUS: list[dict] = [
    {
        "id": "tesla-strategy-ug",
        "brief": (
            "Critically evaluate Tesla's vertical integration strategy in the global "
            "automotive market between 2018 and 2024. Discuss its impact on cost "
            "leadership, supply chain resilience, and brand perception. Word count: 2000."
        ),
        "expected_directive_keywords": ["evaluate", "critic"],
        "expected_word_count": 2000,
        "expected_topics": ["vertical integration", "tesla"],
    },
    {
        "id": "literature-modernism-pg",
        "brief": (
            "With reference to two modernist novels, analyse how stream-of-consciousness "
            "narration challenges the realist tradition. Engage with at least three "
            "secondary critics. 3000 words, Harvard referencing."
        ),
        "expected_directive_keywords": ["analyse", "analyze"],
        "expected_word_count": 3000,
        "expected_topics": ["stream-of-consciousness", "modernist"],
    },
    {
        "id": "biology-mba-case",
        "brief": (
            "Compare and contrast two biotech firms' commercialisation strategies for "
            "mRNA platforms post-2020. Recommend a strategy for a hypothetical new "
            "entrant. 2500 words."
        ),
        "expected_directive_keywords": ["compare", "contrast", "recommend"],
        "expected_word_count": 2500,
        "expected_topics": ["mrna", "biotech"],
    },
]


# -----------------------------------------------------------------------------
# Reviewer corpus: each entry has a section_meta + parsed stub + a "section"
# string the reviewer must score. Strong entries should score >= 85; weak
# entries should score < 75. Live-only (AIM_EVAL_LIVE=1).
# -----------------------------------------------------------------------------
AIM_REVIEWER_CORPUS: list[dict] = [
    # ---------- STRONG (expected >= 85 weighted, all dims >= 85) ----------
    {
        "id": "strong-tesla-vertical-integration",
        "expected": "pass",
        "parsed": {"directive": "evaluate", "academic_level": "ug",
                   "rubric_breakdown": ["critical evaluation", "evidence", "structure"]},
        "section_meta": {"title": "Cost leadership through vertical integration", "word_limit": 500},
        "section": (
            "Tesla's decision to internalise battery cell manufacturing through the "
            "Nevada Gigafactory between 2018 and 2024 produced a measurable cost "
            "advantage that conventional OEMs could not replicate within the same "
            "horizon. Drawing on Sako (2022) and Helper et al. (2021), this section "
            "argues that vertical integration delivered cost leadership only because "
            "Tesla coupled it with software-defined process control \u2014 a condition "
            "absent at GM and Ford. Three mechanisms drove the gap. First, in-house "
            "cathode production removed an estimated $18/kWh of supplier margin, a "
            "figure consistent with BloombergNEF (2023). Second, co-locating cell, "
            "pack and vehicle assembly compressed logistics overhead in ways the "
            "tier-1 supplier model structurally cannot match. Third, telemetry from "
            "the active fleet fed continuous yield improvements, an effect Helper "
            "calls 'integrated learning'. Critics counter that Tesla's gross margin "
            "advantage narrowed sharply in late 2023 as Chinese competitors closed "
            "the cost gap, suggesting integration alone is necessary but not "
            "sufficient. The evidence therefore supports a qualified conclusion: "
            "vertical integration was a cost-leadership lever between 2018 and 2022 "
            "but is being commoditised, and Tesla's durable advantage now rests on "
            "the software layer that integration enabled rather than on integration "
            "itself."
        ),
    },
    {
        "id": "strong-modernism-stream-of-consciousness",
        "expected": "pass",
        "parsed": {"directive": "analyse", "academic_level": "pg",
                   "rubric_breakdown": ["close reading", "secondary criticism", "argument"]},
        "section_meta": {"title": "Interior monologue and the realist contract", "word_limit": 600},
        "section": (
            "Joyce's 'Penelope' chapter and Woolf's 'Time Passes' jointly dismantle "
            "the realist contract by relocating narrative authority from an external "
            "arbiter into the irregular cadences of consciousness itself. Where "
            "Eliot's narrator in Middlemarch arbitrates moral judgement, Molly "
            "Bloom's unpunctuated stream forces the reader to perform that arbitration "
            "without scaffolding, a shift Cohn (1978) reads as a structural \u2014 not "
            "merely stylistic \u2014 break. Auerbach extends the point: the realist "
            "tradition relied on what he calls 'the historical perspective', and "
            "stream-of-consciousness collapses that perspective by privileging the "
            "instant. Yet to argue, with Lukacs, that this collapse is reactionary "
            "misreads the ethical demand it makes. Both passages refuse to console; "
            "they impose interpretive labour. The 'lighthouse beam' in Woolf's "
            "interlude is not symbol but interruption, denying narrative closure in "
            "a way that anticipates Beckett. Read together, the two texts do not "
            "merely depart from realism; they argue, formally, that consciousness is "
            "the only honest unit of historical observation \u2014 a claim the realist "
            "novel structurally cannot accommodate."
        ),
    },
    {
        "id": "strong-mrna-commercialisation",
        "expected": "pass",
        "parsed": {"directive": "compare", "academic_level": "pg",
                   "rubric_breakdown": ["evidence", "comparative argument", "recommendation"]},
        "section_meta": {"title": "Platform vs. product strategy at Moderna and BioNTech", "word_limit": 500},
        "section": (
            "Moderna and BioNTech entered the post-2020 mRNA market with structurally "
            "different commercialisation logics. Moderna positioned its lipid-nanoparticle "
            "stack as a horizontal platform, pursuing twenty-plus parallel programmes "
            "(Moderna 10-K, 2023). BioNTech, by contrast, concentrated its capital on "
            "oncology programmes co-developed with Genentech (BioNTech AR, 2023). The "
            "comparison matters because it isolates platform breadth from indication "
            "depth as competing routes to durable margin. Three lines of evidence support "
            "the depth strategy as the more defensible choice for a new entrant: first, "
            "regulatory throughput at the FDA favours sponsors with concentrated late-stage "
            "data (Sherkow, 2022); second, manufacturing scale-up costs penalise breadth "
            "before any indication has crossed Phase III; third, payer reimbursement in "
            "oncology rewards specificity of clinical benefit. A new entrant should "
            "therefore avoid Moderna's platform posture and instead commit to two oncology "
            "indications with credible biomarker selection \u2014 a recommendation that "
            "BioNTech's own 2023\u201324 pipeline allocation independently validates."
        ),
    },
    {
        "id": "strong-policy-housing-supply",
        "expected": "pass",
        "parsed": {"directive": "evaluate", "academic_level": "ug",
                   "rubric_breakdown": ["evidence", "policy reasoning", "counterargument"]},
        "section_meta": {"title": "Greenbelt release as a supply lever", "word_limit": 500},
        "section": (
            "Releasing greenbelt land at the metropolitan fringe would expand the "
            "developable land bank, but the policy's effect on housing affordability "
            "depends on a chain of intermediate conditions that the supply-elasticity "
            "literature treats as binding rather than incidental. Hilber and Vermeulen "
            "(2016) demonstrate that English house prices respond to constraint relaxation "
            "only where local planning capacity, infrastructure delivery, and absorptive "
            "demand all align. Any one of these failing collapses the price effect. The "
            "Letwin Review (2018) reinforces the point on the supply side: large-site "
            "build-out rates are governed by absorption economics, not by land availability. "
            "The counterargument \u2014 that supply expansion always lowers price in the long "
            "run \u2014 holds in stylised models but fails on observed UK timescales relevant "
            "to a parliamentary horizon. The honest evaluation is therefore that greenbelt "
            "release is a necessary precondition for a meaningful affordability response in "
            "high-demand regions, but is far from sufficient, and a policy that releases "
            "land without simultaneously fixing infrastructure delivery and absorption "
            "constraints will produce land-banking, not affordable homes."
        ),
    },
    {
        "id": "strong-stat-causal-inference",
        "expected": "pass",
        "parsed": {"directive": "evaluate", "academic_level": "pg",
                   "rubric_breakdown": ["technical rigour", "interpretation", "limitations"]},
        "section_meta": {"title": "Limits of difference-in-differences under staggered adoption", "word_limit": 500},
        "section": (
            "The two-way fixed-effects estimator, long the workhorse of policy evaluation, "
            "fails under staggered treatment timing in ways that recent work has made "
            "unavoidable to confront. Goodman-Bacon (2021) shows that the TWFE coefficient "
            "is a weighted average of all 2x2 contrasts, including comparisons that use "
            "already-treated units as controls; when treatment effects evolve over time, "
            "these forbidden comparisons produce sign reversals. De Chaisemartin and "
            "D'Haultf\u0153uille (2020) extend the diagnosis and propose estimators robust "
            "to heterogeneous timing. The practical implication for applied researchers is "
            "not that DiD is invalid, but that the published TWFE estimates from the past "
            "decade require re-examination case by case. A defensible workflow now requires "
            "(i) reporting the Goodman-Bacon decomposition, (ii) presenting an event-study "
            "specification with proper baseline omission, and (iii) using a heterogeneity-"
            "robust estimator as the primary specification. A study that reports only a "
            "TWFE point estimate in 2024 is no longer at the methodological frontier."
        ),
    },

    # ---------- WEAK (expected < 75 weighted, gate should NOT pass) ----------
    {
        "id": "weak-listicle-strategy",
        "expected": "fail",
        "parsed": {"directive": "evaluate", "academic_level": "ug",
                   "rubric_breakdown": ["critical evaluation"]},
        "section_meta": {"title": "Tesla strategy", "word_limit": 400},
        "section": (
            "There are many reasons Tesla is successful. First, they make electric cars. "
            "Second, they have a strong brand. Third, Elon Musk is a famous CEO. Fourth, "
            "they have a lot of factories. Fifth, they sell software. Sixth, they have "
            "good marketing. Seventh, they are vertically integrated. Eighth, they are "
            "innovative. Ninth, they have a global presence. Tenth, they are profitable. "
            "In conclusion, Tesla is a great company because of all these reasons."
        ),
    },
    {
        "id": "weak-banned-phrase-soup",
        "expected": "fail",
        "parsed": {"directive": "analyse", "academic_level": "pg",
                   "rubric_breakdown": ["argument"]},
        "section_meta": {"title": "Modernism overview", "word_limit": 400},
        "section": (
            "In today's fast-paced world, it is important to note that modernism was a "
            "groundbreaking movement that revolutionised literature in countless ways. "
            "It is worth mentioning that Joyce and Woolf, among others, paved the way for "
            "future generations. At the end of the day, modernism delved into the human "
            "condition in a unique and unprecedented manner. In a nutshell, this movement "
            "stood the test of time and continues to resonate with readers across the globe. "
            "Furthermore, it goes without saying that the impact of modernism cannot be "
            "overstated."
        ),
    },
    {
        "id": "weak-surface-summary-no-critique",
        "expected": "fail",
        "parsed": {"directive": "evaluate", "academic_level": "ug",
                   "rubric_breakdown": ["critical evaluation"]},
        "section_meta": {"title": "Summary of Porter's Five Forces", "word_limit": 400},
        "section": (
            "Porter's Five Forces is a framework developed by Michael Porter. It includes "
            "the threat of new entrants, the bargaining power of buyers, the bargaining "
            "power of suppliers, the threat of substitutes, and competitive rivalry. The "
            "framework is used by managers to analyse industries. It was first published "
            "in 1979. Many companies use it. It is taught in business schools. It is "
            "considered a classic framework. The five forces help understand industry "
            "structure. Each force has different implications for strategy."
        ),
    },
    {
        "id": "weak-repetitive-shingles",
        "expected": "fail",
        "parsed": {"directive": "compare", "academic_level": "ug",
                   "rubric_breakdown": ["argument"]},
        "section_meta": {"title": "mRNA companies", "word_limit": 400},
        "section": (
            "Moderna and BioNTech are two mRNA companies. Moderna is an mRNA company. "
            "BioNTech is an mRNA company. Both companies make mRNA vaccines. Their mRNA "
            "vaccines are based on mRNA technology. The mRNA technology is used to make "
            "mRNA vaccines. These mRNA vaccines were used during the pandemic. The pandemic "
            "increased demand for mRNA vaccines. mRNA vaccines became very important during "
            "the pandemic. Both companies benefited from the pandemic demand for mRNA "
            "vaccines based on mRNA technology."
        ),
    },
    {
        "id": "weak-off-directive-narrative",
        "expected": "fail",
        "parsed": {"directive": "evaluate", "academic_level": "ug",
                   "rubric_breakdown": ["critical evaluation", "evidence"]},
        "section_meta": {"title": "Greenbelt policy", "word_limit": 400},
        "section": (
            "When I first heard about the greenbelt, I was a bit confused. My grandmother "
            "lived near a greenbelt area and used to walk her dog there every morning. "
            "She always said it was very peaceful. I think nature is important and we "
            "should protect it. Building houses everywhere would ruin the countryside. "
            "Maybe the government should think about other places to build instead. Cities "
            "are crowded but the countryside is nice. People should be allowed to enjoy "
            "open spaces. That is my opinion on the greenbelt issue."
        ),
    },
]

