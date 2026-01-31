from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import mimetypes
import os
from pathlib import Path
from typing import Callable, Iterable, Iterator

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


@dataclass(frozen=True)
class AssetUpsert:
    asset: Asset
    created: bool
    updated: bool

    @property
    def changed(self) -> bool:
        return self.created or self.updated


AssetChangeCallback = Callable[[AssetUpsert], None]


class FullScanJob:
    def __init__(
        self,
        roots: Iterable[str | Path],
        *,
        follow_symlinks: bool = False,
        on_change: AssetChangeCallback | None = None,
        mark_gone: bool = True,
    ) -> None:
        self._roots = tuple(Path(root) for root in roots)
        self._follow_symlinks = follow_symlinks
        self._on_change = on_change
        self._mark_gone = mark_gone

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
            upsert = _upsert_asset_from_stat(session, path, stat)
            if upsert.created:
                stats.created += 1
            elif upsert.updated:
                stats.updated += 1
            else:
                stats.unchanged += 1
            if upsert.changed and self._on_change is not None:
                if upsert.created:
                    session.flush()
                self._on_change(upsert)

        if self._mark_gone:
            _mark_missing_assets_gone(session, self._roots)

        session.commit()
        return stats


def run_full_scan(
    session: Session,
    roots: Iterable[str | Path],
    *,
    follow_symlinks: bool = False,
    on_change: AssetChangeCallback | None = None,
    mark_gone: bool = True,
) -> ScanStats:
    return FullScanJob(
        roots,
        follow_symlinks=follow_symlinks,
        on_change=on_change,
        mark_gone=mark_gone,
    ).run(session)


def upsert_asset(session: Session, path: Path) -> AssetUpsert | None:
    if not is_supported(path):
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    return _upsert_asset_from_stat(session, path, stat)


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


def _upsert_asset_from_stat(
    session: Session, path: Path, stat: os.stat_result
) -> AssetUpsert:
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
        asset = Asset(
            type=asset_type,
            original_path=normalized,
            original_bytes=size,
            original_mime=mime,
            original_device=device,
            original_inode=inode,
            original_mtime_ns=mtime_ns,
            gone=False,
            gone_at=None,
        )
        session.add(asset)
        return AssetUpsert(asset=asset, created=True, updated=False)

    # If the asset was previously marked gone but the file exists again, revive it.
    if asset.gone:
        asset.gone = False
        asset.gone_at = None

    updated = _update_asset(asset, asset_type, size, mime, device, inode, mtime_ns)
    return AssetUpsert(asset=asset, created=False, updated=updated)


def _mark_missing_assets_gone(session: Session, roots: Iterable[Path]) -> None:
    """Mark assets as gone when their source file no longer exists.

    We do not delete rows; assets can be revived if a file reappears at the same path.
    """

    now = datetime.now(timezone.utc)

    for root in roots:
        resolved = root.expanduser().resolve(strict=False)
        if resolved.is_file():
            candidates = session.execute(
                select(Asset).where(Asset.original_path == normalize_path(resolved))
            ).scalars().all()
        else:
            prefix = normalize_path(resolved)
            if not prefix.endswith(os.sep):
                prefix += os.sep
            candidates = session.execute(
                select(Asset).where(Asset.original_path.like(prefix + "%"))
            ).scalars().all()

        for asset in candidates:
            # If the file exists, ensure it isn't marked gone.
            if Path(asset.original_path).exists():
                continue
            if asset.gone:
                continue
            asset.gone = True
            asset.gone_at = now


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
