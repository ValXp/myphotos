from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AssetType, JobType
from app.db.models import Asset
from app.ingest.reconcile import ReconcileStats, reconcile_events
from app.ingest.scan import AssetUpsert, FullScanJob, ScanStats, upsert_asset
from app.ingest.live_photos import link_live_photo_pairs
from app.ingest.watcher import WatchEvent, WatchEventKind
from app.queue import Job, Queue

METADATA_JOB_NAME = JobType.metadata.value
THUMB_JOB_NAME = JobType.thumb.value
TRANSCODE_JOB_NAME = JobType.transcode.value


@dataclass(frozen=True)
class AssetChange:
    asset: Asset
    created: bool
    updated: bool

    @property
    def changed(self) -> bool:
        return self.created or self.updated


@dataclass
class WatchIngestStats:
    added: int = 0
    updated: int = 0
    enqueued: int = 0
    reconciled: ReconcileStats = field(default_factory=ReconcileStats)


def jobs_for_asset(asset: Asset) -> list[Job]:
    if not asset.id:
        raise ValueError("asset id is required to enqueue jobs")
    jobs = [
        Job(name=METADATA_JOB_NAME, payload={"asset_id": asset.id}),
        Job(name=THUMB_JOB_NAME, payload={"asset_id": asset.id}),
    ]
    if asset.type in {AssetType.video, AssetType.live_photo}:
        jobs.append(Job(name=TRANSCODE_JOB_NAME, payload={"asset_id": asset.id}))
    return jobs


def enqueue_for_change(queue: Queue, change: AssetChange) -> list[Job]:
    if not change.changed:
        return []
    jobs = jobs_for_asset(change.asset)
    for job in jobs:
        queue.enqueue(job)
    return jobs


def enqueue_scan_jobs(
    session: Session,
    roots: Iterable[str | Path],
    queue: Queue,
    *,
    follow_symlinks: bool = False,
) -> ScanStats:
    def on_change(upsert: AssetUpsert) -> None:
        if upsert.created:
            session.flush()
        enqueue_for_change(queue, AssetChange(upsert.asset, upsert.created, upsert.updated))

    job = FullScanJob(roots, follow_symlinks=follow_symlinks, on_change=on_change)
    stats = job.run(session)
    if _enqueue_live_photo_links(session, queue):
        session.commit()
    return stats


def apply_watch_events(
    session: Session, events: Iterable[WatchEvent], queue: Queue
) -> WatchIngestStats:
    stats = WatchIngestStats()
    reconcile_events_list: list[WatchEvent] = []

    for event in events:
        if event.kind == WatchEventKind.add:
            for path in event.paths:
                upsert = upsert_asset(session, path)
                if upsert is None:
                    continue
                if upsert.created:
                    stats.added += 1
                    session.flush()
                elif upsert.updated:
                    stats.updated += 1
                jobs = enqueue_for_change(queue, AssetChange(upsert.asset, upsert.created, upsert.updated))
                stats.enqueued += len(jobs)
        else:
            reconcile_events_list.append(event)

    if reconcile_events_list:
        stats.reconciled = reconcile_events(session, reconcile_events_list)

    stats.enqueued += _enqueue_live_photo_links(session, queue)

    return stats


def _enqueue_live_photo_links(session: Session, queue: Queue) -> int:
    assets = session.execute(select(Asset)).scalars().all()
    assets = [asset for asset in assets if asset not in session.deleted]
    links = link_live_photo_pairs(session, assets=assets)
    enqueued = 0
    for link in links:
        still = session.get(Asset, link.still_id)
        if still is None:
            continue
        jobs = jobs_for_asset(still)
        for job in jobs:
            queue.enqueue(job)
        enqueued += len(jobs)
    return enqueued
