import json
from typing import List

import numpy as np
import plotly.graph_objects as go
from sklearn.manifold import TSNE

from .db import get_embedding_records_for_run, save_run_visualization


class EmbeddingProjector:
    def project_tsne(self, embeddings, perplexity: int = 5) -> np.ndarray:
        matrix = np.array(embeddings, dtype=float)
        if matrix.ndim != 2:
            raise ValueError("Embeddings must be a 2D array")
        if matrix.shape[0] < 2:
            return np.zeros((matrix.shape[0], 2), dtype=float)
        effective_perplexity = min(perplexity, max(1, matrix.shape[0] - 1))
        projector = TSNE(n_components=2, perplexity=effective_perplexity, init="random", random_state=42)
        return projector.fit_transform(matrix)


def generate_run_visualization(run_id: str):
    records = get_embedding_records_for_run(run_id)
    if not records:
        raise ValueError(f"No embeddings found for run '{run_id}'")

    embeddings = [json.loads(record["embedding_json"]) for record in records]
    coordinates = EmbeddingProjector().project_tsne(embeddings, perplexity=min(5, len(embeddings) - 1 or 1))

    hover_text: List[str] = []
    iterations: List[int] = []
    models: List[str] = []
    for record in records:
        iteration = int(record.get("iteration") or 1)
        model = record.get("model") or "unknown"
        iterations.append(iteration)
        models.append(model)
        hover_text.append(f"model={model}<br>iteration={iteration}")

    figure = go.Figure(
        data=[
            go.Scatter(
                x=coordinates[:, 0],
                y=coordinates[:, 1],
                mode="markers+text",
                marker={"size": 12, "color": iterations, "colorscale": "Viridis"},
                text=models,
                hovertext=hover_text,
                hoverinfo="text",
            )
        ]
    )
    figure.update_layout(title=f"Consensus Drift for {run_id}", xaxis_title="t-SNE 1", yaxis_title="t-SNE 2")
    save_run_visualization(run_id, figure.to_json())
    return figure