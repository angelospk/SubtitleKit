"""EmbeddingGemma on ONNX: query/document prefixes, batching, truncation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

QUERY_PREFIX = "task: search result | query: "
DOC_PREFIX = "title: none | text: "
MAX_TOKENS = 256


def query_text(text: str, intent: Optional[str] = None) -> str:
    """Search query with the card's task prefix and an optional intent."""
    core = f"{intent} | {text}" if intent else text
    return QUERY_PREFIX + core


def doc_text(text: str) -> str:
    """Document text with the card's title prefix."""
    return DOC_PREFIX + text


def truncate_normalize(x: np.ndarray, dims: int) -> np.ndarray:
    """First ``dims`` columns as float32, each row L2-normalised."""
    y = np.asarray(x, dtype=np.float32)[:, :dims].copy()
    norms = np.linalg.norm(y, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (y / norms).astype(np.float32)


class GemmaOnnx:
    """Quantised EmbeddingGemma sentence embeddings via onnxruntime."""

    def __init__(self, model_dir: str, dims: int = 256, threads: int = 8, batch: int = 32) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.model_dir = Path(os.path.expanduser(str(model_dir)))
        self.dims = int(dims)
        self.batch = int(batch)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = int(threads)
        self.session = ort.InferenceSession(
            str(self.model_dir / "onnx" / "model_quantized.onnx"), opts,
            providers=["CPUExecutionProvider"],
        )
        self.tokenizer = Tokenizer.from_file(str(self.model_dir / "tokenizer.json"))
        self.tokenizer.enable_padding(pad_id=0, pad_token="<pad>")
        self.tokenizer.enable_truncation(max_length=MAX_TOKENS)

    def embed(self, texts: Iterable[str]) -> np.ndarray:
        """Embed texts; identical texts are sorted by length, results keep input order."""
        items = [str(t) for t in texts]
        if not items:
            return np.zeros((0, self.dims), dtype=np.float32)
        order = sorted(range(len(items)), key=lambda i: len(items[i]))
        out = np.zeros((len(items), self.dims), dtype=np.float32)
        for start in range(0, len(order), self.batch):
            idx = order[start:start + self.batch]
            encodings = self.tokenizer.encode_batch([items[i] for i in idx])
            feed = {
                "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
            }
            hidden = self.session.run(None, feed)[1]
            out[idx] = truncate_normalize(hidden, self.dims)
        return out
