# Semantic Filtering & Geometric Consensus: Implementation Notes

This document clarifies the design envelope of the Semantic Embedding capabilities introduced in the `experimental` branch, noting specifically what was kept, what was removed before integration, and why.

## Kept: Core Strategy & Persistence
1. **Semantic Clustering (`--strategy semantic`)**: The ability to send parallel LLM responses through an embedding backend to cluster and identify the densest semantic region before arbitration.
2. **Architectural Backends**: Clean abstractions exist for OpenAI, SentenceTransformers, and Chutes embeddings.
3. **Database Logging**: `response_embeddings`, `consensus_clusters`, and theoretical metrics like `geometric_confidence` are faithfully persisted to SQLite for downstream analytics and evaluation.

## Removed or Disabled (The "Narrowing" Plan)
Following a technical validation review, parts of the initial semantic prototype were explicitly removed or demoted. They should not be restored without careful redesign:

1. **Silent Fallback to Dummy Vectors**
   - *Original behavior:* If an embedding backend failed (e.g., API timeout), the system caught the error and generated a deterministic pseudo-random vector based on text-hashing. It then performed clustering on this noise. 
   - *Current action:* **Removed**. If embeddings are requested but the service is unavailable or throwing errors, the orchestrator now raises a hard `RuntimeError`. Filtering should never fail open into random noise.

2. **The `visualize-run` CLI Command**
   - *Original behavior:* Exported an interactive HTML map projecting embeddings via t-SNE.
   - *Current action:* **Removed**. t-SNE dimensionality reduction is mathematically invalid and unstable at typical consortium sizes ($N < 10$). The resulting plots showed decorative noise rather than meaningful data. A visualization tool shouldn't be reintroduced until it maps actionable data (PCA, proper bounding, explicit outlier status).

3. **Geometric Confidence as a Decision Threshold**
   - *Original behavior:* The mathematical topology was intended to drive the iteration loop directly.
   - *Current action:* **Demoted to Telemetry**. Geometric confidence is calculated and firmly recorded in the `arbiter_decisions` table in SQLite, but it is strictly an observational metric. It does not control early-stopping, retries, or model weighting. It remains purely observational until proven to predict actual synthesis quality across larger evaluative tests.
