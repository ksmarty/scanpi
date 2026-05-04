from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
import subprocess
import datetime as dt
import os
import tempfile
import uuid
import logging
import re
import time
import threading
import io
import json
import base64
from PIL import Image

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEBUG = os.environ.get("DEBUG", False)
ROOT_PATH = os.environ.get("ROOT_PATH", '/')
SOURCES = os.environ.get("SOURCES", "ADF Front,ADF Back,ADF Duplex").split(",")
MODES = os.environ.get("MODES", "Lineart,Halftone,Gray,Color").split(",")
RESOLUTIONS = os.environ.get("RESOLUTIONS", "50,100,150,200,250,300,350,400,450,500,550,600").split(",")
DATE_FORMAT = os.environ.get("DATE_FORMAT", "%Y-%m-%d-%H-%M-%S")

CACHE_TTL = 60  # seconds
_cache = {}

def cache_get(key):
    entry = _cache.get(key)
    if entry and time.time() - entry['ts'] < CACHE_TTL:
        logger.debug(f"Cache hit: {key}")
        return entry['value']
    return None

def cache_set(key, value):
    _cache[key] = {'value': value, 'ts': time.time()}

app = Flask(__name__)

def current_datetime():
    now = dt.datetime.now()
    return now.strftime(DATE_FORMAT)

def get_scanner_devices():
    cached = cache_get('devices')
    if cached is not None:
        return cached

    try:
        result = subprocess.run(
            ['scanadf', '--list-devices'],
            capture_output=True,
            text=True,
            timeout=30
        )
        logger.debug(f"scanadf --list-devices stdout:\n{result.stdout}")
        logger.debug(f"scanadf --list-devices stderr:\n{result.stderr}")
        
        devices = []
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if not line or line.lower().startswith('available'):
                continue
                
            match = re.search(r"[`']([^`']+)[`']", line)
            if match:
                device_id = match.group(1)
                # Remove the quoted ID and leading "device is a" boilerplate
                description = re.sub(r"^device\s+", '', line).strip()
                description = description.replace(match.group(0), '').strip()
                description = re.sub(r'^\s*is\s+a\s*', '', description).strip()
                devices.append({
                    'id': device_id,
                    'description': description
                })
            else:
                parts = line.split(None, 1)
                if len(parts) >= 1 and ':' in parts[0]:
                    device_id = parts[0].strip()
                    description = parts[1].strip() if len(parts) > 1 else ''
                    devices.append({
                        'id': device_id,
                        'description': description
                    })
        
        logger.info(f"Found scanner devices: {devices}")
        cache_set('devices', devices)
        return devices
    except Exception as e:
        logger.error(f"Error listing devices: {e}")
        return []

def render_root_path(default_date, message="", selected_scanner=""):
    return render_template('form.html', 
        default_date=default_date, 
        resolutions=RESOLUTIONS,
        sources=SOURCES,
        modes=MODES,
        message=message,
        selected_scanner=selected_scanner)

@app.route(ROOT_PATH, methods=['GET','POST'])
def root_path():
    default_date = current_datetime()
    selected_scanner = request.args.get('scanner', '')
    try:
        if request.method == 'POST':
            name = f"{request.form['date']}-{request.form['name']}"
            mode = request.form['mode']
            resolution = request.form['resolution']
            source = request.form['source']
            scanner = request.form.get('scanner', '')
            edited_image = request.form.get('edited_image', '')
            
            scan_dir = os.environ.get('SCAN_DIRECTORY', '/scans')
            
            if edited_image:
                try:
                    img_data = base64.b64decode(edited_image.split(',')[1])
                    
                    scan_path = os.path.join(scan_dir, name)
                    os.makedirs(scan_path, exist_ok=True)
                    
                    img_file = os.path.join(scan_path, f"{name}.png")
                    with open(img_file, 'wb') as f:
                        f.write(img_data)
                    
                    pdf_file = os.path.join(scan_path, f"{name}.pdf")
                    
                    # Use Pillow to convert PNG to PDF to bypass ImageMagick security policy
                    img = Image.open(img_file)
                    img.save(pdf_file, "PDF", resolution=100.0)
                    
                    subprocess.run(['ocrmypdf', '-r', '-d', '-c', '--rotate-pages-threshold', '0', pdf_file, pdf_file], check=True)
                    
                    os.chmod(pdf_file, 0o644)
                    os.chmod(scan_path, 0o755)
                    
                    return render_root_path(default_date, message='Scan saved successfully!', selected_scanner=scanner)
                except Exception as e:
                    if DEBUG:
                        raise
                    return render_root_path(default_date, f'Error saving scan: {str(e)}', selected_scanner)
            else:
                env_vars = os.environ.copy()
                env_vars["FILENAME"] = name
                env_vars["MODE"] = mode
                env_vars["RESOLUTION"] = resolution
                env_vars["SOURCE"] = source
                if scanner:
                    env_vars["SCANNER_DEVICE"] = scanner
                
                subprocess.run(['/bin/bash','scan_adf.sh'], env=env_vars)
                return render_root_path(default_date, message='Scan request submitted successfully!', selected_scanner=scanner)
        else:
            return render_root_path(default_date, selected_scanner=selected_scanner)
    except Exception as e:
        if DEBUG:
            raise
        else:
            return render_root_path(default_date, 'There was an error. Check the server.', selected_scanner)

@app.route('/api/devices')
def api_devices():
    if request.args.get('refresh') == '1':
        _cache.clear()
    return jsonify(get_scanner_devices())

@app.route('/api/capabilities', methods=['GET'])
def api_capabilities():
    scanner = request.args.get('scanner', '')
    logger.info(f"Getting capabilities for scanner: '{scanner}'")
    
    if not scanner or scanner == 'device':
        logger.warning(f"Invalid scanner value: '{scanner}'")
        return jsonify({
            'sources': SOURCES,
            'modes': MODES,
            'resolutions': RESOLUTIONS
        })
    
    return jsonify(get_capabilities(scanner))

def get_capabilities(scanner):
    cache_key = f'capabilities:{scanner}'
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        cmd = ['scanimage', '-d', scanner, '--all-options']
        
        logger.debug(f"Running command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        logger.debug(f"scanimage stdout:\n{result.stdout[:2000]}...")
        logger.debug(f"scanimage stderr:\n{result.stderr}")
        logger.debug(f"scanimage return code: {result.returncode}")
        
        capabilities = {
            'sources': [],
            'modes': [],
            'resolutions': []
        }
        
        if result.returncode != 0:
            logger.warning(f"scanimage --all-options returned code {result.returncode}, using defaults")
        
        lines = result.stdout.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Format: --source Flatbed|Slide|Negative [Flatbed]
            m = re.match(r'--source\s+([^\[]+)', line)
            if m:
                for v in m.group(1).strip().split('|'):
                    v = v.strip()
                    if v and v not in capabilities['sources']:
                        capabilities['sources'].append(v)
                continue
            
            # Format: --mode Color|Gray|Lineart [Color]
            m = re.match(r'--mode\s+([^\[]+)', line)
            if m:
                for v in m.group(1).strip().split('|'):
                    v = v.strip()
                    if v and v not in capabilities['modes']:
                        capabilities['modes'].append(v)
                continue
            
            # Format: --resolution 50|75|100|150dpi [50]
            m = re.match(r'--resolution\s+([^\[]+)', line)
            if m:
                for v in m.group(1).strip().split('|'):
                    v = re.sub(r'[^0-9]', '', v)  # strip "dpi" suffix
                    if v and v not in capabilities['resolutions']:
                        capabilities['resolutions'].append(v)
                continue
        
        logger.info(f"Parsed capabilities: {capabilities}")
        
        if not capabilities['sources']:
            capabilities['sources'] = ['ADF Front', 'ADF Back', 'ADF Duplex']
            logger.info("Using default sources")
        if not capabilities['modes']:
            capabilities['modes'] = ['Lineart', 'Halftone', 'Gray', 'Color']
            logger.info("Using default modes")
        if not capabilities['resolutions']:
            capabilities['resolutions'] = ['75', '100', '150', '200', '300', '400', '600']
            logger.info("Using default resolutions")
        
        cache_set(cache_key, capabilities)
        return capabilities
        
    except Exception as e:
        logger.error(f"Error getting capabilities for {scanner}: {e}")
        return {'sources': SOURCES, 'modes': MODES, 'resolutions': RESOLUTIONS}

def warmup_cache():
    logger.info("Cache warmup started")
    try:
        devices = get_scanner_devices()
        for device in devices:
            get_capabilities(device['id'])
        logger.info("Cache warmup complete")
    except Exception as e:
        logger.error(f"Cache warmup failed: {e}")

@app.route('/api/preview', methods=['POST'])
def api_preview():
    try:
        data = request.get_json() or {}
        scanner = data.get('scanner', '')
        mode = data.get('mode', 'Gray')
        # Use the lowest available resolution (closest to 75 DPI) for fast previews.
        # Pull from cached capabilities so we don't hit the scanner again.
        caps = get_capabilities(scanner) if scanner else {}
        available_res = [int(r) for r in caps.get('resolutions', []) if r.isdigit()]
        if available_res:
            PREVIEW_RESOLUTION = str(min(available_res, key=lambda r: abs(r - 75)))
        else:
            PREVIEW_RESOLUTION = '75'
        
        temp_dir = tempfile.mkdtemp()
        preview_file = os.path.join(temp_dir, f"preview_{uuid.uuid4()}.png")
        
        cmd = ['scanimage']
        if scanner:
            cmd.extend(['-d', scanner])
        cmd.extend([
            '--mode', mode,
            '--resolution', PREVIEW_RESOLUTION,
            '--format', 'png',
            '-o', preview_file
        ])
        
        logger.debug(f"Running preview command: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        logger.debug(f"Preview scanimage stderr:\n{result.stderr}")
        logger.debug(f"Preview scanimage return code: {result.returncode}")

        if result.returncode != 0 or not os.path.exists(preview_file):
            return jsonify({'error': 'Preview scan failed', 'details': result.stderr}), 500
        
        return send_file(preview_file, mimetype='image/png')
        
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Preview scan timed out'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# In debug mode the Werkzeug reloader forks; only warm up in the child (app) process.
if not DEBUG or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    threading.Thread(target=warmup_cache, daemon=True).start()

@app.route('/api/preview/stream')
def api_preview_stream():
    """SSE endpoint that streams progressive scan frames as JPEG while the scanner moves."""
    scanner = request.args.get('scanner', '')
    mode    = request.args.get('mode', 'Gray')

    caps = get_capabilities(scanner) if scanner else {}
    available_res = [int(r) for r in caps.get('resolutions', []) if r.isdigit()]
    preview_res = str(min(available_res, key=lambda r: abs(r - 75))) if available_res else '75'

    cmd = ['scanimage']
    if scanner:
        cmd.extend(['-d', scanner])
    cmd.extend(['--mode', mode, '--resolution', preview_res, '--format', 'pnm'])
    logger.debug(f"Running streaming preview: {' '.join(cmd)}")

    def generate():
        proc = None
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # ── Parse PNM header ──────────────────────────────────────────
            lines, buf = [], b''
            while len(lines) < 3:
                byte = proc.stdout.read(1)
                if not byte:
                    break
                if byte == b'\n':
                    line = buf.decode('ascii', errors='ignore').strip()
                    buf = b''
                    if line and not line.startswith('#'):
                        lines.append(line)
                else:
                    buf += byte

            if len(lines) < 3:
                yield f'data: {json.dumps({"type": "error", "message": "Failed to read scanner output"})}\n\n'
                return

            magic = lines[0]          # P6 = colour, P5 = grey
            width, height = map(int, lines[1].split())
            channels = 3 if magic == 'P6' else 1
            pil_mode  = 'RGB' if channels == 3 else 'L'
            bytes_per_row = width * channels

            yield f'data: {json.dumps({"type": "meta", "width": width, "height": height})}\n\n'

            # ── Stream rows ───────────────────────────────────────────────
            UPDATES = 20          # approximate number of partial-image events to send
            UPDATE_EVERY = max(1, height // UPDATES)
            all_pixels = bytearray()
            rows_read  = 0
            last_sent  = 0

            while rows_read < height:
                want  = bytes_per_row * min(UPDATE_EVERY, height - rows_read)
                chunk = proc.stdout.read(want)
                if not chunk:
                    break
                all_pixels.extend(chunk)
                rows_read = len(all_pixels) // bytes_per_row

                if rows_read >= last_sent + UPDATE_EVERY or rows_read >= height:
                    partial = bytes(all_pixels[:rows_read * bytes_per_row])
                    img = Image.frombytes(pil_mode, (width, rows_read), partial)
                    buf = io.BytesIO()
                    img.save(buf, 'JPEG', quality=85)
                    b64 = base64.b64encode(buf.getvalue()).decode()
                    progress = int(rows_read / height * 100)
                    yield f'data: {json.dumps({"type": "frame", "image": f"data:image/jpeg;base64,{b64}", "progress": progress, "scannedHeight": rows_read, "totalHeight": height})}\n\n'
                    last_sent = rows_read

            proc.wait()

            # ── Final PNG ─────────────────────────────────────────────────
            if len(all_pixels) >= height * bytes_per_row:
                full = bytes(all_pixels[:height * bytes_per_row])
                img  = Image.frombytes(pil_mode, (width, height), full)
                buf  = io.BytesIO()
                img.save(buf, 'PNG')
                b64  = base64.b64encode(buf.getvalue()).decode()
                yield f'data: {json.dumps({"type": "done", "image": f"data:image/png;base64,{b64}"})}\n\n'
            else:
                yield f'data: {json.dumps({"type": "error", "message": "Incomplete scan data received"})}\n\n'

        except GeneratorExit:
            logger.info("SSE client disconnected during preview")
        except Exception as e:
            logger.error(f"Streaming preview error: {e}")
            try:
                yield f'data: {json.dumps({"type": "error", "message": str(e)})}\n\n'
            except GeneratorExit:
                pass
        finally:
            if proc and proc.poll() is None:
                proc.kill()
                logger.info("Killed scan process after SSE disconnect/error")

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'}
    )

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)), debug=DEBUG)