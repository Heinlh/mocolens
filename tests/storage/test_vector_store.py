"""The ONNX question encoder that replaced sentence-transformers/PyTorch.

These run the real exported model (models/granite-embedding-30m). That is
the point: the index in data/curated was embedded with the PyTorch build of
the same model, so if this encoder's tokenization, CLS pooling, or
normalization ever drifts, every search_reports result silently degrades
without anything else failing.
"""
import numpy as np
import pytest

from mocolens.storage import vector_store

pytestmark = pytest.mark.skipif(
    not (vector_store.MODEL_DIR / "model.onnx").exists(),
    reason="run scripts/export_embedding_onnx.py to create the ONNX encoder",
)


def test_encode_returns_one_normalized_384_dim_vector_per_text():
    vectors = np.array(vector_store.encode(["pedestrian crashes", "speed cameras"]))
    assert vectors.shape == (2, 384)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-3)


def test_encode_places_related_text_closer_than_unrelated_text():
    query, related, unrelated = vector_store.encode([
        "How many pedestrians were hit by cars?",
        "Pedestrian collisions and injuries on county roads",
        "Chocolate cake baking instructions and oven temperature",
    ])
    assert np.dot(query, related) > np.dot(query, unrelated)


def test_encode_batches_longer_than_the_batch_size():
    # _BATCH is 32; a 40-item call must return 40 vectors, not one batch.
    assert len(vector_store.encode([f"crash {i}" for i in range(40)])) == 40


def test_encode_truncates_input_longer_than_the_model_window():
    # 512-token limit - a longer document must embed rather than raise.
    assert len(vector_store.encode(["crash " * 4000])) == 1


# --- the flat .npz index that replaced Chroma ---

def _chunk(chunk_id: str, text: str, document_id: str = "doc", **meta) -> dict:
    return {"chunk_id": chunk_id, "document_id": document_id, "text": text,
            "title": "R", "source_url": "u", **meta}


def test_indexed_document_can_be_searched(tmp_path):
    vector_store.replace_document("d", "doc", [
        _chunk("a", "Pedestrian crashes at signalized intersections"),
        _chunk("b", "Snow removal equipment procurement schedule"),
    ], persist_dir=tmp_path)
    hits = vector_store.search("d", "people hit while walking", top_k=2, persist_dir=tmp_path)
    assert [h["chunk_id"] for h in hits] == ["a", "b"]
    assert hits[0]["similarity"] > hits[1]["similarity"]


def test_reprocessing_a_document_replaces_its_chunks_rather_than_duplicating_them(tmp_path):
    vector_store.replace_document("d", "doc", [_chunk("a", "original text")], persist_dir=tmp_path)
    vector_store.replace_document("d", "doc", [_chunk("a", "replacement text")], persist_dir=tmp_path)
    embeddings, records = vector_store.load_index("d", persist_dir=tmp_path)
    assert len(records) == 1
    assert embeddings.shape[0] == 1
    assert records[0]["text"] == "replacement text"


def test_a_shorter_revision_drops_the_old_versions_trailing_chunks(tmp_path):
    """The bug replace_document exists to prevent: chunk ids are positional,
    so an upsert would leave chunk 3 of the old edition searchable forever.
    """
    vector_store.replace_document("d", "doc", [
        _chunk("doc:0", "opening section"),
        _chunk("doc:1", "middle section"),
        _chunk("doc:2", "section the county later deleted"),
    ], persist_dir=tmp_path)
    vector_store.replace_document("d", "doc", [
        _chunk("doc:0", "opening section"),
        _chunk("doc:1", "middle section"),
    ], persist_dir=tmp_path)

    embeddings, records = vector_store.load_index("d", persist_dir=tmp_path)
    assert [r["chunk_id"] for r in records] == ["doc:0", "doc:1"]
    assert embeddings.shape == (2, 384)
    assert vector_store.search("d", "section the county later deleted", persist_dir=tmp_path)[0]["chunk_id"] != "doc:2"


def test_replacing_one_document_leaves_every_other_document_indexed(tmp_path):
    vector_store.replace_document("d", "keep", [_chunk("k1", "untouched text", document_id="keep")],
                                  persist_dir=tmp_path)
    vector_store.replace_document("d", "change", [_chunk("c1", "first", document_id="change")],
                                  persist_dir=tmp_path)
    vector_store.replace_document("d", "change", [_chunk("c2", "second", document_id="change")],
                                  persist_dir=tmp_path)

    _, records = vector_store.load_index("d", persist_dir=tmp_path)
    assert sorted(r["chunk_id"] for r in records) == ["c2", "k1"]


def test_replacing_a_document_with_nothing_removes_it_from_the_index(tmp_path):
    vector_store.replace_document("d", "doc", [_chunk("a", "text")], persist_dir=tmp_path)
    assert vector_store.replace_document("d", "doc", [], persist_dir=tmp_path) == 0
    _, records = vector_store.load_index("d", persist_dir=tmp_path)
    assert records == []


def test_search_year_filter_keeps_only_matching_records(tmp_path):
    vector_store.replace_document("d", "doc", [
        _chunk("old", "vision zero plan", year=2019),
        _chunk("new", "vision zero plan", year=2025),
        _chunk("undated", "vision zero plan"),
    ], persist_dir=tmp_path)
    assert [h["chunk_id"] for h in
            vector_store.search("d", "vision zero", year_at_least=2025, persist_dir=tmp_path)] == ["new"]
    assert vector_store.search("d", "vision zero", year_at_least=2099, persist_dir=tmp_path) == []
    assert len(vector_store.search("d", "vision zero", persist_dir=tmp_path)) == 3


def test_search_on_a_missing_index_names_the_script_that_builds_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="rebuild_vector_index"):
        vector_store.search("nope", "anything", persist_dir=tmp_path)


def test_index_round_trips_without_pickle(tmp_path):
    # allow_pickle=False on load, so records must survive as plain JSON.
    vector_store.replace_document("d", "doc", [_chunk("a", "text", year=2025, page_start=3)],
                                  persist_dir=tmp_path)
    _, records = vector_store.load_index("d", persist_dir=tmp_path)
    assert records[0]["year"] == 2025
    assert records[0]["page_start"] == 3


# --- index_info: the document-level view GET /api/sources and the smoke
# checks read, so neither has to know the chunk record layout ---

def test_index_info_is_none_when_no_index_has_been_built(tmp_path):
    assert vector_store.index_info("nope", persist_dir=tmp_path) is None


def test_index_info_summarizes_documents_not_chunks(tmp_path):
    vector_store.replace_document("d", "a", [
        _chunk("a1", "one", document_id="a", year=2025, page_start=1, page_end=4),
        _chunk("a2", "two", document_id="a", year=2025, page_start=9, page_end=11),
    ], persist_dir=tmp_path)
    vector_store.replace_document("d", "b", [
        _chunk("b1", "three", document_id="b", year=2019, page_start=2, page_end=2),
    ], persist_dir=tmp_path)

    info = vector_store.index_info("d", persist_dir=tmp_path)
    assert info["chunk_count"] == 3
    assert [d["document_id"] for d in info["documents"]] == ["a", "b"]  # newest first
    assert info["documents"][0]["chunk_count"] == 2
    assert (info["documents"][0]["page_start"], info["documents"][0]["page_end"]) == (1, 11)
    assert info["built_at"] is not None
