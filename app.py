from flask import Flask, render_template, request, jsonify, send_file
import subprocess
import datetime as dt
import os
import tempfile
import uuid

DEBUG = os.environ.get("DEBUG", False)
ROOT_PATH = os.environ.get("ROOT_PATH", '/')
SOURCES = os.environ.get("SOURCES", "ADF Front,ADF Back,ADF Duplex").split(",")
MODES = os.environ.get("MODES", "Lineart,Halftone,Gray,Color").split(",")
RESOLUTIONS = os.environ.get("RESOLUTIONS", "50,100,150,200,250,300,350,400,450,500,550,600").split(",")
DATE_FORMAT = os.environ.get("DATE_FORMAT", "%Y-%m-%d-%H-%M-%S")

app = Flask(__name__)

def current_datetime():
    now = dt.datetime.now()
    return now.strftime(DATE_FORMAT)

def get_scanner_devices():
    try:
        result = subprocess.run(
            ['scanadf', '--list-devices'],
            capture_output=True,
            text=True,
            timeout=30
        )
        devices = []
        for line in result.stdout.strip().split('\n'):
            if line.strip() and not line.startswith('Available'):
                parts = line.split(None, 1)
                if len(parts) >= 1:
                    device_id = parts[0].strip()
                    description = parts[1].strip() if len(parts) > 1 else ''
                    devices.append({
                        'id': device_id,
                        'description': description
                    })
        return devices
    except Exception as e:
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
            resolution = f"{int(request.form['resolution'])}dpi"
            source = request.form['source']
            scanner = request.form.get('scanner', '')
            
            env_vars = os.environ.copy()
            env_vars["FILENAME"] = name
            env_vars["MODE"] = mode
            env_vars["RESOLUTION"] = resolution
            env_vars["SOURCE"] = source
            if scanner:
                env_vars["SCANNER_DEVICE"] = scanner
            
            subprocess.Popen(['/bin/bash','scan_adf.sh'], env=env_vars)
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
    return jsonify(get_scanner_devices())

@app.route('/api/preview', methods=['POST'])
def api_preview():
    try:
        data = request.get_json() or {}
        scanner = data.get('scanner', '')
        mode = data.get('mode', 'Gray')
        resolution = data.get('resolution', '75')
        
        temp_dir = tempfile.mkdtemp()
        preview_file = os.path.join(temp_dir, f"preview_{uuid.uuid4()}.png")
        
        cmd = ['scanimage']
        if scanner:
            cmd.extend(['-d', scanner])
        cmd.extend([
            '--mode', mode,
            '--resolution', resolution,
            '--format', 'png',
            '-o', preview_file
        ])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0 or not os.path.exists(preview_file):
            return jsonify({'error': 'Preview scan failed', 'details': result.stderr}), 500
        
        return send_file(preview_file, mimetype='image/png')
        
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Preview scan timed out'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5123)), debug=DEBUG)