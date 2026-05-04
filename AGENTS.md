# ScanPi Development Guide

## Run Commands

```bash
# Docker (primary)
docker-compose up -d
docker-compose logs -f

# Build and run from source
docker-compose up --build

# Local development
pip install -r requirements.txt
python3 app.py
```

## Important Notes

- **Always commit after making changes.** Every completed change should be committed immediately before moving on.
- **Scanner hardware access**: Docker on macOS/Windows doesn't support USB passthrough. Use network scanner (eSCL/AirScan) or run SANE server on host.
- **Version**: Increment `VERSION` in `Dockerfile` (semver format) for each release.
- **Port**: Default is `5123:5000` in docker-compose (mapped to container port 5000).
- **Lock file**: Located at `{SCAN_DIRECTORY}/.scanlock` (inside mounted volume).

## Key Files

- `app.py` - Flask app with API endpoints for devices, capabilities, preview, scan submission
- `scan_adf.sh` - Scanner script using scanadf + ocrmypdf
- `Dockerfile` - Container build (uses python:3.11-slim-bookworm, VERSION=2.2.0)
- `docker-compose.yml` - Service config with volume mounts

## API Endpoints

- `GET /` - Main UI with preview and editing
- `GET /api/devices` - List available scanners
- `GET /api/capabilities?scanner=<id>` - Get scanner options (source/mode/resolution)
- `POST /api/preview` - Run preview scan, returns PNG image

## Environment Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `DEBUG` | False | |
| `ROOT_PATH` | / | |
| `SCAN_DIRECTORY` | /scans | Mount this volume |
| `SOURCES` | ADF Front,ADF Back,ADF Duplex | |
| `MODES` | Lineart,Halftone,Gray,Color | |
| `RESOLUTIONS` | 50-600 | |
| `VERSION` | 2.2.0 | |

## CI/CD

GitHub Actions workflow (`.github/workflows/docker.yml`) builds and pushes to ghcr.io on every push.

## Development Tips

- Preview endpoint returns PNG which can be edited client-side (rotate, crop, brightness, contrast, sharpen)
- Edited images are base64-encoded and submitted with the scan form
- Scanner capabilities are fetched via `scanimage --all-options`