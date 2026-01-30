from __future__ import annotations

from dataclasses import dataclass, field
import mimetypes
import os
from pathlib import Path
from typing import Iterable, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AssetType
from app.db.models import Asset
from app.ingest.file_types import is_image, is_supported, is_video


@dataclass
class ScanStats:
    scanned: int = 0
    supported: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: list[str] = field(default_factory=list)


class FullScanJob:
    def __init__(self, roots: Iterable[str | Path], *, follow_symlinks: bool = False) -> None:
        self._roots = tuple(Path(root) for root in roots)
        self._follow_symlinks = follow_symlinks

    def run(self, session: Session) -> ScanStats:
        stats = ScanStats()
        for path in iter_scan_paths(
            self._roots, stats=stats, follow_symlinks=self._follow_symlinks
        ):
            stats.scanned += 1
            if not is_supported(path):
                continue
            stats.supported += 1
            try:
                stat = path.stat()
            except OSError as exc:
                stats.errors.append(f"{path}: {exc}")
                continue
            size = stat.st_size
            device = stat.st_dev
            inode = stat.st_ino
            mtime_ns = stat.st_mtime_ns
            mime = guess_mime(path)
            asset_type = asset_type_for_path(path)
            normalized = normalize_path(path)
            asset = session.execute(
                select(Asset).where(Asset.original_path == normalized)
            ).scalar_one_or_none()
            if asset is None:
                session.add(
                    Asset(
                        type=asset_type,
                        original_path=normalized,
                        original_bytes=size,
                        original_mime=mime,
                        original_device=device,
                        original_inode=inode,
                        original_mtime_ns=mtime_ns,
                    )
                )
                stats.created += 1
            else:
                if _update_asset(asset, asset_type, size, mime, device, inode, mtime_ns):
                    stats.updated += 1
                else:
                    stats.unchanged += 1
        session.commit()
        return stats


def run_full_scan(
    session: Session, roots: Iterable[str | Path], *, follow_symlinks: bool = False
) -> ScanStats:
    return FullScanJob(roots, follow_symlinks=follow_symlinks).run(session)


def iter_scan_paths(
    roots: Iterable[Path], *, stats: ScanStats | None = None, follow_symlinks: bool = False
) -> Iterator[Path]:
    seen: set[Path] = set()
    for root in roots:
        resolved = root.expanduser().resolve(strict=False)
        if resolved in seen:
            continue
        if resolved.is_file():
            seen.add(resolved)
            yield resolved
            continue
        if resolved.is_dir():
            for dirpath, _, filenames in os.walk(resolved, followlinks=follow_symlinks):
                for filename in filenames:
                    candidate = Path(dirpath) / filename
                    path = candidate.resolve(strict=False)
                    if path in seen:
                        continue
                    seen.add(path)
                    yield path
            continue
        if stats is not None:
            stats.errors.append(f"{resolved}: path not found")


def asset_type_for_path(path: Path) -> AssetType:
    if is_image(path):
        return AssetType.photo
    if is_video(path):
        return AssetType.video
    raise ValueError(f"unsupported asset type for {path}")


def guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name, strict=False)
    if mime:
        return mime
    extension = path.suffix.lower().lstrip(".")
    if is_image(path):
        return f"image/{extension}" if extension else "image/*"
    if is_video(path):
        return f"video/{extension}" if extension else "video/*"
    return "application/octet-stream"


def normalize_path(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def _update_asset(
    asset: Asset,
    asset_type: AssetType,
    size: int,
    mime: str,
    device: int,
    inode: int,
    mtime_ns: int,
) -> bool:
    changed = False
    if asset.type != asset_type:
        asset.type = asset_type
        changed = True
    if asset.original_bytes != size:
        asset.original_bytes = size
        changed = True
    if asset.original_mime != mime:
        asset.original_mime = mime
        changed = True
    if asset.original_device != device:
        asset.original_device = device
        changed = True
    if asset.original_inode != inode:
        asset.original_inode = inode
        changed = True
    if asset.original_mtime_ns != mtime_ns:
        asset.original_mtime_ns = mtime_ns
        changed = True
    return changed
