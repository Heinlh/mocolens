"""Change-detection tests for processing/runner.process_domain (§8.3, §24).

Docling and the embedding model never run here: the subprocess that does the
real work is replaced with a fake that writes the chunk file, so these test
the decision - reprocess or skip - rather than the parsing.
"""
import json
from pathlib import Path

import pytest

from mocolens.processing import runner


@pytest.fixture
def lake(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(runner, "FAILURE_LOG", tmp_path / "logs" / "failures.jsonl")
    return tmp_path


def _write_manifest(lake: Path, domain: str, documents: list[dict]) -> None:
    manifest = lake / "data" / "raw" / "documents" / domain / "manifest.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        "".join(json.dumps(doc) + "\n" for doc in documents), encoding="utf-8"
    )


def _document(lake: Path, doc_id: str, content_hash: str, *, exists: bool = True) -> dict:
    pdf = lake / "data" / "raw" / "documents" / "d" / "PDFs" / f"{doc_id}.pdf"
    if exists:
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.4 fake")
    return {
        "document_id": doc_id,
        "content_hash": content_hash,
        "local_path": str(pdf),
        "source_url": f"https://example.gov/{doc_id}.pdf",
    }


class FakeRun:
    """Stands in for subprocess.run, recording which documents were processed."""

    def __init__(self, lake: Path, chunks_per_document: int = 3, returncode: int = 0):
        self.lake = lake
        self.chunks_per_document = chunks_per_document
        self.returncode = returncode
        self.processed: list[str] = []

    def __call__(self, argv, **kwargs):
        domain, doc_id = argv[-2], argv[-1]
        self.processed.append(doc_id)
        if self.returncode == 0:
            chunks_dir = self.lake / "data" / "processed" / "documents" / domain / "chunks"
            chunks_dir.mkdir(parents=True, exist_ok=True)
            (chunks_dir / f"{doc_id}.jsonl").write_text(
                "".join(json.dumps({"chunk_id": f"{doc_id}:{i}"}) + "\n"
                        for i in range(self.chunks_per_document)),
                encoding="utf-8",
            )
        return type("Result", (), {"returncode": self.returncode, "stderr": "boom"})()


def test_first_run_processes_every_document(lake, monkeypatch):
    _write_manifest(lake, "d", [_document(lake, "a", "h1"), _document(lake, "b", "h2")])
    fake = FakeRun(lake)
    monkeypatch.setattr(runner.subprocess, "run", fake)

    stats = runner.process_domain("d")
    assert sorted(fake.processed) == ["a", "b"]
    assert stats["documents_processed"] == 2
    assert stats["chunks_created"] == 6


def test_second_run_over_unchanged_documents_processes_nothing(lake, monkeypatch):
    _write_manifest(lake, "d", [_document(lake, "a", "h1"), _document(lake, "b", "h2")])
    monkeypatch.setattr(runner.subprocess, "run", FakeRun(lake))
    runner.process_domain("d")

    second = FakeRun(lake)
    monkeypatch.setattr(runner.subprocess, "run", second)
    stats = runner.process_domain("d")

    assert second.processed == []
    assert stats["documents_skipped"] == 2
    assert stats["documents_processed"] == 0


def test_only_the_document_whose_content_changed_is_reprocessed(lake, monkeypatch):
    """§24's requirement: one changed report must not rebuild the corpus."""
    _write_manifest(lake, "d", [_document(lake, "a", "h1"), _document(lake, "b", "h2")])
    monkeypatch.setattr(runner.subprocess, "run", FakeRun(lake))
    runner.process_domain("d")

    # The county republishes document b at the same URL with new content.
    _write_manifest(lake, "d", [_document(lake, "a", "h1"), _document(lake, "b", "h2-revised")])
    second = FakeRun(lake)
    monkeypatch.setattr(runner.subprocess, "run", second)
    stats = runner.process_domain("d")

    assert second.processed == ["b"]
    assert stats["documents_processed"] == 1
    assert stats["documents_skipped"] == 1


def test_a_republished_document_is_not_skipped_just_because_chunks_exist(lake, monkeypatch):
    """The bug this replaced: skipping on chunk-file existence alone kept the
    superseded text searchable after the PDF beside it had changed.
    """
    _write_manifest(lake, "d", [_document(lake, "a", "h1")])
    monkeypatch.setattr(runner.subprocess, "run", FakeRun(lake))
    runner.process_domain("d")
    chunks = lake / "data" / "processed" / "documents" / "d" / "chunks" / "a.jsonl"
    assert chunks.exists()

    _write_manifest(lake, "d", [_document(lake, "a", "h1-revised")])
    second = FakeRun(lake)
    monkeypatch.setattr(runner.subprocess, "run", second)
    runner.process_domain("d")
    assert second.processed == ["a"]


def test_force_reprocesses_unchanged_documents(lake, monkeypatch):
    _write_manifest(lake, "d", [_document(lake, "a", "h1")])
    monkeypatch.setattr(runner.subprocess, "run", FakeRun(lake))
    runner.process_domain("d")

    second = FakeRun(lake)
    monkeypatch.setattr(runner.subprocess, "run", second)
    runner.process_domain("d", force=True)
    assert second.processed == ["a"]


def test_a_tree_with_no_state_file_reprocesses_rather_than_assuming_it_is_current(lake, monkeypatch):
    _write_manifest(lake, "d", [_document(lake, "a", "h1")])
    monkeypatch.setattr(runner.subprocess, "run", FakeRun(lake))
    runner.process_domain("d")

    (lake / "data" / "processed" / "documents" / "d" / runner.STATE_FILE).unlink()
    second = FakeRun(lake)
    monkeypatch.setattr(runner.subprocess, "run", second)
    assert runner.process_domain("d")["documents_processed"] == 1


def test_corrupt_state_file_reprocesses_instead_of_crashing(lake, monkeypatch):
    _write_manifest(lake, "d", [_document(lake, "a", "h1")])
    monkeypatch.setattr(runner.subprocess, "run", FakeRun(lake))
    runner.process_domain("d")

    state_path = lake / "data" / "processed" / "documents" / "d" / runner.STATE_FILE
    state_path.write_text("{not json", encoding="utf-8")

    second = FakeRun(lake)
    monkeypatch.setattr(runner.subprocess, "run", second)
    assert runner.process_domain("d")["documents_processed"] == 1


def test_a_failed_document_is_retried_on_the_next_run(lake, monkeypatch):
    _write_manifest(lake, "d", [_document(lake, "a", "h1")])
    failing = FakeRun(lake, returncode=1)
    monkeypatch.setattr(runner.subprocess, "run", failing)
    stats = runner.process_domain("d")
    assert stats["documents_failed"] == 1
    assert runner.load_state("d") == {}, "a failure must not be recorded as processed"

    succeeding = FakeRun(lake)
    monkeypatch.setattr(runner.subprocess, "run", succeeding)
    assert runner.process_domain("d")["documents_processed"] == 1


def test_a_failure_writes_a_diagnosable_log_entry(lake, monkeypatch):
    _write_manifest(lake, "d", [_document(lake, "a", "h1")])
    monkeypatch.setattr(runner.subprocess, "run", FakeRun(lake, returncode=1))
    runner.process_domain("d")

    entry = json.loads(runner.FAILURE_LOG.read_text(encoding="utf-8").splitlines()[0])
    assert entry["document_id"] == "a"
    assert entry["returncode"] == 1
    assert "boom" in entry["stderr_tail"]


def test_state_is_saved_per_document_so_a_killed_run_keeps_its_progress(lake, monkeypatch):
    _write_manifest(lake, "d", [_document(lake, "a", "h1"), _document(lake, "b", "h2")])

    fake = FakeRun(lake)

    def run_then_die(argv, **kwargs):
        result = fake(argv, **kwargs)
        if len(fake.processed) == 2:
            raise KeyboardInterrupt("run killed partway through")
        return result

    monkeypatch.setattr(runner.subprocess, "run", run_then_die)
    with pytest.raises(KeyboardInterrupt):
        runner.process_domain("d")

    # The first document finished before the interrupt, so it must be recorded.
    assert list(runner.load_state("d")) == [fake.processed[0]]


def test_a_document_whose_file_is_missing_is_skipped_not_failed(lake, monkeypatch):
    _write_manifest(lake, "d", [_document(lake, "a", "h1", exists=False)])
    fake = FakeRun(lake)
    monkeypatch.setattr(runner.subprocess, "run", fake)

    stats = runner.process_domain("d")
    assert fake.processed == []
    assert stats == {"documents_processed": 0, "documents_skipped": 1,
                     "documents_failed": 0, "chunks_created": 0}


def test_an_empty_manifest_is_a_no_op(lake, monkeypatch):
    _write_manifest(lake, "d", [])
    monkeypatch.setattr(runner.subprocess, "run", FakeRun(lake))
    assert runner.process_domain("d") == {"documents_processed": 0, "documents_skipped": 0,
                                          "documents_failed": 0, "chunks_created": 0}
