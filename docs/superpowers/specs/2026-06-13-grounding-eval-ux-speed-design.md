# Grounding, Evaluation, UX, And Speed Design

Date: 2026-06-13

## Goal

Improve AdhikarAI in the order A, C, B, D:

1. Grounding accuracy
2. Evaluation quality
3. User experience
4. Speed and cost

The product goal is a fast Indian legal-rights assistant that answers from retrieved legal material, exposes uncertainty clearly, and stays interactive for ordinary chat commands.

## Current State

The app already has:

- A query planner that skips retrieval for smalltalk and detects multi-issue legal queries.
- A stricter prompt that asks the model to mark unsupported issues as `source missing`.
- Streaming diagnostics shown in the chat bubble.
- Basic golden eval coverage for domain routing, retrieval, answer coverage, and query planning.

The main remaining risk is corpus and grounding quality. If the knowledge base does not contain the right law, section, procedure, or authority, the assistant must not invent an answer.

## A. Grounding Accuracy

### Legal Coverage Map

Create a coverage map for the practical domains users are likely to ask about:

- Labour: unpaid salary, termination, maternity, workplace harassment.
- Tenancy and deposit: landlord deposit return, rent disputes, eviction basics.
- Consumer: defective product, refund, warranty, service complaints.
- Police and FIR: FIR refusal, arrest, bail, complaint escalation.
- Women and family: domestic violence, threats, dowry, maintenance, protection.
- RTI: filing, fees, appeal, public authority.
- Property and registration: compulsory registration, stamp duty, land acquisition.
- Citizen rights: fundamental rights, disability rights, grievance portals.

Each domain should report whether the corpus has enough source material for common user scenarios.

### Source Metadata

Each retrieved chunk should carry enough metadata to make citations useful:

- `title`
- `source`
- `domain`
- `section`
- `act_or_rule`
- `year`
- `jurisdiction`
- `chunk_index`
- `url` when available

If metadata is missing, the UI should show a weaker citation label instead of pretending the source is precise.

### Grounding Guard

Every actionable recommendation must be supported by a retrieved chunk or marked `source missing`.

The answer policy should be:

- If the source supports the action, cite it.
- If the source does not support the action, say `source missing`.
- If the query contains multiple issues, answer each issue separately.
- If too many facts are missing, ask one focused follow-up question instead of guessing.

This avoids responses such as "Contact the Labour Department" unless the retrieved material actually supports that route.

## C. Evaluation Quality

### Scenario Set

Expand `eval/golden.yaml` from short law questions into realistic user scenarios:

- Unpaid salary with no payslip.
- Landlord refusing security deposit.
- Defective product and seller refusing refund.
- Husband threatening user.
- Police refusing FIR.
- Combined multi-issue query covering all of the above.
- Smalltalk and retry commands that should not trigger new retrieval.

### Automated Checks

The eval runner should check:

- Expected domain.
- Query type: `smalltalk`, `legal_single`, `legal_multi_issue`, or `followup`.
- Retrieval needed or skipped.
- Minimum issue count for multi-issue prompts.
- Minimum citations for legal answers.
- Whether unsupported advice appears without `source missing`.
- Whether answer language matches the requested language.

### Regression Report

Generate a JSON report that lists weak areas:

- Domains with low retrieval hit rate.
- Scenarios with no citations.
- Answers that contain unsupported action terms.
- Multi-issue queries where one or more issues had no supporting source.

This report should guide what PDFs or legal sources to ingest next.

## B. User Experience

### Multi-Issue Answer UI

For a query with several legal problems, show issue-level structure:

- Issue title.
- Retrieved source count.
- Answer summary.
- Source status: `grounded`, `partial`, or `source missing`.
- Continue button for that issue.

This lets the user continue with one issue instead of receiving one long mixed answer.

### Follow-Up Flow

When facts are missing, the assistant should ask one focused question:

- "Which state is the rental property in?"
- "Do you have a salary slip or written employment proof?"
- "Was the police refusal verbal or written?"

The question should only appear when the missing fact changes the next legal step.

### Source Display

The right insights panel should show:

- Source title.
- Section or act name when available.
- Domain.
- Chunk number.
- Similarity score or confidence label.
- Missing metadata warning when citation quality is weak.

## D. Speed And Cost

### Cache Preference

Use a hybrid cache. This is safer than putting all legal answers in the browser.

### Browser Session Cache

Use browser `sessionStorage` for short-lived, non-sensitive interaction state:

- Active conversation id.
- Open/closed UI panels.
- Draft composer text.
- Last visible diagnostics for the current tab.
- Recent non-sensitive query-plan result for the current session.

Do not store full legal answers, retrieved chunks, or long chat history in browser storage by default. Legal queries may contain sensitive facts, and browser storage can remain accessible on shared devices.

### Server Cache

Keep retrieval and answer caching server-side:

- Query-plan cache keyed by normalized query, language, and short history hash.
- Retrieval cache keyed by normalized query, domain, language, embedding model, and corpus version.
- Answer cache only when the final answer is deterministic enough and the result is not tied to private uploaded material.

Recommended TTLs:

- Query plan: 10-30 minutes.
- Retrieval: 30-120 minutes.
- Full answer: 5-30 minutes, disabled for private or uploaded-document contexts.

### Cache Invalidation

Include a corpus version in retrieval cache keys. Increment it after ingesting or deleting legal documents so stale retrieved chunks do not survive corpus changes.

### Latency Metrics

Measure and report:

- Query planning time.
- Retrieval time.
- Rerank time.
- Generation first-token time.
- Full answer time.
- Cache hit rate by cache type.

## Data Flow

1. User sends message.
2. Browser restores draft/session UI state from `sessionStorage`.
3. Backend creates a query plan.
4. If no retrieval is needed, backend returns a fast chat response.
5. If retrieval is needed, backend retrieves per issue where applicable.
6. Backend validates grounding status and builds prompt context.
7. Model generates answer under strict source rules.
8. Backend streams answer and diagnostics.
9. Frontend displays answer, issue/source chips, and source panel data.
10. Eval runner checks whether the behavior matches golden expectations.

## Testing

Add tests for:

- Query planning and retrieval skipping.
- Multi-issue splitting.
- Citation metadata formatting.
- Unsupported-advice detection.
- Eval report fields.
- Browser session cache helper behavior.
- Server cache key construction and corpus-version invalidation.

## Out Of Scope

This design does not cover:

- Final deployment work.
- Auth, user accounts, or billing.
- Long-term browser storage of legal answers.
- Adding new third-party LLM providers.

## Success Criteria

The next implementation is successful when:

- Smalltalk and retry behavior remain fast and interactive.
- Multi-issue legal queries produce issue-level grounded output.
- Unsupported advice is either cited or marked `source missing`.
- Eval reports identify weak corpus domains.
- Browser session cache improves UX without storing sensitive legal answers long-term.
- Server-side retrieval caching improves latency without serving stale corpus results.
