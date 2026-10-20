import hashlib

import numpy as np
import pytest


class FakeEmbedder:
    """Deterministic bag-of-words embedder: texts that share words are close."""

    def __init__(self, dims=32):
        self.dims = dims
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        out = np.zeros((len(texts), self.dims), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in t.lower().replace("|", " ").replace(":", " ").split():
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                out[i, h % self.dims] += 1.0
            out[i, 0] += 1e-3  # never all zero
        return out / np.linalg.norm(out, axis=1, keepdims=True)


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()
