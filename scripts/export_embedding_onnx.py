"""One-off: export the query-embedding model to float16 ONNX.

Serving only needs to embed the user's question against an index that was
already built with this model. Doing that with sentence-transformers pulls
PyTorch into the API process - measured at +390 MB RSS, which alone blows
past Render's 512 MB. onnxruntime and tokenizers are small next to that,
so the serving image trades a heavy dependency for a light one plus the
artifact this writes. Run this again only if EMBEDDING_MODEL changes -
which also means re-embedding the index.

    python scripts/export_embedding_onnx.py
"""
import sys
from pathlib import Path

import onnx
import torch
from onnxruntime.transformers.float16 import convert_float_to_float16
from torch import nn
from transformers import AutoModel, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from mocolens.storage.vector_store import EMBEDDING_MODEL, MODEL_DIR  # noqa: E402


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_MODEL)
    tokenizer.save_pretrained(MODEL_DIR)
    for stale in MODEL_DIR.iterdir():
        if stale.name not in ("tokenizer.json", "model.onnx"):
            stale.unlink()

    # float32, not the checkpoint's bfloat16: onnxruntime's CPU provider has
    # no kernels for bf16 and refuses to load the session otherwise.
    model = AutoModel.from_pretrained(EMBEDDING_MODEL, dtype=torch.float32).eval()

    class Encoder(nn.Module):
        """Positional wrapper - torch.onnx.export passes inputs positionally,
        and RobertaModel.forward's second positional parameter is not
        attention_mask.
        """

        def __init__(self, model):
            super().__init__()
            self.model = model

        def forward(self, input_ids, attention_mask):
            return self.model(
                input_ids=input_ids, attention_mask=attention_mask
            ).last_hidden_state

    sample = tokenizer(["export sample"], return_tensors="pt")
    fp32_path = MODEL_DIR / "model_fp32.onnx"
    torch.onnx.export(
        Encoder(model).eval(),
        (sample["input_ids"], sample["attention_mask"]),
        str(fp32_path),
        input_names=["input_ids", "attention_mask"],
        output_names=["last_hidden_state"],
        dynamic_axes={
            name: {0: "batch", 1: "sequence"}
            for name in ("input_ids", "attention_mask", "last_hidden_state")
        },
        # opset >= 18: downgrading to 17 emits an Add that onnxruntime has
        # no CPU kernel for ("Could not find an implementation for Add(14)").
        opset_version=18,
        external_data=False,
    )

    # float16 halves the file to ~61 MB (GitHub rejects anything over 100 MB)
    # while staying retrieval-identical: cosine 0.9999999 against the float32
    # graph, versus 0.93-0.98 and a badly reordered top-5 for every int8
    # variant tried (per-tensor and per-channel, QInt8 and QUInt8).
    onnx.save(
        convert_float_to_float16(onnx.load(fp32_path), keep_io_types=True),
        MODEL_DIR / "model.onnx",
    )
    fp32_path.unlink()

    size_mb = (MODEL_DIR / "model.onnx").stat().st_size / 1e6
    print(f"wrote {MODEL_DIR / 'model.onnx'} ({size_mb:.1f} MB) + tokenizer.json")


if __name__ == "__main__":
    main()
