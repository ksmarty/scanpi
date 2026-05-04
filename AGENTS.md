# ScanPi Development Guide

## Run Commands

```bash
# Docker (primary)
docker-compose up --build

# Local development (requires scanadf, ocrmypdf, imagemagick installed)
pip install -r requirements.txt
python3 app.py
```

## Important Notes

- **Scanner hardware access**: Docker on macOS/Windows doesn't support USB passthrough. Use network scanner (eSCL/AirScan) or run SANE server on host.
- **Version**: Increment `VERSION` in `Dockerfile` (semver format) for each release.
- **Port**: Default is `1934:5000` in docker-compose.
- **Lock file**: Located at `{SCAN_DIRECTORY}/.scanlock` (inside mounted volume).

## Key Files

- `app.py` - Flask app with API endpoints for devices, capabilities, preview
- `scan_adf.sh` - Scanner script using scanadf + ocrmypdf
- `Dockerfile` - Container build (uses python:3.11-slim-bookworm)
- `docker-compose.yml` - Multi-platform config (macOS uses network_mode: host)

## API Endpoints

- `GET /` - Main UI
- `GET /api/devices` - List available scanners
- `GET /api/capabilities?scanner=<id>` - Get scanner options (source/mode/resolution)
- `POST /api/preview` - Run preview scan
- `POST /` - Submit scan (form or edited image)

## Environment Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `DEBUG` | False | |
| `ROOT_PATH` | / | |
| `SCAN_DIRECTORY` | /scans | Mount this volume |
| `SOURCES` | ADF Front,ADF Back,ADF Duplex | |
| `MODES` | Lineart,Halftone,Gray,Color | |
| `RESOLUTIONS` | 50-600 | |

## CI/CD

GitHub Actions workflow (`.github/workflows/docker.yml`) builds and pushes to ghcr.io on every push.