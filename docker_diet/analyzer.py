"""Analyze Docker resources: find waste, group, and calculate reclaimable space."""

from dataclasses import dataclass, field
from typing import Optional

from .scanner import ScanResult, DockerImage, DockerContainer, DockerVolume


@dataclass
class ReclaimableCategory:
    name: str
    description: str
    items: list = field(default_factory=list)
    reclaimable_bytes: int = 0

    @property
    def count(self) -> int:
        return len(self.items)


@dataclass
class AnalysisResult:
    dangling_images: ReclaimableCategory = field(default_factory=lambda: ReclaimableCategory(
        name="Dangling Images",
        description="Images without tags (intermediate build layers)",
    ))
    unused_images: ReclaimableCategory = field(default_factory=lambda: ReclaimableCategory(
        name="Unused Images",
        description="Tagged images not used by any container",
    ))
    stopped_containers: ReclaimableCategory = field(default_factory=lambda: ReclaimableCategory(
        name="Stopped Containers",
        description="Containers that are not running",
    ))
    old_containers: ReclaimableCategory = field(default_factory=lambda: ReclaimableCategory(
        name="Old Containers",
        description="Stopped containers older than threshold",
    ))
    unused_volumes: ReclaimableCategory = field(default_factory=lambda: ReclaimableCategory(
        name="Unused Volumes",
        description="Volumes not mounted by any container",
    ))
    build_cache: ReclaimableCategory = field(default_factory=lambda: ReclaimableCategory(
        name="Build Cache",
        description="Docker build cache entries",
    ))

    @property
    def total_reclaimable(self) -> int:
        return sum([
            self.dangling_images.reclaimable_bytes,
            self.stopped_containers.reclaimable_bytes,
            self.unused_volumes.reclaimable_bytes,
            self.build_cache.reclaimable_bytes,
        ])

    @property
    def categories(self) -> list[ReclaimableCategory]:
        return [
            self.dangling_images,
            self.unused_images,
            self.stopped_containers,
            self.old_containers,
            self.unused_volumes,
            self.build_cache,
        ]


def analyze(scan: ScanResult, old_days: int = 7) -> AnalysisResult:
    """Analyze scan results to find reclaimable resources.

    Args:
        scan: Results from full_scan()
        old_days: Containers stopped for this many days are flagged
    """
    result = AnalysisResult()

    # -- Images --
    # Find which images are in use by containers
    images_in_use = set()
    for container in scan.containers:
        images_in_use.add(container.image)

    for image in scan.images:
        if image.dangling:
            result.dangling_images.items.append(image)
            result.dangling_images.reclaimable_bytes += image.size
        elif image.full_name not in images_in_use and image.id not in images_in_use:
            result.unused_images.items.append(image)
            result.unused_images.reclaimable_bytes += image.size

    # -- Containers --
    for container in scan.containers:
        if not container.is_running:
            result.stopped_containers.items.append(container)
            result.stopped_containers.reclaimable_bytes += container.size

            if container.age_days > old_days:
                result.old_containers.items.append(container)
                result.old_containers.reclaimable_bytes += container.size

    # -- Volumes --
    for volume in scan.volumes:
        if not volume.in_use:
            result.unused_volumes.items.append(volume)
            result.unused_volumes.reclaimable_bytes += volume.size

    # -- Build cache --
    for cache in scan.build_cache:
        if not cache.in_use:
            result.build_cache.items.append(cache)
            result.build_cache.reclaimable_bytes += cache.size

    return result


def group_images_by_repo(images: list[DockerImage]) -> dict[str, list[DockerImage]]:
    """Group images by repository name."""
    groups: dict[str, list[DockerImage]] = {}
    for image in images:
        repo = image.repository
        if repo not in groups:
            groups[repo] = []
        groups[repo].append(image)

    # Sort each group by size descending
    for repo in groups:
        groups[repo].sort(key=lambda i: -i.size)

    return dict(sorted(groups.items()))


def format_size(bytes_val: int) -> str:
    """Format bytes to human-readable string."""
    if bytes_val == 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(bytes_val) < 1024:
            return f"{bytes_val:.1f} {unit}" if unit != "B" else f"{bytes_val} B"
        bytes_val /= 1024
    return f"{bytes_val:.1f} PB"
