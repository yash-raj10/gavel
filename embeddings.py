"""
Turns text into a vector, for Question similarity search.

Local, free, no API key (sentence-transformers / all-MiniLM-L6-v2). Kept
separate from judge.py (laya) because the two models are tuned for different
jobs: this one for "how similar are these two pieces of text", laya for
"what's the probability the answer to this question is yes".
"""

from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def embed(text: str) -> list[float]:
    """Returns a normalized embedding vector for one piece of text."""
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


if __name__ == "__main__":
    v = embed("which tickets sound angry?")
    print(len(v), v[:5])
