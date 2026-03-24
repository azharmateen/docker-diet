# docker-diet

[![Built with Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-blue?logo=anthropic&logoColor=white)](https://claude.ai/code)


**Interactive TUI to visualize Docker disk usage and safely clean up resources.**

See exactly where Docker is eating your disk. Tree view of images, containers, volumes, and build cache with color-coded size bars.

```
pip install docker-diet
docker-diet dashboard
```

> Visual breakdown of every byte Docker uses. One-click cleanup.

## Why docker-diet?

- **Visual TUI** - Tree view of all Docker resources with size bars and color coding
- **Safe cleanup** - Always dry-run first. Confirm before deletion. Never touches running containers
- **Smart analysis** - Groups images by repo, finds dangling images, old containers, unused volumes
- **Multiple outputs** - Terminal, JSON, markdown reports
- **Granular control** - Clean dangling images only, or go aggressive with stopped containers + volumes
- **Age filtering** - Only clean containers stopped for N+ days

## Quick Start

```bash
# Interactive TUI dashboard
docker-diet dashboard

# Quick scan and report
docker-diet scan

# Safe cleanup (dangling images only, dry run first)
docker-diet clean --dry-run
docker-diet clean

# Aggressive cleanup
docker-diet clean --dangling --stopped --volumes --cache

# Only clean old stopped containers
docker-diet clean --stopped --old-days 30

# Generate report
docker-diet report --format markdown --output report.md
```

## TUI Dashboard

Launch with `docker-diet dashboard`:

- Tree view of all Docker resources organized by category
- Size bars showing relative disk usage per category
- Color-coded: green (running), red (stopped/dangling), yellow (unused)
- Summary table with reclaimable space per category
- Quick Clean button for one-click safe cleanup
- Keyboard shortcuts: `r` refresh, `c` clean, `q` quit

## CLI Commands

| Command | Description |
|---------|-------------|
| `docker-diet scan` | Scan and show resource overview |
| `docker-diet clean` | Remove unused resources |
| `docker-diet dashboard` | Launch interactive TUI |
| `docker-diet report` | Generate detailed report |

## Cleanup Options

| Flag | Description |
|------|-------------|
| `--dangling/--no-dangling` | Dangling images (default: yes) |
| `--stopped/--no-stopped` | Stopped containers (default: no) |
| `--volumes/--no-volumes` | Unused volumes (default: no) |
| `--cache/--no-cache` | Build cache (default: no) |
| `--old-days N` | Only containers stopped N+ days |
| `--dry-run` | Show plan without executing |
| `--force` | Skip confirmation prompt |

## What Gets Analyzed

| Resource | Detection |
|----------|-----------|
| Dangling images | No tags, intermediate build layers |
| Unused images | Tagged but not used by any container |
| Stopped containers | Exited, created, dead state |
| Old containers | Stopped for N+ days |
| Unused volumes | Not mounted by any container |
| Build cache | Inactive builder cache entries |

## License

MIT
