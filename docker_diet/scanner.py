"""Docker resource scanner: images, containers, volumes, build cache."""

import json
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DockerImage:
    id: str
    repository: str
    tag: str
    size: int  # bytes
    created: str
    created_timestamp: float = 0.0
    dangling: bool = False
    shared_size: int = 0
    unique_size: int = 0

    @property
    def full_name(self) -> str:
        if self.repository == "<none>":
            return f"<none>:{self.id[:12]}"
        return f"{self.repository}:{self.tag}"

    @property
    def age_days(self) -> float:
        if self.created_timestamp > 0:
            return (time.time() - self.created_timestamp) / 86400
        return 0


@dataclass
class DockerContainer:
    id: str
    name: str
    image: str
    status: str
    state: str  # running, exited, paused, etc.
    size: int = 0  # writable layer size
    created: str = ""
    created_timestamp: float = 0.0

    @property
    def is_running(self) -> bool:
        return self.state == "running"

    @property
    def age_days(self) -> float:
        if self.created_timestamp > 0:
            return (time.time() - self.created_timestamp) / 86400
        return 0


@dataclass
class DockerVolume:
    name: str
    driver: str
    mountpoint: str
    size: int = 0  # estimated
    labels: dict = field(default_factory=dict)
    in_use: bool = False


@dataclass
class BuildCache:
    id: str
    cache_type: str
    size: int
    in_use: bool
    shared: bool
    created: str = ""


@dataclass
class ScanResult:
    images: list[DockerImage] = field(default_factory=list)
    containers: list[DockerContainer] = field(default_factory=list)
    volumes: list[DockerVolume] = field(default_factory=list)
    build_cache: list[BuildCache] = field(default_factory=list)
    scan_time: float = 0.0
    error: Optional[str] = None

    @property
    def total_image_size(self) -> int:
        return sum(i.size for i in self.images)

    @property
    def total_container_size(self) -> int:
        return sum(c.size for c in self.containers)

    @property
    def total_volume_size(self) -> int:
        return sum(v.size for v in self.volumes)

    @property
    def total_cache_size(self) -> int:
        return sum(c.size for c in self.build_cache)

    @property
    def total_size(self) -> int:
        return (self.total_image_size + self.total_container_size +
                self.total_volume_size + self.total_cache_size)


def _run_docker(args: list[str], timeout: int = 30) -> tuple[str, Optional[str]]:
    """Run a docker command and return (stdout, error)."""
    try:
        result = subprocess.run(
            ["docker"] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return "", result.stderr.strip()
        return result.stdout.strip(), None
    except FileNotFoundError:
        return "", "Docker not found. Is Docker installed and in PATH?"
    except subprocess.TimeoutExpired:
        return "", f"Docker command timed out after {timeout}s"


def _parse_size(size_str: str) -> int:
    """Parse Docker size string to bytes."""
    if not size_str or size_str == "0B" or size_str == "0":
        return 0

    size_str = size_str.strip().upper()
    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "TB": 1024 ** 4,
        "KIB": 1024,
        "MIB": 1024 ** 2,
        "GIB": 1024 ** 3,
    }

    for suffix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(suffix):
            try:
                return int(float(size_str[:-len(suffix)].strip()) * mult)
            except ValueError:
                return 0

    try:
        return int(float(size_str))
    except ValueError:
        return 0


def _parse_timestamp(ts_str: str) -> float:
    """Parse Docker timestamp to Unix timestamp."""
    import datetime
    if not ts_str:
        return 0.0
    try:
        # Docker outputs ISO 8601 format
        ts_str = ts_str.split(".")[0]  # Remove fractional seconds
        ts_str = ts_str.replace("T", " ").replace("Z", "")
        dt = datetime.datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
        return dt.timestamp()
    except (ValueError, IndexError):
        return 0.0


def scan_images() -> list[DockerImage]:
    """Scan all Docker images."""
    output, err = _run_docker([
        "images", "--format",
        "{{.ID}}\t{{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
    ])
    if err or not output:
        return []

    images = []
    for line in output.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue

        img = DockerImage(
            id=parts[0],
            repository=parts[1],
            tag=parts[2],
            size=_parse_size(parts[3]),
            created=parts[4],
            dangling=(parts[1] == "<none>"),
        )
        images.append(img)

    return images


def scan_containers() -> list[DockerContainer]:
    """Scan all Docker containers (running and stopped)."""
    output, err = _run_docker([
        "ps", "-a", "--format",
        "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.State}}\t{{.Size}}\t{{.CreatedAt}}"
    ])
    if err or not output:
        return []

    containers = []
    for line in output.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue

        size_str = parts[5] if len(parts) > 5 else "0B"
        # Docker size format: "32.8kB (virtual 125MB)"
        if "(" in size_str:
            size_str = size_str.split("(")[0].strip()

        container = DockerContainer(
            id=parts[0],
            name=parts[1],
            image=parts[2],
            status=parts[3],
            state=parts[4],
            size=_parse_size(size_str),
            created=parts[6] if len(parts) > 6 else "",
        )
        containers.append(container)

    return containers


def scan_volumes() -> list[DockerVolume]:
    """Scan all Docker volumes."""
    output, err = _run_docker([
        "volume", "ls", "--format", "{{.Name}}\t{{.Driver}}\t{{.Mountpoint}}"
    ])
    if err or not output:
        return []

    # Get list of volumes in use
    in_use_output, _ = _run_docker([
        "ps", "-a", "--format", "{{.Mounts}}"
    ])
    in_use_names = set()
    if in_use_output:
        for line in in_use_output.split("\n"):
            for mount in line.split(","):
                in_use_names.add(mount.strip())

    volumes = []
    for line in output.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue

        vol = DockerVolume(
            name=parts[0],
            driver=parts[1],
            mountpoint=parts[2] if len(parts) > 2 else "",
            in_use=parts[0] in in_use_names,
        )

        # Try to get volume size via inspect
        inspect_out, _ = _run_docker(["volume", "inspect", vol.name])
        if inspect_out:
            try:
                vol_data = json.loads(inspect_out)
                if vol_data and isinstance(vol_data, list):
                    vol.labels = vol_data[0].get("Labels", {}) or {}
            except json.JSONDecodeError:
                pass

        volumes.append(vol)

    return volumes


def scan_build_cache() -> list[BuildCache]:
    """Scan Docker build cache."""
    output, err = _run_docker(["builder", "du", "--verbose"], timeout=60)
    if err or not output:
        return []

    entries = []
    for line in output.split("\n"):
        if not line.strip() or line.startswith("ID") or line.startswith("Total"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue

        entry = BuildCache(
            id=parts[0],
            cache_type=parts[1] if len(parts) > 4 else "regular",
            size=_parse_size(parts[-2] if len(parts) > 3 else "0B"),
            in_use=parts[-1].lower() == "true" if len(parts) > 4 else False,
            shared="shared" in line.lower(),
        )
        entries.append(entry)

    return entries


def full_scan() -> ScanResult:
    """Perform a full Docker resource scan."""
    start = time.time()

    # Test Docker connectivity
    _, err = _run_docker(["info", "--format", "{{.ServerVersion}}"])
    if err:
        return ScanResult(error=f"Cannot connect to Docker: {err}")

    result = ScanResult(
        images=scan_images(),
        containers=scan_containers(),
        volumes=scan_volumes(),
        build_cache=scan_build_cache(),
        scan_time=time.time() - start,
    )

    return result
