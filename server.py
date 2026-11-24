import sys
try:
    import cgi
except ImportError:
    try:
        import legacy_cgi as cgi
        sys.modules['cgi'] = cgi
    except ImportError:
        pass

import os
import shutil
import subprocess
import tempfile
import zipfile
import json
import threading
import uuid
import mimetypes
from datetime import datetime
from bottle import Bottle, request, response, static_file, BaseRequest
from waitress import serve
from core.builder import build_apk

# 100MB buffer for ZIP and media uploads
WORKSTATION_ROOT = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = os.path.join(WORKSTATION_ROOT, "tmp")
os.makedirs(TMP_DIR, exist_ok=True)
tempfile.tempdir = TMP_DIR
os.environ["TMPDIR"] = TMP_DIR

def cleanup_tmp_dir(force_all=False):
    reclaimed_bytes = 0
    reclaimed_items = 0
    if not os.path.exists(TMP_DIR):
        return 0, 0
    for entry in os.listdir(TMP_DIR):
        full_path = os.path.join(TMP_DIR, entry)
        try:
            if os.path.isdir(full_path):
                for r, _, fs in os.walk(full_path):
                    for fn in fs:
                        try:
                            reclaimed_bytes += os.path.getsize(os.path.join(r, fn))
                        except OSError:
                            pass
                shutil.rmtree(full_path, ignore_errors=True)
                reclaimed_items += 1
            else:
                reclaimed_bytes += os.path.getsize(full_path)
                os.remove(full_path)
                reclaimed_items += 1
        except OSError:
            pass
    return reclaimed_items, reclaimed_bytes

BaseRequest.MEMFILE_MAX = 1024 * 1024 * 1024  # 1 GB upload ceiling
mimetypes.add_type('application/vnd.android.package-archive', '.apk')

app = Bottle()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYSTORE_DIR = os.path.join(BASE_DIR, "keystores")
BUILDS_DIR = os.path.join(BASE_DIR, "builds")
PROFILES_DIR = os.path.join(BASE_DIR, "profiles")
os.makedirs(PROFILES_DIR, exist_ok=True)

def _safe_profile_filename(pkg_id):
    cleaned = "".join(c if c.isalnum() or c in ('.', '-', '_') else '_' for c in pkg_id.strip())
    return f"{cleaned or 'default'}.json"

def load_app_profile(pkg_id):
    fp = os.path.join(PROFILES_DIR, _safe_profile_filename(pkg_id))
    if not os.path.exists(fp):
        return None
    try:
        with open(fp, "r", encoding="utf-8") as pf:
            return json.load(pf)
    except Exception:
        return None

def save_app_profile(profile_data):
    pkg_id = profile_data.get("package_id", "").strip()
    if not pkg_id:
        return
    fp = os.path.join(PROFILES_DIR, _safe_profile_filename(pkg_id))
    with open(fp, "w", encoding="utf-8") as pf:
        json.dump(profile_data, pf, indent=2)

def bump_semver_patch(vname):
    parts = [p for p in vname.strip().split(".") if p]
    if parts and parts[-1].isdigit():
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)
    return f"{vname}.1" if vname else "1.0.1"
STATIC_DIR = os.path.join(BASE_DIR, "static")

os.makedirs(KEYSTORE_DIR, exist_ok=True)
os.makedirs(BUILDS_DIR, exist_ok=True)

@app.hook('after_request')
def disable_ui_cache():
    p = request.path or ''
    if p == '/' or p.startswith('/assets/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

@app.route('/')
def serve_index():
    response.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
    return static_file('index.html', root=STATIC_DIR)

@app.route('/assets/<filepath:path>')
def serve_modular_assets(filepath):
    response.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
    return static_file(filepath, root=os.path.join(STATIC_DIR, 'assets'))

@app.route('/builds/<filename>')
def serve_build(filename):
    return static_file(
        filename, 
        root=BUILDS_DIR, 
        download=filename, 
        mimetype='application/vnd.android.package-archive'
    )

# --- KEYSTORE CRUD ---
@app.route('/api/keystores', method='GET')
def list_keystores():
    response.content_type = 'application/json'
    items = []
    if os.path.exists(KEYSTORE_DIR):
        for f in os.listdir(KEYSTORE_DIR):
            if f.endswith('.jks'):
                fp = os.path.join(KEYSTORE_DIR, f)
                items.append({
                    "name": f,
                    "size_kb": round(os.path.getsize(fp) / 1024, 1),
                    "modified": datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M")
                })
    return json.dumps({"keystores": items})

@app.route('/api/keystores', method='POST')
def create_keystore():
    response.content_type = 'application/json'
    alias = request.forms.get('alias', 'key0').strip()
    password = request.forms.get('password', 'password123').strip()
    dname = request.forms.get('dname', 'CN=Master, OU=Dev, O=Workstation, C=PH').strip()
    filename = f"{alias}.jks"
    target_path = os.path.join(KEYSTORE_DIR, filename)

    if os.path.exists(target_path):
        response.status = 400
        return json.dumps({"error": f"Keystore '{filename}' already exists."})

    cmd = [
        "keytool", "-genkey", "-v",
        "-keystore", target_path,
        "-alias", alias,
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "10000",
        "-storepass", password,
        "-keypass", password,
        "-dname", dname
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        response.status = 500
        return json.dumps({"error": res.stderr.strip()})
    return json.dumps({"success": True, "keystore": filename})

@app.route('/api/keystores/<filename>', method='DELETE')
def delete_keystore(filename):
    response.content_type = 'application/json'
    target_path = os.path.join(KEYSTORE_DIR, filename)
    if filename == "master.jks":
        response.status = 400
        return json.dumps({"error": "Cannot delete default master.jks keystore."})
    if not os.path.exists(target_path):
        response.status = 404
        return json.dumps({"error": "Keystore file not found."})
    try:
        os.remove(target_path)
        return json.dumps({"success": True, "deleted": filename})
    except Exception as e:
        response.status = 500
        return json.dumps({"error": str(e)})

@app.route('/api/keystores/<filename>/details', method='GET')
def keystore_details(filename):
    response.content_type = 'application/json'
    target_path = os.path.join(KEYSTORE_DIR, filename)
    password = request.query.get('password', 'password123')
    if not os.path.exists(target_path):
        response.status = 404
        return json.dumps({"error": "Keystore not found."})

    cmd = ["keytool", "-list", "-v", "-keystore", target_path, "-storepass", password]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        response.status = 400
        return json.dumps({"error": res.stderr.strip()})
    return json.dumps({"success": True, "details": res.stdout})

# --- BUILDS CRUD ---
@app.route('/api/builds', method='GET')
def list_builds():
    response.content_type = 'application/json'
    items = []
    if os.path.exists(BUILDS_DIR):
        for f in os.listdir(BUILDS_DIR):
            if f.endswith('.apk'):
                fp = os.path.join(BUILDS_DIR, f)
                size_mb = round(os.path.getsize(fp) / (1024 * 1024), 2)
                items.append({
                    "name": f,
                    "size_mb": size_mb,
                    "date": datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M")
                })
    return json.dumps({"builds": items})

@app.route('/api/builds/<filename>', method='DELETE')
def delete_build(filename):
    response.content_type = 'application/json'
    target_path = os.path.join(BUILDS_DIR, filename)
    if not os.path.exists(target_path):
        response.status = 404
        return json.dumps({"error": "Build artifact not found."})
    try:
        os.remove(target_path)
        return json.dumps({"success": True, "deleted": filename})
    except Exception as e:
        response.status = 500
        return json.dumps({"error": str(e)})

# --- PLATFORM SDK (android.jar) MANAGER ---
@app.route('/api/sdk', method='GET')
def get_sdk_info():
    response.content_type = 'application/json'
    jar_path = os.path.join(BASE_DIR, "libs", "android.jar")
    if not os.path.exists(jar_path):
        return json.dumps({"exists": False, "size_mb": 0, "api_level": "Missing"})
    size_mb = round(os.path.getsize(jar_path) / (1024 * 1024), 2)
    modified = datetime.fromtimestamp(os.path.getmtime(jar_path)).strftime("%Y-%m-%d %H:%M")
    api_level = "Unknown"
    try:
        with zipfile.ZipFile(jar_path, 'r') as zf:
            if "android/os/Build$VERSION_CODES.class" in zf.namelist():
                raw = zf.read("android/os/Build$VERSION_CODES.class")
                # Scan constant pool ints for highest SDK code between 30 and 120
                import struct
                found_codes = []
                for i in range(len(raw) - 5):
                    if raw[i] == 3:  # CONSTANT_Integer
                        val = struct.unpack(">i", raw[i+1:i+5])[0]
                        if 30 <= val <= 120:
                            found_codes.append(val)
                if found_codes:
                    api_level = f"API {max(found_codes)}"
    except Exception:
        pass
    return json.dumps({
        "exists": True,
        "path": "libs/android.jar",
        "size_mb": size_mb,
        "modified": modified,
        "api_level": api_level
    })

@app.route('/api/sdk/upload', method='POST')
def upload_sdk_jar():
    response.content_type = 'application/json'
    jar_upload = request.files.get('sdk_jar')
    if not jar_upload:
        response.status = 400
        return json.dumps({"error": "No android.jar file uploaded."})
    os.makedirs(os.path.join(BASE_DIR, "libs"), exist_ok=True)
    target_jar = os.path.join(BASE_DIR, "libs", "android.jar")
    backup_jar = os.path.join(BASE_DIR, "libs", "android.jar.bak")
    tmp_jar = os.path.join(BASE_DIR, "libs", "android.jar.tmp")
    try:
        jar_upload.save(tmp_jar, overwrite=True)
        with zipfile.ZipFile(tmp_jar, 'r') as zf:
            if "classes.dex" not in zf.namelist() and "android/app/Activity.class" not in zf.namelist():
                os.remove(tmp_jar)
                response.status = 400
                return json.dumps({"error": "Invalid android.jar: missing Android framework classes."})
        if os.path.exists(target_jar):
            shutil.copy2(target_jar, backup_jar)
        os.replace(tmp_jar, target_jar)
        return json.dumps({"success": True, "message": "Updated libs/android.jar successfully."})
    except Exception as e:
        if os.path.exists(tmp_jar):
            os.remove(tmp_jar)
        response.status = 500
        return json.dumps({"error": str(e)})

# --- APP PROFILES CRUD ---
@app.route('/api/profiles', method='GET')
def list_profiles():
    response.content_type = 'application/json'
    profiles = []
    if os.path.exists(PROFILES_DIR):
        for fn in os.listdir(PROFILES_DIR):
            if fn.endswith('.json'):
                fp = os.path.join(PROFILES_DIR, fn)
                try:
                    with open(fp, 'r', encoding='utf-8') as pf:
                        data = json.load(pf)
                        profiles.append(data)
                except Exception:
                    pass
    profiles.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
    return json.dumps({"profiles": profiles})

@app.route('/api/profiles/<package_id>', method='GET')
def get_profile(package_id):
    response.content_type = 'application/json'
    data = load_app_profile(package_id)
    if not data:
        response.status = 404
        return json.dumps({"error": "Profile not found."})
    return json.dumps({"profile": data})

@app.route('/api/profiles/<package_id>', method='DELETE')
def delete_profile(package_id):
    response.content_type = 'application/json'
    fp = os.path.join(PROFILES_DIR, _safe_profile_filename(package_id))
    if not os.path.exists(fp):
        response.status = 404
        return json.dumps({"error": "Profile not found."})
    try:
        os.remove(fp)
        return json.dumps({"success": True, "deleted": package_id})
    except Exception as e:
        response.status = 500
        return json.dumps({"error": str(e)})

# --- BUILD PIPELINE (ASYNC LIVE STREAMING) ---
BUILD_JOBS = {}
BUILD_LOCK = threading.Lock()

def update_job_log(job_id, msg):
    print(msg, flush=True)
    with BUILD_LOCK:
        job = BUILD_JOBS.get(job_id)
        if not job:
            return
        job["logs"].append(msg)
        lower = msg.lower()
        if "unpacking" in lower:
            job["progress"] = 25
            job["stage"] = "Unpacking project archive..."
        elif "detected 'index.html'" in lower:
            job["progress"] = 35
            job["stage"] = "Configuring WebView & permissions..."
        elif "aapt" in lower:
            job["progress"] = 50
            job["stage"] = "Packaging Android resources (AAPT)..."
        elif "javac" in lower:
            job["progress"] = 65
            job["stage"] = "Compiling Java bridge..."
        elif "d8" in lower or "dx" in lower:
            job["progress"] = 80
            job["stage"] = "Translating bytecode to DEX..."
        elif "zipalign" in lower or "apksigner" in lower:
            job["progress"] = 92
            job["stage"] = "Aligning & signing release APK..."

@app.route('/api/build', method='POST')
def trigger_build():
    response.content_type = 'application/json'
    job_id = uuid.uuid4().hex[:12]
    timestamp = datetime.now().strftime("%H:%M:%S")

    with BUILD_LOCK:
        BUILD_JOBS[job_id] = {
            "status": "running",
            "progress": 15,
            "stage": "Receiving uploaded files...",
            "logs": [f"[{timestamp}] Build job {job_id} accepted by server."],
            "filename": None,
            "download_url": None,
            "error": None
        }

    raw_name = request.forms.get('app_name', 'My Custom App').strip()
    app_label = raw_name if raw_name else 'My Custom App'
    file_safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in app_label)
    raw_pkg = request.forms.get('package_id', '').strip()
    auto_pkg_note = None
    if not raw_pkg or (raw_pkg == 'com.resteus.store' and app_label.lower() not in ('my custom app', 'resteus store', 'store')):
        slug = "".join(c.lower() for c in app_label if c.isalnum()) or "app"
        package_id = f"com.resteus.{slug}"
        auto_pkg_note = f"Auto-assigned unique Package ID '{package_id}' from App Name to prevent app collisions."
    else:
        package_id = raw_pkg

    version_code = request.forms.get('version_code', '1').strip() or '1'
    version_name = request.forms.get('version_name', '1.0.0').strip() or '1.0.0'
    min_sdk = "".join(c for c in request.forms.get('min_sdk', '21').strip() if c.isdigit()) or '21'
    target_sdk = "".join(c for c in request.forms.get('target_sdk', '36').strip() if c.isdigit()) or '36'

    existing_profile = load_app_profile(package_id)
    auto_ver_note = None
    if existing_profile:
        try:
            prev_vc = int(existing_profile.get("last_version_code", 0))
            curr_vc = int(version_code)
            if curr_vc <= prev_vc:
                new_vc = prev_vc + 1
                version_code = str(new_vc)
                if version_name == existing_profile.get("last_version_name", ""):
                    version_name = existing_profile.get("next_version_name") or bump_semver_patch(version_name)
                auto_ver_note = f"Auto-bumped version for '{package_id}' to VC {version_code} (v{version_name}) for seamless Android update."
        except ValueError:
            pass

    orientation = int(request.forms.get('orientation', '0'))
    force_offline = request.forms.get('force_offline') == 'true'
    allow_zoom = request.forms.get('allow_zoom') == 'true'
    allow_camera = request.forms.get('allow_camera') == 'true'
    allow_storage = request.forms.get('allow_storage') == 'true'
    allow_copy_paste = request.forms.get('allow_copy_paste') == 'true'
    enable_location = request.forms.get('enable_location') == 'true'
    enable_notifications = request.forms.get('enable_notifications') == 'true'
    block_screenshots = request.forms.get('block_screenshots') == 'true'
    pull_to_refresh = request.forms.get('pull_to_refresh', 'true') == 'true'
    respect_system_bars = request.forms.get('respect_system_bars', 'true') == 'true'

    ks_file = request.forms.get('keystore', 'master.jks')
    ks_pass = request.forms.get('keystore_pass', 'password123')
    k_alias = request.forms.get('key_alias', 'master')
    k_pass = request.forms.get('key_pass', 'password123')

    website_url = request.forms.get('website_url', '').strip()
    if website_url and not website_url.startswith(('http://', 'https://')):
        website_url = 'https://' + website_url
    local_path = request.forms.get('local_path', '').strip()
    upload = request.files.get('project_zip')
    icon_upload = request.files.get('custom_icon')

    temp_extract = tempfile.mkdtemp(prefix="web_src_")
    zip_target = None
    upload_name = None
    icon_path = None
    icon_name = None

    try:
        if upload:
            upload_name = upload.filename
            zip_target = os.path.join(temp_extract, "project.zip")
            upload.save(zip_target, overwrite=True)

        if icon_upload:
            icon_name = icon_upload.filename
            ext = os.path.splitext(icon_name)[1].lower()
            if ext in ('.png', '.jpg', '.jpeg', '.webp'):
                icon_path = os.path.join(temp_extract, f"custom_icon{ext}")
                icon_upload.save(icon_path, overwrite=True)
            else:
                update_job_log(job_id, f"[{datetime.now().strftime('%H:%M:%S')}] Warning: Unsupported icon extension '{ext}'. Skipping.")
    except Exception as e:
        shutil.rmtree(temp_extract, ignore_errors=True)
        err_msg = f"Upload staging failed: {str(e)}"
        with BUILD_LOCK:
            BUILD_JOBS[job_id]["status"] = "error"
            BUILD_JOBS[job_id]["error"] = err_msg
            BUILD_JOBS[job_id]["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: {err_msg}")
        return json.dumps({"success": False, "error": err_msg, "logs": "\n".join(BUILD_JOBS[job_id]["logs"])})

    def worker():
        log = lambda m: update_job_log(job_id, m)
        try:
            if auto_pkg_note:
                log(f"[{datetime.now().strftime('%H:%M:%S')}] {auto_pkg_note}")
            if auto_ver_note:
                log(f"[{datetime.now().strftime('%H:%M:%S')}] {auto_ver_note}")
            source_dir = ""
            if website_url:
                source_dir = temp_extract
                log(f"[{datetime.now().strftime('%H:%M:%S')}] Website URL mode: {website_url}")
            elif zip_target and os.path.exists(zip_target):
                log(f"[{datetime.now().strftime('%H:%M:%S')}] Receiving project archive: {upload_name}")
                log(f"[{datetime.now().strftime('%H:%M:%S')}] Unpacking archive...")
                with zipfile.ZipFile(zip_target, 'r') as zf:
                    zf.extractall(temp_extract)
                os.remove(zip_target)

                found_dir = None
                for root, _, files in os.walk(temp_extract):
                    if "index.html" in files:
                        found_dir = root
                        break

                if found_dir:
                    source_dir = found_dir
                    rel = os.path.relpath(source_dir, temp_extract)
                    log(f"[{datetime.now().strftime('%H:%M:%S')}] Detected 'index.html' entrypoint at: {rel if rel != '.' else 'archive root'}")
                else:
                    raise RuntimeError("No 'index.html' found in uploaded ZIP.")
            elif local_path and os.path.exists(os.path.expanduser(local_path)):
                source_dir = os.path.expanduser(local_path)
                log(f"[{datetime.now().strftime('%H:%M:%S')}] Using local path: {source_dir}")
                if not os.path.exists(os.path.join(source_dir, "index.html")):
                    raise RuntimeError(f"No 'index.html' found in '{local_path}'.")
            else:
                raise RuntimeError("Please provide a valid Website URL, project ZIP, or local path.")

            if icon_path:
                log(f"[{datetime.now().strftime('%H:%M:%S')}] Custom icon staged: {icon_name}")

            build_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_vname = "".join(c for c in version_name if c.isalnum() or c in ('.', '-', '_')).lstrip('v') or "1.0.0"
            safe_vcode = "".join(c for c in version_code if c.isalnum() or c in ('-', '_')) or "1"
            apk_filename = f"{file_safe_name}_VC{safe_vcode}_v{safe_vname}_{build_stamp}.apk"
            out_apk = os.path.join(BUILDS_DIR, apk_filename)
            keystore_path = os.path.join(KEYSTORE_DIR, ks_file)

            build_apk(
                source_web_dir=source_dir,
                package_id=package_id,
                version_code=version_code,
                version_name=version_name,
                min_sdk=min_sdk,
                target_sdk=target_sdk,
                website_url=website_url,
                output_apk_path=out_apk,
                app_label=app_label,
                app_orientation=orientation,
                custom_icon_path=icon_path,
                force_offline=force_offline,
                allow_zoom=allow_zoom,
                allow_camera=allow_camera,
                allow_storage=allow_storage,
                allow_copy_paste=allow_copy_paste,
                enable_location=enable_location,
                enable_notifications=enable_notifications,
                block_screenshots=block_screenshots,
                pull_to_refresh=pull_to_refresh,
                respect_system_bars=respect_system_bars,
                keystore_path=keystore_path,
                keystore_pass=ks_pass,
                key_alias=k_alias,
                key_pass=k_pass,
                log_fn=log
            )

            try:
                vc_int = int(version_code)
                next_vc = str(vc_int + 1)
            except ValueError:
                next_vc = "2"
            next_vn = bump_semver_patch(version_name)

            save_app_profile({
                "app_name": app_label,
                "package_id": package_id,
                "last_version_code": version_code,
                "last_version_name": version_name,
                "next_version_code": next_vc,
                "next_version_name": next_vn,
                "min_sdk": min_sdk,
                "target_sdk": target_sdk,
                "website_url": website_url,
                "orientation": orientation,
                "force_offline": force_offline,
                "allow_zoom": allow_zoom,
                "allow_camera": allow_camera,
                "allow_storage": allow_storage,
                "allow_copy_paste": allow_copy_paste,
                "enable_location": enable_location,
                "enable_notifications": enable_notifications,
                "block_screenshots": block_screenshots,
                "pull_to_refresh": pull_to_refresh,
                "respect_system_bars": respect_system_bars,
                "keystore": ks_file,
                "key_alias": k_alias,
                "local_path": local_path,
                "last_apk": apk_filename,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            log(f"[{datetime.now().strftime('%H:%M:%S')}] Saved app profile '{package_id}' (next suggested: VC {next_vc} / v{next_vn}).")

            with BUILD_LOCK:
                BUILD_JOBS[job_id]["status"] = "done"
                BUILD_JOBS[job_id]["progress"] = 100
                BUILD_JOBS[job_id]["stage"] = "Build Finished Successfully!"
                BUILD_JOBS[job_id]["filename"] = apk_filename
                BUILD_JOBS[job_id]["download_url"] = f"/builds/{apk_filename}"
        except Exception as e:
            log(f"[{datetime.now().strftime('%H:%M:%S')}] CRITICAL FAILURE: {str(e)}")
            with BUILD_LOCK:
                BUILD_JOBS[job_id]["status"] = "error"
                BUILD_JOBS[job_id]["error"] = str(e)
        finally:
            shutil.rmtree(temp_extract, ignore_errors=True)
            with BUILD_LOCK:
                active = sum(1 for j in BUILD_JOBS.values() if j.get("status") == "running")
            if active == 0:
                cleanup_tmp_dir(force_all=True)

    threading.Thread(target=worker, daemon=True).start()
    with BUILD_LOCK:
        initial_logs = "\n".join(BUILD_JOBS[job_id]["logs"])
    return json.dumps({"success": True, "job_id": job_id, "logs": initial_logs})

@app.route('/api/build/status/<job_id>', method='GET')
def build_status(job_id):
    response.content_type = 'application/json'
    with BUILD_LOCK:
        job = BUILD_JOBS.get(job_id)
        if not job:
            response.status = 404
            return json.dumps({"error": "Build job not found."})
        return json.dumps({
            "status": job["status"],
            "progress": job["progress"],
            "stage": job["stage"],
            "logs": "\n".join(job["logs"]),
            "filename": job["filename"],
            "download_url": job["download_url"],
            "error": job["error"]
        })

if __name__ == '__main__':
    items_cleaned, bytes_cleaned = cleanup_tmp_dir(force_all=True)
    if items_cleaned > 0:
        print(f"[*] Swept {items_cleaned} orphaned tmp item(s) ({bytes_cleaned / (1024*1024):.2f} MB freed)")
    print("[*] APK Workstation running on Waitress at http://127.0.0.1:8080")
    serve(
        app,
        host='127.0.0.1',
        port=8080,
        max_request_body_size=1073741824,  # 1 GB
        inbuf_overflow=10485760,          # 10 MB memory buffer before disk spool
        channel_timeout=600,              # 10-minute timeout for large assets
        threads=4
    )
