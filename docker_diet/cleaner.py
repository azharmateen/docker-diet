"""Safe cleanup: remove Docker resources with dry-run and confirmation."""

import subprocess
from dataclasses import dataclass, field
from typing import Optional

from .analyzer import AnalysisResult, format_size


@dataclass
class CleanupAction:
    resource_type: str  # image, container, volume, cache
    resource_id: str
    description: str
    size: int = 0
    success: bool = False
    error: Optional[str] = None


@dataclass
class CleanupResult:
    actions: list[CleanupAction] = field(default_factory=list)
    total_freed: int = 0
    total_failed: int = 0
    dry_run: bool = False

    @property
    def summary(self) -> str:
        if self.dry_run:
            return (f"DRY RUN: Would remove {len(self.actions)} resource(s), "
                    f"freeing ~{format_size(sum(a.size for a in self.actions))}")
        succeeded = sum(1 for a in self.actions if a.success)
        return (f"Removed {succeeded}/{len(self.actions)} resource(s), "
                f"freed {format_size(self.total_freed)}")


def _docker_rm(args: list[str]) -> tuple[bool, str]:
    """Run docker removal command."""
    try:
        result = subprocess.run(
            ["docker"] + args,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, ""
    except Exception as e:
        return False, str(e)


def plan_cleanup(analysis: AnalysisResult,
                 remove_dangling: bool = True,
                 remove_stopped: bool = False,
                 remove_volumes: bool = False,
                 remove_cache: bool = False,
                 old_days: Optional[int] = None) -> list[CleanupAction]:
    """Plan cleanup actions (dry run)."""
    actions = []

    if remove_dangling:
        for image in analysis.dangling_images.items:
            actions.append(CleanupAction(
                resource_type="image",
                resource_id=image.id,
                description=f"Dangling image {image.id[:12]}",
                size=image.size,
            ))

    if remove_stopped:
        containers = analysis.old_containers.items if old_days else analysis.stopped_containers.items
        for container in containers:
            actions.append(CleanupAction(
                resource_type="container",
                resource_id=container.id,
                description=f"Stopped container {container.name} ({container.image})",
                size=container.size,
            ))

    if remove_volumes:
        for volume in analysis.unused_volumes.items:
            actions.append(CleanupAction(
                resource_type="volume",
                resource_id=volume.name,
                description=f"Unused volume {volume.name[:30]}",
                size=volume.size,
            ))

    if remove_cache:
        for cache in analysis.build_cache.items:
            actions.append(CleanupAction(
                resource_type="cache",
                resource_id=cache.id,
                description=f"Build cache {cache.id[:12]} ({cache.cache_type})",
                size=cache.size,
            ))

    return actions


def execute_cleanup(actions: list[CleanupAction]) -> CleanupResult:
    """Execute planned cleanup actions."""
    result = CleanupResult()

    for action in actions:
        if action.resource_type == "image":
            success, err = _docker_rm(["rmi", action.resource_id])
        elif action.resource_type == "container":
            success, err = _docker_rm(["rm", action.resource_id])
        elif action.resource_type == "volume":
            success, err = _docker_rm(["volume", "rm", action.resource_id])
        elif action.resource_type == "cache":
            # Build cache is cleaned in bulk
            success, err = _docker_rm(["builder", "prune", "-f"])
        else:
            success, err = False, f"Unknown resource type: {action.resource_type}"

        action.success = success
        action.error = err if not success else None

        if success:
            result.total_freed += action.size
        else:
            result.total_failed += 1

        result.actions.append(action)

    return result


def quick_clean() -> CleanupResult:
    """Quick cleanup: dangling images, stopped containers, build cache."""
    result = CleanupResult()

    # Docker system prune (non-interactive)
    success, err = _docker_rm(["system", "prune", "-f"])
    if success:
        result.actions.append(CleanupAction(
            resource_type="system",
            resource_id="prune",
            description="Docker system prune (dangling images, stopped containers, unused networks)",
            success=True,
        ))
    else:
        result.actions.append(CleanupAction(
            resource_type="system",
            resource_id="prune",
            description="Docker system prune",
            success=False,
            error=err,
        ))

    return result
