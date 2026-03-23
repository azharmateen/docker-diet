"""Report generators: terminal, JSON, markdown."""

import json
from typing import Any

from .scanner import ScanResult
from .analyzer import AnalysisResult, format_size, group_images_by_repo


def terminal_report(scan: ScanResult, analysis: AnalysisResult) -> str:
    """Generate a rich terminal report."""
    lines = []
    lines.append("=" * 60)
    lines.append("  Docker Diet - Resource Report")
    lines.append("=" * 60)
    lines.append("")

    # Overview
    lines.append("  Overview:")
    lines.append(f"    Images:       {len(scan.images):>5}  ({format_size(scan.total_image_size)})")
    lines.append(f"    Containers:   {len(scan.containers):>5}  ({format_size(scan.total_container_size)})")
    lines.append(f"    Volumes:      {len(scan.volumes):>5}  ({format_size(scan.total_volume_size)})")
    lines.append(f"    Build Cache:  {len(scan.build_cache):>5}  ({format_size(scan.total_cache_size)})")
    lines.append(f"    {'':>14}  -------")
    lines.append(f"    Total:               {format_size(scan.total_size)}")
    lines.append("")

    # Reclaimable
    lines.append(f"  Reclaimable: {format_size(analysis.total_reclaimable)}")
    lines.append("")
    for cat in analysis.categories:
        if cat.count > 0:
            lines.append(f"    {cat.name}: {cat.count} item(s) = {format_size(cat.reclaimable_bytes)}")
            lines.append(f"      {cat.description}")
    lines.append("")

    # Images by repository
    groups = group_images_by_repo(scan.images)
    if groups:
        lines.append("  Images by Repository:")
        for repo, images in groups.items():
            total = sum(i.size for i in images)
            lines.append(f"    {repo}: {len(images)} tag(s), {format_size(total)}")
            for img in images[:3]:
                lines.append(f"      {img.tag} ({format_size(img.size)})")
            if len(images) > 3:
                lines.append(f"      ... and {len(images) - 3} more")
        lines.append("")

    # Containers
    running = [c for c in scan.containers if c.is_running]
    stopped = [c for c in scan.containers if not c.is_running]
    if scan.containers:
        lines.append(f"  Containers: {len(running)} running, {len(stopped)} stopped")
        for c in stopped[:5]:
            lines.append(f"    {c.name}: {c.image} ({c.status})")
        if len(stopped) > 5:
            lines.append(f"    ... and {len(stopped) - 5} more")
        lines.append("")

    lines.append(f"  Scan completed in {scan.scan_time:.1f}s")
    lines.append("=" * 60)
    return "\n".join(lines)


def json_report(scan: ScanResult, analysis: AnalysisResult) -> dict:
    """Generate a JSON report."""
    return {
        "overview": {
            "images": {"count": len(scan.images), "size": scan.total_image_size},
            "containers": {"count": len(scan.containers), "size": scan.total_container_size},
            "volumes": {"count": len(scan.volumes), "size": scan.total_volume_size},
            "build_cache": {"count": len(scan.build_cache), "size": scan.total_cache_size},
            "total_size": scan.total_size,
        },
        "reclaimable": {
            "total": analysis.total_reclaimable,
            "categories": {
                cat.name: {
                    "count": cat.count,
                    "size": cat.reclaimable_bytes,
                    "description": cat.description,
                }
                for cat in analysis.categories if cat.count > 0
            },
        },
        "images": [
            {
                "id": img.id[:12],
                "name": img.full_name,
                "size": img.size,
                "dangling": img.dangling,
                "created": img.created,
            }
            for img in scan.images
        ],
        "containers": [
            {
                "id": c.id[:12],
                "name": c.name,
                "image": c.image,
                "state": c.state,
                "status": c.status,
            }
            for c in scan.containers
        ],
        "volumes": [
            {
                "name": v.name,
                "driver": v.driver,
                "in_use": v.in_use,
            }
            for v in scan.volumes
        ],
        "scan_time_seconds": round(scan.scan_time, 2),
    }


def markdown_report(scan: ScanResult, analysis: AnalysisResult) -> str:
    """Generate a markdown report."""
    lines = []
    lines.append("# Docker Diet Report")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Resource | Count | Size |")
    lines.append(f"|----------|-------|------|")
    lines.append(f"| Images | {len(scan.images)} | {format_size(scan.total_image_size)} |")
    lines.append(f"| Containers | {len(scan.containers)} | {format_size(scan.total_container_size)} |")
    lines.append(f"| Volumes | {len(scan.volumes)} | {format_size(scan.total_volume_size)} |")
    lines.append(f"| Build Cache | {len(scan.build_cache)} | {format_size(scan.total_cache_size)} |")
    lines.append(f"| **Total** | | **{format_size(scan.total_size)}** |")
    lines.append("")

    # Reclaimable
    lines.append(f"## Reclaimable Space: {format_size(analysis.total_reclaimable)}")
    lines.append("")
    for cat in analysis.categories:
        if cat.count > 0:
            lines.append(f"- **{cat.name}**: {cat.count} item(s), {format_size(cat.reclaimable_bytes)}")
            lines.append(f"  - {cat.description}")
    lines.append("")

    # Images
    if scan.images:
        lines.append("## Images")
        lines.append("")
        lines.append("| Name | Size | Dangling |")
        lines.append("|------|------|----------|")
        for img in sorted(scan.images, key=lambda i: -i.size)[:20]:
            lines.append(f"| `{img.full_name}` | {format_size(img.size)} | {'Yes' if img.dangling else 'No'} |")
        if len(scan.images) > 20:
            lines.append(f"| ... | {len(scan.images) - 20} more | |")
        lines.append("")

    return "\n".join(lines)
