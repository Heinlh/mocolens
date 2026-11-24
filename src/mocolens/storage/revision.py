from pathlib import Path


def file_revision(path: Path) -> tuple[int, int, int] | None:
    """Cheap cache key for a file that may be rewritten, replaced or removed."""
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_ino, stat.st_size, stat.st_mtime_ns
