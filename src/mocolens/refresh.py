"""One scheduled refresh of a domain, end to end (architecture doc §24).

    ingest (API + documents)
      -> curate structured tables
      -> reprocess only the documents whose content changed
      -> smoke checks

Each stage is the same entry point a person runs by hand
(scripts/ingest.py, build_curated_tables.py, rebuild_vector_index.py); this
module only sequences them and decides what a failure means. That keeps one
implementation of each stage, so a scheduled run and a manual run cannot
drift apart.

Two decisions worth stating:

* Document processing is change-driven, not forced. processing/runner.py
  compares each document's manifest content hash against the hash it was last
  processed at, so an unchanged corpus costs nothing and a single revised
  report re-embeds only itself (§24: "Do not rebuild the entire vector
  database if only one document changed").
* The structured tables are rebuilt in full every run. They are derived from
  one Socrata snapshot in a few seconds, and a full rebuild is the only way a
  correction upstream - a crash reclassified, a location fixed - actually
  reaches the curated layer.

Stages are independent enough to be useful alone: if document ingestion fails
because the county's site is down, the crash tables are still refreshed and
the run reports a partial success rather than throwing all of it away.
"""
import logging
from dataclasses import dataclass, field

from . import smoke
from .ingestion import runner as ingestion_runner
from .processing import curate
from .processing import runner as processing_runner
from .processing.quality import QualityError

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    name: str
    ok: bool
    detail: str
    stats: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{'ok' if self.ok else 'FAILED'}] {self.name}: {self.detail}"


@dataclass
class RefreshResult:
    domain: str
    stages: list[StageResult] = field(default_factory=list)
    checks: list[smoke.SmokeResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True only if every stage ran and no hard smoke check failed.

        Soft check failures - a stale snapshot, say - are reported but do not
        fail the run, matching processing/quality.py's split.
        """
        return all(stage.ok for stage in self.stages) and not smoke.failures(self.checks)

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "ok": self.ok,
            "stages": [vars(stage) for stage in self.stages],
            "checks": [vars(check) for check in self.checks],
        }


def _ingest(domain: str, result: RefreshResult) -> None:
    """Extract layer. A document-source failure must not stop the API refresh,
    so the two source kinds are run separately.
    """
    for name, kwargs in (("ingest_api", {"api_only": True}), ("ingest_documents", {"documents_only": True})):
        try:
            stats = ingestion_runner.run(domain, **kwargs)
            payload = stats.get("api") or stats.get("documents") or {}
            result.stages.append(StageResult(
                name=name, ok=True,
                detail=", ".join(f"{k}={v}" for k, v in payload.items()) or "nothing to do",
                stats=payload,
            ))
        except Exception as exc:  # noqa: BLE001 - network, parsing, or disk; all are "this stage failed"
            logger.exception("%s failed for domain %s", name, domain)
            result.stages.append(StageResult(name=name, ok=False, detail=f"{type(exc).__name__}: {exc}"))


def _curate(domain: str, result: RefreshResult) -> None:
    try:
        curated = curate.curate_domain(domain)
        result.stages.append(StageResult(
            name="curate", ok=True,
            detail=f"snapshot {curated['snapshot_dir']}, "
                   + ", ".join(f"{t}={c:,}" for t, c in curated["row_counts"].items()),
            stats=curated["row_counts"],
        ))
    except QualityError as exc:
        # A hard quality check already refused to publish the build; say so
        # in those terms rather than as a generic crash.
        result.stages.append(StageResult(name="curate", ok=False, detail=f"quality check failed: {exc}"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("curation failed for domain %s", domain)
        result.stages.append(StageResult(name="curate", ok=False, detail=f"{type(exc).__name__}: {exc}"))


def _process_documents(domain: str, force: bool, result: RefreshResult) -> None:
    try:
        stats = processing_runner.process_domain(domain, force=force)
        # A document that failed to parse is a real problem, but the other
        # documents and the whole structured side are still fine, so the run
        # continues and reports it.
        result.stages.append(StageResult(
            name="process_documents",
            ok=stats["documents_failed"] == 0,
            detail=(f"{stats['documents_processed']} processed "
                    f"({stats['chunks_created']} chunks), "
                    f"{stats['documents_skipped']} unchanged, "
                    f"{stats['documents_failed']} failed"),
            stats=stats,
        ))
    except Exception as exc:  # noqa: BLE001
        logger.exception("document processing failed for domain %s", domain)
        result.stages.append(StageResult(name="process_documents", ok=False, detail=f"{type(exc).__name__}: {exc}"))


def run_refresh(
    domain: str,
    *,
    skip_ingest: bool = False,
    force_documents: bool = False,
) -> RefreshResult:
    """Run one full refresh for a domain and check the result.

    `skip_ingest` reruns curation, processing, and the checks over the raw lake
    already on disk - useful for re-deriving artifacts after a code change
    without re-downloading from the county.
    `force_documents` reprocesses every document, bypassing change detection.
    """
    result = RefreshResult(domain=domain)
    # Captured before curation overwrites it, so the row-loss check compares
    # against the build this run replaces.
    previous_counts = (curate.build_info(domain) or {}).get("row_counts")

    if not skip_ingest:
        _ingest(domain, result)
    _curate(domain, result)
    _process_documents(domain, force_documents, result)

    result.checks = smoke.run_smoke_checks(domain, previous_counts=previous_counts)
    return result
