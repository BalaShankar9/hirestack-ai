"""
Gold evaluation corpus for agent quality benchmarking.

Each module exports test cases as lists of dicts with:
  - inputs: context dict that would be passed to the pipeline
  - expected: expected output properties (not exact text)
  - failure_conditions: what constitutes a failed test
  - scoring_rules: how to score the output
"""
