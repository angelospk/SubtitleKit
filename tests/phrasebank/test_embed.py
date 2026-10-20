import os

import numpy as np
import pytest

from subtitlekit.phrasebank.embed import DOC_PREFIX, QUERY_PREFIX, doc_text, query_text, truncate_normalize


def test_prefixes_follow_the_embeddinggemma_card():
    assert QUERY_PREFIX == "task: search result | query: "
    assert DOC_PREFIX == "title: none | text: "
    assert query_text("Get out.") == "task: search result | query: Get out."
    assert query_text("Get out.", intent="angry threat") == "task: search result | query: angry threat | Get out."
    assert doc_text("Φύγε.") == "title: none | text: Φύγε."


def test_truncate_normalize():
    x = np.array([[3.0, 4.0, 12.0], [1.0, 0.0, 0.0]], dtype=np.float32)
    y = truncate_normalize(x, 2)
    assert y.shape == (2, 2) and y.dtype == np.float32
    assert np.allclose(y[0], [0.6, 0.8])
    assert np.allclose(np.linalg.norm(y, axis=1), 1.0)


MODEL_DIR = os.path.expanduser(os.environ.get("PHRASEBANK_MODEL_DIR", "~/phrasebank-data/models/embeddinggemma"))


@pytest.mark.skipif(not os.path.exists(os.path.join(MODEL_DIR, "tokenizer.json")), reason="model not downloaded")
def test_gemma_onnx_ranks_the_translation_first():
    from subtitlekit.phrasebank.embed import GemmaOnnx

    e = GemmaOnnx(MODEL_DIR, dims=256)
    q = e.embed([query_text("I'm starving.")])
    d = e.embed([doc_text("Πεθαίνω της πείνας."), doc_text("Το αυτοκίνητο είναι κόκκινο.")])
    assert q.shape == (1, 256)
    s = (q @ d.T)[0]
    assert s[0] > s[1]
