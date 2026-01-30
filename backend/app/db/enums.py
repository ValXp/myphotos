from __future__ import annotations

import enum


class AssetType(str, enum.Enum):
    photo = "photo"
    video = "video"
    live_photo = "live_photo"


class AssetVariantKind(str, enum.Enum):
    thumb = "thumb"
    video_transcode = "video_transcode"
    live_video = "live_video"


class JobType(str, enum.Enum):
    scan = "scan"
    metadata = "metadata"
    thumb = "thumb"
    transcode = "transcode"
    zip = "zip"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
