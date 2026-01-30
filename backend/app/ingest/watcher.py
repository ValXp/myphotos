from __future__ import annotations

from dataclasses import dataclass
import enum
import os
from pathlib import Path
from typing import Iterable, Iterator

from app.ingest.file_types import find_live_photo_pairs, is_live_photo_pair, is_supported


class WatchEventKind(str, enum.Enum):
    add = "add"
    move = "move"
    delete = "delete"


@dataclass(frozen=True)
class WatchEvent:
    kind: WatchEventKind
    paths: tuple[Path, ...]
    previous_paths: tuple[Path, ...] | None = None

    def is_live_photo(self) -> bool:
        return len(self.paths) == 2


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int

    @classmethod
    def from_stat(cls, stat: os.stat_result) -> "FileIdentity":
        return cls(device=stat.st_dev, inode=stat.st_ino)


@dataclass(frozen=True)
class Move:
    src: Path
    dest: Path


class FilesystemWatcher:
    def __init__(self, roots: Iterable[str | Path], *, follow_symlinks: bool = False) -> None:
        self._roots = tuple(Path(root) for root in roots)
        self._follow_symlinks = follow_symlinks
        self._snapshot: dict[Path, FileIdentity] = {}

    def poll(self) -> list[WatchEvent]:
        new_snapshot = _snapshot_paths(self._roots, follow_symlinks=self._follow_symlinks)
        events = _diff_snapshots(self._snapshot, new_snapshot)
        self._snapshot = new_snapshot
        return events

    def prime(self) -> None:
        self._snapshot = _snapshot_paths(self._roots, follow_symlinks=self._follow_symlinks)


def iter_watch_paths(
    roots: Iterable[str | Path], *, follow_symlinks: bool = False
) -> Iterator[Path]:
    seen: set[Path] = set()
    for root in roots:
        resolved = Path(root).expanduser().resolve(strict=False)
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


def _snapshot_paths(
    roots: Iterable[Path], *, follow_symlinks: bool = False
) -> dict[Path, FileIdentity]:
    entries: dict[Path, FileIdentity] = {}
    for path in iter_watch_paths(roots, follow_symlinks=follow_symlinks):
        if not is_supported(path):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        entries[path] = FileIdentity.from_stat(stat)
    return entries


def _diff_snapshots(
    old: dict[Path, FileIdentity], new: dict[Path, FileIdentity]
) -> list[WatchEvent]:
    old_paths = set(old)
    new_paths = set(new)
    added = new_paths - old_paths
    deleted = old_paths - new_paths

    moves = _detect_moves(old, new, added, deleted)
    moved_old = {move.src for move in moves}
    moved_new = {move.dest for move in moves}
    added = added - moved_new
    deleted = deleted - moved_old

    events: list[WatchEvent] = []
    pair_move_events, remaining_moves = _group_live_photo_moves(moves)
    events.extend(pair_move_events)
    events.extend(_move_events(remaining_moves))
    events.extend(_add_delete_events(WatchEventKind.add, added))
    events.extend(_add_delete_events(WatchEventKind.delete, deleted))
    return events


def _detect_moves(
    old: dict[Path, FileIdentity],
    new: dict[Path, FileIdentity],
    added: set[Path],
    deleted: set[Path],
) -> list[Move]:
    old_by_inode = _index_by_inode(old)
    moves: list[Move] = []
    for new_path in sorted(added, key=_path_sort_key):
        identity = new[new_path]
        key = (identity.device, identity.inode)
        old_path = old_by_inode.get(key)
        if old_path is None:
            continue
        if old_path == new_path:
            continue
        if old_path not in deleted:
            continue
        moves.append(Move(src=old_path, dest=new_path))
    return moves


def _index_by_inode(snapshot: dict[Path, FileIdentity]) -> dict[tuple[int, int], Path | None]:
    mapping: dict[tuple[int, int], Path | None] = {}
    for path, identity in snapshot.items():
        key = (identity.device, identity.inode)
        if key in mapping:
            mapping[key] = None
        else:
            mapping[key] = path
    return mapping


def _group_live_photo_moves(moves: list[Move]) -> tuple[list[WatchEvent], list[Move]]:
    if not moves:
        return [], []
    move_by_src = {move.src: move.dest for move in moves}
    pairs = find_live_photo_pairs(move_by_src.keys())
    events: list[WatchEvent] = []
    used: set[Path] = set()
    for pair in sorted(pairs, key=lambda item: (_path_sort_key(item.still), _path_sort_key(item.video))):
        if pair.still in used or pair.video in used:
            continue
        dest_still = move_by_src.get(pair.still)
        dest_video = move_by_src.get(pair.video)
        if dest_still is None or dest_video is None:
            continue
        if not is_live_photo_pair(dest_still, dest_video):
            continue
        used.add(pair.still)
        used.add(pair.video)
        events.append(
            WatchEvent(
                kind=WatchEventKind.move,
                paths=(dest_still, dest_video),
                previous_paths=(pair.still, pair.video),
            )
        )
    events.sort(key=lambda event: _path_sort_key(event.previous_paths[0]))
    remaining = [move for move in moves if move.src not in used]
    return events, remaining


def _move_events(moves: list[Move]) -> list[WatchEvent]:
    events: list[WatchEvent] = []
    for move in sorted(moves, key=lambda item: (_path_sort_key(item.src), _path_sort_key(item.dest))):
        events.append(
            WatchEvent(
                kind=WatchEventKind.move,
                paths=(move.dest,),
                previous_paths=(move.src,),
            )
        )
    return events


def _add_delete_events(kind: WatchEventKind, paths: Iterable[Path]) -> list[WatchEvent]:
    events: list[WatchEvent] = []
    for group in _group_live_photo_paths(paths):
        events.append(WatchEvent(kind=kind, paths=group))
    return events


def _group_live_photo_paths(paths: Iterable[Path]) -> list[tuple[Path, ...]]:
    ordered = sorted(paths, key=_path_sort_key)
    pairs = find_live_photo_pairs(ordered)
    used: set[Path] = set()
    groups: list[tuple[Path, ...]] = []
    for pair in sorted(pairs, key=lambda item: (_path_sort_key(item.still), _path_sort_key(item.video))):
        if pair.still in used or pair.video in used:
            continue
        used.add(pair.still)
        used.add(pair.video)
        groups.append((pair.still, pair.video))
    for path in ordered:
        if path in used:
            continue
        groups.append((path,))
    return groups


def _path_sort_key(path: Path) -> str:
    return str(path)
