from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Asset
from app.ingest.scan import asset_type_for_path, guess_mime, normalize_path
from app.ingest.watcher import WatchEvent, WatchEventKind


@dataclass(frozen=True)
class FileSignature:
    device: int
    inode: int
    size: int
    mtime_ns: int

    @classmethod
    def from_stat(cls, stat: os.stat_result) -> "FileSignature":
        return cls(
            device=stat.st_dev,
            inode=stat.st_ino,
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
        )


@dataclass
class ReconcileStats:
    moved: int = 0
    deleted: int = 0
    unmatched_moves: int = 0
    missing_deletes: int = 0


def reconcile_events(session: Session, events: Iterable[WatchEvent]) -> ReconcileStats:
    stats = ReconcileStats()
    for event in events:
        if event.kind == WatchEventKind.move:
            moved = _apply_move_event(session, event)
            stats.moved += moved
            if moved == 0:
                stats.unmatched_moves += 1
        elif event.kind == WatchEventKind.delete:
            removed = _apply_delete_event(session, event)
            stats.deleted += removed
            if removed == 0:
                stats.missing_deletes += 1
    return stats


def _apply_move_event(session: Session, event: WatchEvent) -> int:
    previous_paths = event.previous_paths or ()
    moved = 0
    for index, dest_path in enumerate(event.paths):
        previous = previous_paths[index] if index < len(previous_paths) else None
        if _reconcile_move(session, dest_path, previous) is not None:
            moved += 1
    return moved


def _apply_delete_event(session: Session, event: WatchEvent) -> int:
    removed = 0
    for path in event.paths:
        if _delete_asset(session, path):
            removed += 1
    return removed


def _reconcile_move(session: Session, dest_path: Path, previous: Path | None) -> Asset | None:
    try:
        stat = dest_path.stat()
    except OSError:
        return None

    if previous is not None:
        asset = _asset_by_path(session, previous)
        if asset is not None:
            _apply_file_metadata(asset, dest_path, stat)
            return asset

    signature = FileSignature.from_stat(stat)
    asset = _asset_by_signature(session, signature)
    if asset is not None:
        _apply_file_metadata(asset, dest_path, stat)
        return asset

    file_hash = _hash_file(dest_path)
    if file_hash is None:
        return None

    asset = _asset_by_hash(session, file_hash)
    if asset is not None:
        _apply_file_metadata(asset, dest_path, stat)
        return asset

    return None


def _delete_asset(session: Session, path: Path) -> bool:
    asset = _asset_by_path(session, path)
    if asset is None:
        return False
    session.delete(asset)
    return True


def _asset_by_path(session: Session, path: Path) -> Asset | None:
    normalized = normalize_path(path)
    return session.execute(
        select(Asset).where(Asset.original_path == normalized)
    ).scalar_one_or_none()


def _asset_by_signature(session: Session, signature: FileSignature) -> Asset | None:
    return session.execute(
        select(Asset).where(
            Asset.original_device == signature.device,
            Asset.original_inode == signature.inode,
            Asset.original_bytes == signature.size,
            Asset.original_mtime_ns == signature.mtime_ns,
        )
    ).scalar_one_or_none()


def _asset_by_hash(session: Session, digest: str) -> Asset | None:
    return session.execute(select(Asset).where(Asset.hash == digest)).scalar_one_or_none()


def _apply_file_metadata(asset: Asset, path: Path, stat: os.stat_result) -> None:
    asset.original_path = normalize_path(path)
    asset.original_bytes = stat.st_size
    asset.original_device = stat.st_dev
    asset.original_inode = stat.st_ino
    asset.original_mtime_ns = stat.st_mtime_ns
    asset.original_mime = guess_mime(path)
    asset.type = asset_type_for_path(path)


def _hash_file(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            hasher = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
            return hasher.hexdigest()
    except OSError:
        return None
