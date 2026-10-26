# Research handover

## Project idea supported by repository materials

The README and AI integration notes describe a system for helping people reflect on how they solve problems over time. The implemented concept is to capture a user-provided session, extract decisions/assumptions/evidence/justifications, retrieve earlier sessions, and show tentative recurring reasoning similarities with supporting quotes and reflection questions.

No standalone research protocol, paper draft, participant data, or study results were found. The research-adjacent project description is in `README.md` and `docs/ai_integration.md`; PostgreSQL scope is described in `docs/postgres_storage_phase1.md`. These are software documents, not evidence that the system improves reasoning.

## Components relevant to research

- Structured extraction schema and evidence validation: `ai/schemas/reasoning.py`, `ai/extraction/reasoning_extractor.py`.
- Session record and persistence: `ai/storage/session_store.py`; optional Data API adapter and RLS migration are present locally.
- Keyword-based retrieval: `ai/retrieval/keyword_search.py`.
- Deterministic cross-session similarity: `ai/patterns/reasoning_patterns.py`.
- Workflow: `ai/workflow.py`.
- Hand-authored extraction set and scorer: `ai/evaluation/dataset.json`, `ai/evaluation/saved_predictions.json`, `ai/evaluation/evaluate.py`.

These are engineering components, not validated research instruments. The pattern method measures textual overlap and has no empirical construct validation.

## Evidence currently available

The dataset contains 16 hand-written synthetic/example sessions and expected structured outputs. Saved predictions are deterministic fixtures. They support regression testing and metric-code checking only. The developer reports offline evaluation completed with 16 examples and zero prediction errors; that does not describe live Gemini output. The developer also reports 9/9 local pgTAP assertions; those test database access policies, not human outcomes. No controlled user study, baseline, inter-rater agreement, or causal evidence was found.

## Claims that remain hypotheses

- Evidence-linked extraction may help users notice how they reason.
- Retrieval and cross-session observations may help users reflect on repeated approaches.
- Reflection prompts may be useful or change decision quality.

None of these outcome claims is established by current tests or fixtures. Avoid saying Cognitrace improves reasoning, decision quality, mental health, or self-awareness as a proven result.

## Further work for credible research

1. Define a research question and measurable outcome before collecting data.
2. Specify consent, data minimization, retention/deletion, access control, and any required institutional ethics review.
3. Create an annotation guide and have independent reviewers label reasoning categories/evidence; measure agreement and adjudicate disagreements.
4. Evaluate extraction on held-out, consented, de-identified sessions. Report category precision/recall/F1, unsupported-evidence rate, failure rate, and confidence intervals; keep live-model and fixture metrics separate.
5. Evaluate retrieval/pattern quality with human relevance judgments and false-positive analysis; compare against a simple baseline.
6. If claiming user benefit, conduct an appropriately reviewed study with a comparison condition and pre-registered outcomes. Distinguish usability feedback from causal efficacy.
7. Version datasets and model/configuration details without committing private session data or credentials.

This document is not a rewrite of a research paper and contains no new empirical results.

