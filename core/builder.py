import os, re, sys, shutil, subprocess, time, zipfile
from datetime import datetime

WORKSTATION_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BASE_TEMPLATE = os.path.join(WORKSTATION_ROOT, "custom-base")
LIBS_JAR = os.path.join(WORKSTATION_ROOT, "libs", "android.jar")
BUILDS_DIR = os.path.join(WORKSTATION_ROOT, "builds")
SHARED_DOWNLOADS = os.path.expanduser("~/storage/shared/Download")

def run_cmd(cmd, cwd=None, log_fn=None):
    if log_fn:
        log_fn(f"[CMD] {cmd}")
    proc = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        if log_fn:
            log_fn(f"[ERROR] {err}")
        raise RuntimeError(f"Command failed: {cmd}\nError: {err}")
    return proc.stdout

def build_apk(
    source_web_dir,
    output_apk_path,
    app_label="My Custom App",
    package_id="com.resteus.store",
    version_code="1",
    version_name="1.0.0",
    min_sdk="21",
    target_sdk="36",
    website_url="",
    app_orientation=0,
    custom_icon_path=None,
    force_offline=False,
    allow_zoom=False,
    allow_camera=False,
    allow_storage=False,
    allow_copy_paste=True,
    enable_location=False,
    enable_notifications=False,
    block_screenshots=False,
    pull_to_refresh=True,
    respect_system_bars=True,
    keystore_path=None,
    keystore_pass="password123",
    key_alias="master",
    key_pass="password123",
    log_fn=None,
    **kwargs
):
    def emit(msg):
        if log_fn:
            log_fn(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    os.makedirs(BUILDS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    build_sandbox = os.path.join(os.environ.get("TMPDIR", "/data/data/com.termux/files/usr/tmp"), f"web_build_{timestamp}")
    os.makedirs(build_sandbox, exist_ok=True)

    try:
        emit(f"Initializing build environment: {package_id} (v{version_name})")
        res_dir = os.path.join(build_sandbox, "res")
        assets_dir = os.path.join(build_sandbox, "assets", "web")
        src_dir = os.path.join(build_sandbox, "src")
        bin_dir = os.path.join(build_sandbox, "bin")
        classes_dir = os.path.join(bin_dir, "classes")

        shutil.copytree(os.path.join(BASE_TEMPLATE, "res"), res_dir)
        os.makedirs(assets_dir, exist_ok=True)
        os.makedirs(classes_dir, exist_ok=True)

        clean_url = (website_url or "").strip()
        if clean_url and not clean_url.startswith(("http://", "https://")):
            clean_url = "https://" + clean_url
        is_url_mode = bool(clean_url)
        if is_url_mode and force_offline:
            emit("Website URL mode active: automatically disabling Force Offline so live site loads.")
            force_offline = False

        safe_min_sdk = "".join(c for c in str(min_sdk) if c.isdigit()) or "21"
        safe_target_sdk = "".join(c for c in str(target_sdk) if c.isdigit()) or "36"
        emit(f"Target Android API Matrix: minSdkVersion={safe_min_sdk}, targetSdkVersion={safe_target_sdk}")

        # 1. Ingest Web Assets (Skipped in Live Website URL mode)
        if is_url_mode:
            emit(f"Live Website Wrapper Mode: binding ROOT_URL -> {clean_url}")
        else:
            emit(f"Ingesting web assets from: {source_web_dir}")
            for item in os.listdir(source_web_dir):
                s = os.path.join(source_web_dir, item)
                d = os.path.join(assets_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d)
                else:
                    shutil.copy2(s, d)

        # 2. Custom App Icon
        icon_attr = ""
        if custom_icon_path and os.path.exists(custom_icon_path):
            emit("Staging custom application launcher icon...")
            drawable_dir = os.path.join(res_dir, "drawable-nodpi")
            os.makedirs(drawable_dir, exist_ok=True)
            ext = os.path.splitext(custom_icon_path)[1].lower()
            shutil.copy2(custom_icon_path, os.path.join(drawable_dir, f"ic_launcher{ext}"))
            icon_attr = 'android:icon="@drawable/ic_launcher"'

        # 3. Orientation Attribute
        orientation_map = {1: 'android:screenOrientation="portrait"', 2: 'android:screenOrientation="sensorLandscape"'}
        orientation_attr = orientation_map.get(int(app_orientation), "")

        # 4. Generate strings.xml
        emit(f"Writing strings.xml: app_name = '{app_label}'")
        strings_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">{app_label}</string>
</resources>
"""
        with open(os.path.join(res_dir, "values", "strings.xml"), "w") as f:
            f.write(strings_xml)

        # 5. Manifest Permissions & Runtime Requests
        manifest_perms = []
        manifest_features = []
        runtime_perms_init = []

        if not force_offline:
            emit("Network access enabled: injecting INTERNET and ACCESS_NETWORK_STATE.")
            manifest_perms.append('    <uses-permission android:name="android.permission.INTERNET" />')
            manifest_perms.append('    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />')
        else:
            emit("Force Offline ACTIVE: isolating container from all network interfaces.")

        if allow_camera:
            emit("Hardware Flag: Camera enabled.")
            manifest_perms.append('    <uses-permission android:name="android.permission.CAMERA" />')
            manifest_features.append('    <uses-feature android:name="android.hardware.camera" android:required="false" />')
            runtime_perms_init.append('perms.add("android.permission.CAMERA");')

        if allow_storage:
            emit("Storage Flag: Read/Write storage enabled.")
            manifest_perms.append('    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" android:maxSdkVersion="32" />')
            manifest_perms.append('    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" android:maxSdkVersion="29" />')
            manifest_perms.append('    <uses-permission android:name="android.permission.READ_MEDIA_IMAGES" />')
            manifest_perms.append('    <uses-permission android:name="android.permission.READ_MEDIA_VIDEO" />')
            manifest_perms.append('    <uses-permission android:name="android.permission.READ_MEDIA_AUDIO" />')
            runtime_perms_init.append('''if (Build.VERSION.SDK_INT >= 33) {
            perms.add("android.permission.READ_MEDIA_IMAGES");
            perms.add("android.permission.READ_MEDIA_VIDEO");
            perms.add("android.permission.READ_MEDIA_AUDIO");
        } else {
            perms.add("android.permission.READ_EXTERNAL_STORAGE");
            perms.add("android.permission.WRITE_EXTERNAL_STORAGE");
        }''')

        if enable_location:
            emit("Hardware Flag: Geolocation enabled.")
            manifest_perms.append('    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />')
            manifest_perms.append('    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />')
            runtime_perms_init.append('perms.add("android.permission.ACCESS_FINE_LOCATION");')
            runtime_perms_init.append('perms.add("android.permission.ACCESS_COARSE_LOCATION");')

        if enable_notifications:
            emit("System Flag: Post notifications enabled.")
            manifest_perms.append('    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />')
            runtime_perms_init.append('if (Build.VERSION.SDK_INT >= 33) perms.add("android.permission.POST_NOTIFICATIONS");')

        perms_block = "\n".join(manifest_perms)
        features_block = "\n".join(manifest_features)

        # 6. AndroidManifest.xml (Applied Theme.DeviceDefault.NoActionBar)
        emit(f"Generating AndroidManifest.xml for package '{package_id}' (Theme.DeviceDefault.NoActionBar)")
        manifest_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{package_id}"
    android:versionCode="{version_code}"
    android:versionName="{version_name}">

    <uses-sdk android:minSdkVersion="{safe_min_sdk}" android:targetSdkVersion="{safe_target_sdk}" />
{perms_block}
{features_block}

    <application
        android:label="@string/app_name"
        android:theme="@android:style/Theme.DeviceDefault.NoActionBar"
        {icon_attr}
        android:hardwareAccelerated="true"
        android:usesCleartextTraffic="true"
        android:allowBackup="false">
        <activity
            android:name="{package_id}.MainActivity"
            android:exported="true"
            android:theme="@android:style/Theme.DeviceDefault.NoActionBar"
            {orientation_attr}
            android:windowSoftInputMode="adjustResize"
            android:configChanges="orientation|screenSize|screenLayout|smallestScreenSize|keyboardHidden">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
"""
        manifest_path = os.path.join(build_sandbox, "AndroidManifest.xml")
        with open(manifest_path, "w") as f:
            f.write(manifest_xml)

        # 7. Configure Native Security Flags
        secure_window_code = ""
        if block_screenshots:
            emit("Security Flag: BLOCK_SCREENSHOTS active (enforcing FLAG_SECURE).")
            secure_window_code = "getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE);"

        zoom_code = "settings.setSupportZoom(false); settings.setBuiltInZoomControls(false);"
        if allow_zoom:
            emit("Feature Flag: Built-in zoom gestures enabled.")
            zoom_code = "settings.setSupportZoom(true); settings.setBuiltInZoomControls(true); settings.setDisplayZoomControls(false);"

        copy_paste_code = ""
        if not allow_copy_paste:
            emit("Security Flag: Text selection and long-press disabled.")
            copy_paste_code = """
        webView.setOnLongClickListener(new View.OnLongClickListener() {
            @Override
            public boolean onLongClick(View v) {
                return true;
            }
        });
        webView.setLongClickable(false);
        webView.setHapticFeedbackEnabled(false);
"""

        runtime_perms_exec = ""
        if runtime_perms_init:
            runtime_perms_exec = f"""
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {{
            List<String> perms = new ArrayList<String>();
            {" ".join(runtime_perms_init)}
            List<String> toRequest = new ArrayList<String>();
            for (String p : perms) {{
                if (p != null && checkSelfPermission(p) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
                    toRequest.add(p);
                }}
            }}
            if (!toRequest.isEmpty()) {{
                requestPermissions(toRequest.toArray(new String[0]), 101);
            }}
        }}
"""

        offline_interceptor = ""
        if force_offline:
            offline_interceptor = """
                if (url != null && (url.startsWith("http://") || url.startsWith("https://"))) {
                    return true;
                }
"""

        # 8. Encrypt Web Assets (AES-256-CBC) & Bind Key to Signing Certificate
        ks = keystore_path if keystore_path and os.path.exists(keystore_path) else os.path.join(WORKSTATION_ROOT, "keystores", "master.jks")
        emit(f"Deriving certificate fingerprint lock from keystore alias '{key_alias}'...")
        kt_out = run_cmd(f'keytool -list -v -keystore "{ks}" -alias "{key_alias}" -storepass "{keystore_pass}"')
        sha_match = re.search(r"SHA-?256:\s*([0-9A-Fa-f:]{95})", kt_out)
        if not sha_match:
            raise RuntimeError("Could not extract SHA-256 certificate fingerprint from keystore. Verify keystore password and alias.")
        cert_sha256 = bytes.fromhex(sha_match.group(1).replace(":", ""))

        aes_key = os.urandom(32)
        key_mask = os.urandom(32)
        sealed_key = bytes([aes_key[i] ^ cert_sha256[i] ^ key_mask[i] for i in range(32)])

        aes_key_hex = aes_key.hex()
        enc_count = 0
        if not is_url_mode:
            emit("Encrypting bundled web assets with per-build AES-256-CBC stream cipher...")
        for root_dir, _, files in os.walk(assets_dir):
            for fname in files:
                fpath = os.path.join(root_dir, fname)
                iv = os.urandom(16)
                with open(fpath, "rb") as raw_f:
                    plain_bytes = raw_f.read()
                proc_enc = subprocess.run(
                    ["openssl", "enc", "-aes-256-cbc", "-K", aes_key_hex, "-iv", iv.hex()],
                    input=plain_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                if proc_enc.returncode != 0:
                    raise RuntimeError(f"Asset encryption failed on {fname}: {proc_enc.stderr.decode(errors='ignore')}")
                with open(fpath, "wb") as enc_f:
                    enc_f.write(iv + proc_enc.stdout)
                enc_count += 1
        if not is_url_mode:
            emit(f"Encrypted {enc_count} web asset files in-place (zero plaintext files on disk).")

        def format_obfuscated_int_array(b_arr):
            parts = []
            for idx, b in enumerate(b_arr):
                salt = ((idx * 73 + 41) & 0xFF)
                parts.append(f"(({b ^ salt} ^ {salt}) & 0xFF)")
            return ", ".join(parts)

        sealed_java_arr = format_obfuscated_int_array(sealed_key)
        mask_java_arr = format_obfuscated_int_array(key_mask)

        pkg_dir = os.path.join(src_dir, *package_id.split("."))
        os.makedirs(pkg_dir, exist_ok=True)

        java_template = r"""package __PACKAGE_ID__;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.graphics.Bitmap;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.graphics.Insets;
import android.view.WindowInsets;
import android.widget.FrameLayout;
import android.os.Environment;
import android.print.PrintAttributes;
import android.print.PrintDocumentAdapter;
import android.print.PrintManager;
import android.provider.MediaStore;
import android.util.Base64;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.GeolocationPermissions;
import android.webkit.JavascriptInterface;
import android.webkit.JsResult;
import android.webkit.PermissionRequest;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import javax.crypto.Cipher;
import javax.crypto.CipherInputStream;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class MainActivity extends Activity {
    private WebView webView;
    private ValueCallback<Uri[]> uploadMessage;
    private final static int FILE_CHOOSER_RESULT_CODE = 1001;
    private static final String VIRTUAL_HOST = "appassets.androidplatform.net";
    private static final String VIRTUAL_ORIGIN = "https://" + VIRTUAL_HOST;
    private static final String ROOT_URL = "__ROOT_URL__";
    private static final boolean FORCE_OFFLINE = __FORCE_OFFLINE__;
    private static final boolean PULL_TO_REFRESH = __PULL_TO_REFRESH__;
    private static final boolean RESPECT_SYSTEM_BARS = __RESPECT_SYSTEM_BARS__;
    private static final String APP_TITLE = "__APP_TITLE__";

    private static final int[] SEALED_KEY = new int[]{ __SEALED_KEY_ARR__ };
    private static final int[] MASK_KEY = new int[]{ __MASK_KEY_ARR__ };
    private SecretKeySpec aesKeySpec;

    private static final String BRIDGE_JS =
        "(function() {" +
        "  if (window.__wsBridgeInstalled) return;" +
        "  window.__wsBridgeInstalled = true;" +
        "  window.__wsBlobStore = new Map();" +
        "  const origCreate = URL.createObjectURL.bind(URL);" +
        "  URL.createObjectURL = function(obj) {" +
        "    const u = origCreate(obj);" +
        "    if (obj instanceof Blob) window.__wsBlobStore.set(u, obj);" +
        "    return u;" +
        "  };" +
        "  const origRevoke = URL.revokeObjectURL.bind(URL);" +
        "  URL.revokeObjectURL = function(u) {" +
        "    setTimeout(function() { window.__wsBlobStore.delete(u); }, 20000);" +
        "    return origRevoke(u);" +
        "  };" +
        "  window.__wsExportBlob = async function(blob, filename) {" +
        "    if (!window.NativeBridge || !blob) return;" +
        "    const fname = filename || ('export_' + Date.now());" +
        "    const mime = blob.type || '';" +
        "    if (blob.size <= 262144 || !window.NativeBridge.beginFileExport) {" +
        "      const reader = new FileReader();" +
        "      reader.onloadend = function() {" +
        "        if (reader.result) window.NativeBridge.saveBase64File(reader.result, fname, mime);" +
        "      };" +
        "      reader.readAsDataURL(blob);" +
        "      return;" +
        "    }" +
        "    const sid = window.NativeBridge.beginFileExport(fname, mime);" +
        "    if (!sid) return;" +
        "    const CHUNK = 524286;" +
        "    try {" +
        "      for (let off = 0; off < blob.size; off += CHUNK) {" +
        "        const slice = blob.slice(off, off + CHUNK);" +
        "        const b64 = await new Promise(function(res, rej) {" +
        "          const r = new FileReader();" +
        "          r.onload = function() {" +
        "            const s = r.result || '';" +
        "            const idx = s.indexOf(',');" +
        "            res(idx !== -1 ? s.slice(idx + 1) : s);" +
        "          };" +
        "          r.onerror = function() { rej(r.error); };" +
        "          r.readAsDataURL(slice);" +
        "        });" +
        "        if (!window.NativeBridge.writeFileChunk(sid, b64)) {" +
        "          throw new Error('Chunk write failed');" +
        "        }" +
        "      }" +
        "      window.NativeBridge.finishFileExport(sid);" +
        "    } catch (err) {" +
        "      window.NativeBridge.abortFileExport(sid);" +
        "    }" +
        "  };" +
        "  function handleDownloadUrl(href, filename) {" +
        "    if (!href) return false;" +
        "    if (href.startsWith('blob:')) {" +
        "      const cached = window.__wsBlobStore.get(href);" +
        "      if (cached) {" +
        "        window.__wsExportBlob(cached, filename);" +
        "      } else {" +
        "        fetch(href).then(function(r) { return r.blob(); }).then(function(b) { window.__wsExportBlob(b, filename); });" +
        "      }" +
        "      return true;" +
        "    }" +
        "    if (href.startsWith('data:')) {" +
        "      if (window.NativeBridge) window.NativeBridge.saveBase64File(href, filename || ('export_' + Date.now()), '');" +
        "      return true;" +
        "    }" +
        "    return false;" +
        "  }" +
        "  const origAnchorClick = HTMLAnchorElement.prototype.click;" +
        "  HTMLAnchorElement.prototype.click = function() {" +
        "    if (this.href && (this.href.startsWith('blob:') || this.href.startsWith('data:') || this.hasAttribute('download'))) {" +
        "      if (handleDownloadUrl(this.href, this.getAttribute('download'))) return;" +
        "    }" +
        "    return origAnchorClick.apply(this, arguments);" +
        "  };" +
        "  document.addEventListener('click', function(e) {" +
        "    const a = e.target && e.target.closest ? e.target.closest('a') : null;" +
        "    if (a && a.href && (a.href.startsWith('blob:') || a.href.startsWith('data:') || a.hasAttribute('download'))) {" +
        "      if (handleDownloadUrl(a.href, a.getAttribute('download'))) {" +
        "        e.preventDefault();" +
        "        e.stopPropagation();" +
        "      }" +
        "    }" +
        "  }, true);" +
        "  if (!window.showSaveFilePicker) {" +
        "    window.showSaveFilePicker = async function(opts) {" +
        "      const suggested = (opts && opts.suggestedName) ? opts.suggestedName : ('export_' + Date.now());" +
        "      const chunks = [];" +
        "      let mime = '';" +
        "      if (opts && opts.types && opts.types[0] && opts.types[0].accept) {" +
        "        const keys = Object.keys(opts.types[0].accept);" +
        "        if (keys.length) mime = keys[0];" +
        "      }" +
        "      return {" +
        "        name: suggested," +
        "        createWritable: async function() {" +
        "          return {" +
        "            write: async function(data) {" +
        "              if (data && typeof data === 'object' && data.type === 'write') {" +
        "                chunks.push(data.data);" +
        "              } else {" +
        "                chunks.push(data);" +
        "              }" +
        "            }," +
        "            close: async function() {" +
        "              const blob = new Blob(chunks, { type: mime });" +
        "              window.__wsExportBlob(blob, suggested);" +
        "            }" +
        "          };" +
        "        }" +
        "      };" +
        "    };" +
        "  }" +
        "  if (!navigator.share) {" +
        "    navigator.share = async function(data) {" +
        "      if (!data) return;" +
        "      if (data.files && data.files.length > 0) {" +
        "        for (let i = 0; i < data.files.length; i++) {" +
        "          window.__wsExportBlob(data.files[i], data.files[i].name);" +
        "        }" +
        "        return;" +
        "      }" +
        "      if (window.NativeBridge) {" +
        "        window.NativeBridge.shareText(data.title || '', data.text || '', data.url || '');" +
        "      }" +
        "    };" +
        "  }" +
        "  if (document.head && !document.querySelector('meta[name=\"viewport\"]')) {" +
        "    var m = document.createElement('meta');" +
        "    m.name = 'viewport';" +
        "    m.content = 'width=device-width, initial-scale=1.0, viewport-fit=cover';" +
        "    document.head.appendChild(m);" +
        "  }" +
        "  window.print = function() {" +
        "    if (window.NativeBridge) window.NativeBridge.printPage();" +
        "  };" +
        "  if (__PULL_TO_REFRESH__ && !window.__wsPtrInstalled) {" +
        "    window.__wsPtrInstalled = true;" +
        "    var startY = 0, startX = 0, pulling = false, triggered = false, pill = null;" +
        "    function ensurePill() {" +
        "      if (pill && document.body && document.body.contains(pill)) return pill;" +
        "      if (!document.body) return null;" +
        "      pill = document.createElement('div');" +
        "      pill.style.cssText = 'position:fixed;top:-52px;left:50%;transform:translateX(-50%);z-index:2147483647;background:#121824;color:#10b981;border:1px solid #243044;border-radius:999px;padding:7px 16px;font:600 12px/1.2 -apple-system,sans-serif;box-shadow:0 6px 20px rgba(0,0,0,0.45);transition:top 0.16s ease,opacity 0.16s ease;opacity:0;pointer-events:none;white-space:nowrap;';" +
        "      pill.textContent = 'Pull to refresh';" +
        "      document.body.appendChild(pill);" +
        "      return pill;" +
        "    }" +
        "    function hasScrolledParent(el) {" +
        "      while (el && el !== document.body && el !== document.documentElement) {" +
        "        if (el.scrollTop && el.scrollTop > 0) return true;" +
        "        el = el.parentElement;" +
        "      }" +
        "      return false;" +
        "    }" +
        "    function atPageTop() {" +
        "      return (window.scrollY || window.pageYOffset || document.documentElement.scrollTop || (document.body && document.body.scrollTop) || 0) <= 0;" +
        "    }" +
        "    document.addEventListener('touchstart', function(e) {" +
        "      if (!e.touches || e.touches.length !== 1) { pulling = false; return; }" +
        "      if (!atPageTop() || hasScrolledParent(e.target)) { pulling = false; return; }" +
        "      startY = e.touches[0].clientY;" +
        "      startX = e.touches[0].clientX;" +
        "      pulling = true;" +
        "      triggered = false;" +
        "    }, { passive: true });" +
        "    document.addEventListener('touchmove', function(e) {" +
        "      if (!pulling || !e.touches || e.touches.length !== 1) return;" +
        "      if (!atPageTop()) { pulling = false; if (pill) { pill.style.top = '-52px'; pill.style.opacity = '0'; } return; }" +
        "      var dy = e.touches[0].clientY - startY;" +
        "      var dx = e.touches[0].clientX - startX;" +
        "      if (dy <= 6 || Math.abs(dy) < Math.abs(dx) * 1.3) return;" +
        "      var el = ensurePill();" +
        "      if (!el) return;" +
        "      var dist = Math.min(dy * 0.45, 88);" +
        "      el.style.transition = 'none';" +
        "      el.style.top = Math.round(dist - 44) + 'px';" +
        "      el.style.opacity = String(Math.min(dist / 45, 1));" +
        "      if (dist >= 62) {" +
        "        triggered = true;" +
        "        el.textContent = 'Release to refresh';" +
        "      } else {" +
        "        triggered = false;" +
        "        el.textContent = 'Pull to refresh';" +
        "      }" +
        "    }, { passive: true });" +
        "    function endPull() {" +
        "      if (!pulling) return;" +
        "      pulling = false;" +
        "      if (triggered && pill) {" +
        "        pill.style.transition = 'top 0.18s ease';" +
        "        pill.style.top = '16px';" +
        "        pill.textContent = 'Refreshing...';" +
        "        setTimeout(function() {" +
        "          if (window.NativeBridge && window.NativeBridge.reloadPage) window.NativeBridge.reloadPage();" +
        "          else window.location.reload();" +
        "        }, 120);" +
        "      } else if (pill) {" +
        "        pill.style.transition = 'top 0.18s ease, opacity 0.18s ease';" +
        "        pill.style.top = '-52px';" +
        "        pill.style.opacity = '0';" +
        "      }" +
        "    }" +
        "    document.addEventListener('touchend', endPull, { passive: true });" +
        "    document.addEventListener('touchcancel', endPull, { passive: true });" +
        "  }" +
        "})();";

    private byte[] getAppSigningCertSha256() {
        try {
            PackageManager pm = getPackageManager();
            String pkg = getPackageName();
            Signature[] sigs = null;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                PackageInfo pi = pm.getPackageInfo(pkg, PackageManager.GET_SIGNING_CERTIFICATES);
                if (pi.signingInfo != null) {
                    sigs = pi.signingInfo.hasMultipleSigners()
                        ? pi.signingInfo.getApkContentsSigners()
                        : pi.signingInfo.getSigningCertificateHistory();
                }
            }
            if (sigs == null || sigs.length == 0) {
                @SuppressWarnings("deprecation")
                PackageInfo piLegacy = pm.getPackageInfo(pkg, PackageManager.GET_SIGNATURES);
                sigs = piLegacy.signatures;
            }
            if (sigs != null && sigs.length > 0) {
                MessageDigest md = MessageDigest.getInstance("SHA-256");
                return md.digest(sigs[0].toByteArray());
            }
        } catch (Exception ignored) {}
        return new byte[32];
    }

    private void initVaultKey() {
        byte[] certHash = getAppSigningCertSha256();
        byte[] rawKey = new byte[32];
        for (int i = 0; i < 32; i++) {
            rawKey[i] = (byte) ((SEALED_KEY[i] ^ MASK_KEY[i] ^ (certHash[i] & 0xFF)) & 0xFF);
        }
        this.aesKeySpec = new SecretKeySpec(rawKey, "AES");
        Arrays.fill(rawKey, (byte) 0);
    }

    private InputStream openDecryptedAsset(String assetPath) throws Exception {
        InputStream rawIn = getAssets().open(assetPath);
        byte[] iv = new byte[16];
        int offset = 0;
        while (offset < 16) {
            int read = rawIn.read(iv, offset, 16 - offset);
            if (read == -1) {
                rawIn.close();
                throw new IOException("Corrupted encrypted asset header");
            }
            offset += read;
        }
        Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
        cipher.init(Cipher.DECRYPT_MODE, aesKeySpec, new IvParameterSpec(iv));
        return new CipherInputStream(rawIn, cipher);
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        super.onCreate(savedInstanceState);
        initVaultKey();
        __SECURE_WINDOW_CODE__
        __RUNTIME_PERMS_EXEC__

        webView = new WebView(this);
        WebSettings settings = webView.getSettings();

        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setJavaScriptCanOpenWindowsAutomatically(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setLoadWithOverviewMode(false);
        settings.setUseWideViewPort(true);
        settings.setSupportZoom(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        String defaultUa = settings.getUserAgentString();
        if (defaultUa != null) {
            settings.setUserAgentString(defaultUa.replace("; wv)", ")").replace("; wv;", ";"));
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            cookieManager.setAcceptThirdPartyCookies(webView, true);
        }

        __ZOOM_CODE__
        __COPY_PASTE_CODE__

        webView.addJavascriptInterface(new NativeBridge(), "NativeBridge");

        webView.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(String url, String userAgent, String contentDisposition, String mimetype, long contentLength) {
                if (url == null) return;
                String guessedName = URLUtil.guessFileName(url, contentDisposition, mimetype);
                if (url.startsWith("data:")) {
                    new NativeBridge().saveBase64File(url, guessedName, mimetype);
                } else if (url.startsWith("blob:")) {
                    String safeUrl = url.replace("'", "\\'");
                    String safeName = guessedName.replace("'", "\\'");
                    webView.evaluateJavascript(
                        "fetch('" + safeUrl + "').then(r=>r.blob()).then(b=>window.__wsExportBlob(b,'" + safeName + "'));",
                        null
                    );
                } else if (url.startsWith("http://") || url.startsWith("https://")) {
                    try {
                        DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
                        req.setMimeType(mimetype);
                        req.addRequestHeader("User-Agent", userAgent);
                        req.setTitle(guessedName);
                        req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                        req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, guessedName);
                        DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                        if (dm != null) {
                            dm.enqueue(req);
                            Toast.makeText(MainActivity.this, "Downloading: " + guessedName, Toast.LENGTH_SHORT).show();
                        }
                    } catch (Exception e) {
                        Toast.makeText(MainActivity.this, "Download failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
                    }
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> filePathCallback, FileChooserParams fileChooserParams) {
                if (uploadMessage != null) {
                    uploadMessage.onReceiveValue(null);
                    uploadMessage = null;
                }
                uploadMessage = filePathCallback;
                try {
                    Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
                    intent.addCategory(Intent.CATEGORY_OPENABLE);
                    intent.setType("*/*");
                    intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                    startActivityForResult(Intent.createChooser(intent, "Select File"), FILE_CHOOSER_RESULT_CODE);
                } catch (Exception e) {
                    uploadMessage = null;
                    return false;
                }
                return true;
            }

            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            request.grant(request.getResources());
                        }
                    });
                }
            }

            @Override
            public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback callback) {
                callback.invoke(origin, __ENABLE_LOCATION__, false);
            }

            @Override
            public boolean onJsAlert(WebView view, String url, String message, final JsResult result) {
                new AlertDialog.Builder(MainActivity.this)
                    .setTitle("Alert")
                    .setMessage(message)
                    .setPositiveButton(android.R.string.ok, new DialogInterface.OnClickListener() {
                        public void onClick(DialogInterface dialog, int which) {
                            result.confirm();
                        }
                    })
                    .setCancelable(false)
                    .show();
                return true;
            }

            @Override
            public boolean onJsConfirm(WebView view, String url, String message, final JsResult result) {
                new AlertDialog.Builder(MainActivity.this)
                    .setTitle("Confirm")
                    .setMessage(message)
                    .setPositiveButton(android.R.string.ok, new DialogInterface.OnClickListener() {
                        public void onClick(DialogInterface dialog, int which) {
                            result.confirm();
                        }
                    })
                    .setNegativeButton(android.R.string.cancel, new DialogInterface.OnClickListener() {
                        public void onClick(DialogInterface dialog, int which) {
                            result.cancel();
                        }
                    })
                    .setCancelable(false)
                    .show();
                return true;
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri uri = (request != null) ? request.getUrl() : null;
                if (uri == null) return super.shouldInterceptRequest(view, request);

                String host = uri.getHost();
                if (VIRTUAL_HOST.equalsIgnoreCase(host)) {
                    String path = uri.getPath();
                    if (path == null || path.isEmpty() || "/".equals(path)) {
                        path = "/index.html";
                    } else if (path.endsWith("/")) {
                        path = path + "index.html";
                    }
                    if (path.contains("..")) {
                        return new WebResourceResponse("text/plain", "UTF-8", 403, "Forbidden", null, null);
                    }
                    String assetPath = "web" + (path.startsWith("/") ? path : "/" + path);
                    Map<String, String> headers = new HashMap<String, String>();
                    headers.put("Access-Control-Allow-Origin", "*");
                    headers.put("Cache-Control", "no-cache");
                    try {
                        InputStream is = openDecryptedAsset(assetPath);
                        String mime = guessMimeType(assetPath);
                        String encoding = isTextMime(mime) ? "UTF-8" : null;
                        return new WebResourceResponse(mime, encoding, 200, "OK", headers, is);
                    } catch (FileNotFoundException e) {
                        if (!path.contains(".")) {
                            try {
                                InputStream fallback = openDecryptedAsset("web/index.html");
                                return new WebResourceResponse("text/html", "UTF-8", 200, "OK", headers, fallback);
                            } catch (Exception ignored) {}
                        }
                        return new WebResourceResponse("text/plain", "UTF-8", 404, "Not Found", headers, new ByteArrayInputStream(new byte[0]));
                    } catch (Exception e) {
                        return new WebResourceResponse("text/plain", "UTF-8", 500, "Server Error", headers, new ByteArrayInputStream(new byte[0]));
                    }
                }

                if (FORCE_OFFLINE && ("http".equalsIgnoreCase(uri.getScheme()) || "https".equalsIgnoreCase(uri.getScheme()))) {
                    return new WebResourceResponse("text/plain", "UTF-8", 403, "Offline Mode", null, new ByteArrayInputStream(new byte[0]));
                }
                return super.shouldInterceptRequest(view, request);
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String target = (request != null && request.getUrl() != null) ? request.getUrl().toString() : "";
                if (target.isEmpty()) return false;
                if (!target.startsWith("http://") && !target.startsWith("https://") && !target.startsWith("about:") && !target.startsWith("javascript:") && !target.startsWith("blob:") && !target.startsWith("data:")) {
                    try {
                        Intent ext = new Intent(Intent.ACTION_VIEW, Uri.parse(target));
                        startActivity(ext);
                    } catch (Exception ignored) {}
                    return true;
                }
                if (FORCE_OFFLINE && (target.startsWith("http://") || target.startsWith("https://")) && !target.startsWith(VIRTUAL_ORIGIN)) {
                    return true;
                }
                return false;
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                super.onPageStarted(view, url, favicon);
                view.evaluateJavascript(BRIDGE_JS, null);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                view.evaluateJavascript(BRIDGE_JS, null);
                if (url != null && (url.equals(ROOT_URL) || url.equals(VIRTUAL_ORIGIN + "/") || url.endsWith("/index.html"))) {
                    view.clearHistory();
                }
            }
        });

        if (RESPECT_SYSTEM_BARS) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                try {
                    getWindow().setStatusBarColor(0xFF0B0F17);
                    getWindow().setNavigationBarColor(0xFF0B0F17);
                } catch (Exception ignored) {}
            }
            final FrameLayout rootContainer = new FrameLayout(this);
            rootContainer.setBackgroundColor(0xFF0B0F17);
            rootContainer.addView(webView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ));
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT_WATCH) {
                rootContainer.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener() {
                    @Override
                    public WindowInsets onApplyWindowInsets(View v, WindowInsets insets) {
                        if (Build.VERSION.SDK_INT >= 30) {
                            Insets bars = insets.getInsets(
                                WindowInsets.Type.systemBars()
                                | WindowInsets.Type.displayCutout()
                                | WindowInsets.Type.ime()
                            );
                            v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                        } else {
                            v.setPadding(
                                insets.getSystemWindowInsetLeft(),
                                insets.getSystemWindowInsetTop(),
                                insets.getSystemWindowInsetRight(),
                                insets.getSystemWindowInsetBottom()
                            );
                        }
                        return insets;
                    }
                });
            }
            setContentView(rootContainer);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT_WATCH) {
                rootContainer.requestApplyInsets();
            }
            rootContainer.post(new Runnable() {
                @Override
                public void run() {
                    webView.loadUrl(ROOT_URL);
                }
            });
        } else {
            setContentView(webView);
            webView.loadUrl(ROOT_URL);
        }
    }

    private class NativeBridge {
        @JavascriptInterface
        public void reloadPage() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    if (webView != null) {
                        webView.reload();
                    }
                }
            });
        }

        @JavascriptInterface
        public void saveBase64File(final String base64Data, final String rawFilename, final String explicitMime) {
            try {
                if (base64Data == null || base64Data.isEmpty()) return;
                String detectedMime = (explicitMime != null && !explicitMime.isEmpty()) ? explicitMime : "application/octet-stream";
                String pureBase64 = base64Data;
                if (base64Data.startsWith("data:")) {
                    int commaIdx = base64Data.indexOf(",");
                    if (commaIdx != -1) {
                        String meta = base64Data.substring(5, commaIdx);
                        int semiIdx = meta.indexOf(";");
                        String parsedMime = (semiIdx != -1) ? meta.substring(0, semiIdx) : meta;
                        if (!parsedMime.isEmpty()) {
                            detectedMime = parsedMime;
                        }
                        pureBase64 = base64Data.substring(commaIdx + 1);
                    }
                }

                byte[] bytes = Base64.decode(pureBase64, Base64.DEFAULT);
                String safeName = sanitizeFilename(rawFilename, detectedMime);

                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    ContentValues values = new ContentValues();
                    values.put(MediaStore.Downloads.DISPLAY_NAME, safeName);
                    values.put(MediaStore.Downloads.MIME_TYPE, detectedMime);
                    values.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);
                    ContentResolver resolver = getContentResolver();
                    Uri uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                    if (uri != null) {
                        OutputStream out = resolver.openOutputStream(uri);
                        if (out != null) {
                            out.write(bytes);
                            out.flush();
                            out.close();
                        }
                    }
                } else {
                    File downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
                    if (!downloadsDir.exists()) downloadsDir.mkdirs();
                    File outFile = new File(downloadsDir, safeName);
                    FileOutputStream fos = new FileOutputStream(outFile);
                    fos.write(bytes);
                    fos.flush();
                    fos.close();
                    MediaScannerConnection.scanFile(MainActivity.this, new String[]{outFile.getAbsolutePath()}, new String[]{detectedMime}, null);
                }

                final String finalName = safeName;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        Toast.makeText(MainActivity.this, "Saved to Downloads: " + finalName, Toast.LENGTH_LONG).show();
                    }
                });
            } catch (final Exception e) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        Toast.makeText(MainActivity.this, "Export error: " + e.getMessage(), Toast.LENGTH_LONG).show();
                    }
                });
            }
        }

        @JavascriptInterface
        public void printPage() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    try {
                        PrintManager printManager = (PrintManager) getSystemService(Context.PRINT_SERVICE);
                        if (printManager != null && webView != null) {
                            String jobName = APP_TITLE + " Document";
                            PrintDocumentAdapter adapter = webView.createPrintDocumentAdapter(jobName);
                            printManager.print(jobName, adapter, new PrintAttributes.Builder().build());
                        }
                    } catch (Exception e) {
                        Toast.makeText(MainActivity.this, "Print error: " + e.getMessage(), Toast.LENGTH_LONG).show();
                    }
                }
            });
        }

        @JavascriptInterface
        public void shareText(final String title, final String text, final String url) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    try {
                        StringBuilder body = new StringBuilder();
                        if (text != null && !text.isEmpty()) body.append(text);
                        if (url != null && !url.isEmpty()) {
                            if (body.length() > 0) body.append("\n");
                            body.append(url);
                        }
                        Intent sendIntent = new Intent(Intent.ACTION_SEND);
                        sendIntent.setType("text/plain");
                        if (title != null && !title.isEmpty()) sendIntent.putExtra(Intent.EXTRA_SUBJECT, title);
                        sendIntent.putExtra(Intent.EXTRA_TEXT, body.toString());
                        startActivity(Intent.createChooser(sendIntent, title != null && !title.isEmpty() ? title : "Share"));
                    } catch (Exception e) {
                        Toast.makeText(MainActivity.this, "Share error: " + e.getMessage(), Toast.LENGTH_LONG).show();
                    }
                }
            });
        }
    }

    private String sanitizeFilename(String name, String mime) {
        String clean = (name == null || name.trim().isEmpty()) ? ("export_" + System.currentTimeMillis()) : name.trim();
        clean = clean.replaceAll("[\\\\/:*?\"<>|]", "_");
        if (!clean.contains(".")) {
            String ext = extensionFromMime(mime);
            if (!ext.isEmpty()) clean = clean + "." + ext;
        }
        return clean;
    }

    private String extensionFromMime(String mime) {
        if (mime == null) return "";
        String m = mime.toLowerCase(Locale.US);
        if (m.contains("pdf")) return "pdf";
        if (m.contains("json")) return "json";
        if (m.contains("epub")) return "epub";
        if (m.contains("zip")) return "zip";
        if (m.contains("csv")) return "csv";
        if (m.contains("html")) return "html";
        if (m.contains("xml")) return "xml";
        if (m.contains("markdown")) return "md";
        if (m.contains("text/plain")) return "txt";
        if (m.contains("png")) return "png";
        if (m.contains("jpeg") || m.contains("jpg")) return "jpg";
        if (m.contains("webp")) return "webp";
        if (m.contains("svg")) return "svg";
        if (m.contains("mp3") || m.contains("mpeg")) return "mp3";
        if (m.contains("mp4")) return "mp4";
        return "";
    }

    private boolean isTextMime(String mime) {
        return mime.startsWith("text/") || mime.equals("application/javascript") || mime.equals("application/json") || mime.equals("application/xml") || mime.equals("image/svg+xml");
    }

    private String guessMimeType(String path) {
        String p = path.toLowerCase(Locale.US);
        if (p.endsWith(".html") || p.endsWith(".htm")) return "text/html";
        if (p.endsWith(".js") || p.endsWith(".mjs")) return "application/javascript";
        if (p.endsWith(".css")) return "text/css";
        if (p.endsWith(".json") || p.endsWith(".map")) return "application/json";
        if (p.endsWith(".wasm")) return "application/wasm";
        if (p.endsWith(".svg")) return "image/svg+xml";
        if (p.endsWith(".png")) return "image/png";
        if (p.endsWith(".jpg") || p.endsWith(".jpeg")) return "image/jpeg";
        if (p.endsWith(".gif")) return "image/gif";
        if (p.endsWith(".webp")) return "image/webp";
        if (p.endsWith(".ico")) return "image/x-icon";
        if (p.endsWith(".woff")) return "font/woff";
        if (p.endsWith(".woff2")) return "font/woff2";
        if (p.endsWith(".ttf")) return "font/ttf";
        if (p.endsWith(".otf")) return "font/otf";
        if (p.endsWith(".mp3")) return "audio/mpeg";
        if (p.endsWith(".wav")) return "audio/wav";
        if (p.endsWith(".ogg")) return "audio/ogg";
        if (p.endsWith(".mp4")) return "video/mp4";
        if (p.endsWith(".webm")) return "video/webm";
        if (p.endsWith(".pdf")) return "application/pdf";
        if (p.endsWith(".xml")) return "application/xml";
        if (p.endsWith(".csv")) return "text/csv";
        if (p.endsWith(".txt") || p.endsWith(".md")) return "text/plain";
        if (p.endsWith(".zip")) return "application/zip";
        if (p.endsWith(".epub")) return "application/epub+zip";
        return "application/octet-stream";
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER_RESULT_CODE) {
            if (uploadMessage == null) return;
            Uri[] results = null;
            if (resultCode == Activity.RESULT_OK && data != null) {
                String dataString = data.getDataString();
                if (dataString != null) {
                    results = new Uri[]{Uri.parse(dataString)};
                } else if (data.getClipData() != null) {
                    int count = data.getClipData().getItemCount();
                    results = new Uri[count];
                    for (int i = 0; i < count; i++) {
                        results[i] = data.getClipData().getItemAt(i).getUri();
                    }
                }
            }
            uploadMessage.onReceiveValue(results);
            uploadMessage = null;
        }
    }

    @Override
    public void onBackPressed() {
        String currentUrl = (webView != null) ? webView.getUrl() : null;
        boolean isHome = (currentUrl == null || currentUrl.equals(ROOT_URL) || currentUrl.equals(VIRTUAL_ORIGIN + "/") || currentUrl.endsWith("/index.html"));

        if (isHome || !webView.canGoBack()) {
            showExitDialog();
        } else {
            webView.goBack();
        }
    }

    private void showExitDialog() {
        new AlertDialog.Builder(this)
            .setTitle("Exit App")
            .setMessage("Are you sure you want to exit?")
            .setPositiveButton("Exit", new DialogInterface.OnClickListener() {
                @Override
                public void onClick(DialogInterface dialog, int which) {
                    finish();
                }
            })
            .setNegativeButton("Cancel", null)
            .show();
    }
}
"""

        safe_app_title = app_label.replace("\\", "\\\\").replace('"', '\\"')
        main_java = (
            java_template
            .replace("__PACKAGE_ID__", package_id)
            .replace("__ROOT_URL__", (clean_url if is_url_mode else "https://appassets.androidplatform.net/index.html").replace("\\", "\\\\").replace('"', '\\"'))
            .replace("__FORCE_OFFLINE__", str(force_offline).lower())
            .replace("__PULL_TO_REFRESH__", str(pull_to_refresh).lower())
            .replace("__RESPECT_SYSTEM_BARS__", str(respect_system_bars).lower())
            .replace("__APP_TITLE__", safe_app_title)
            .replace("__SEALED_KEY_ARR__", sealed_java_arr)
            .replace("__MASK_KEY_ARR__", mask_java_arr)
            .replace("__SECURE_WINDOW_CODE__", secure_window_code)
            .replace("__RUNTIME_PERMS_EXEC__", runtime_perms_exec)
            .replace("__ZOOM_CODE__", zoom_code)
            .replace("__COPY_PASTE_CODE__", copy_paste_code)
            .replace("__ENABLE_LOCATION__", str(enable_location).lower())
        )

        with open(os.path.join(pkg_dir, "MainActivity.java"), "w") as f:
            f.write(main_java)

        # 9. Resource Generation via AAPT
        emit("Generating R.java symbols via AAPT...")
        run_cmd(f"aapt package -m -J {src_dir} -M {manifest_path} -S {res_dir} -I {LIBS_JAR}", log_fn=emit)

        # 10. Java Compilation
        emit("Compiling Java classes (Java 8 target)...")
        java_files = []
        for root, _, files in os.walk(src_dir):
            for file in files:
                if file.endswith(".java"):
                    java_files.append(os.path.join(root, file))
        run_cmd(f"javac -cp {LIBS_JAR} -d {classes_dir} -g:none -source 1.8 -target 1.8 {' '.join(java_files)}", log_fn=emit)

        # 11. Bytecode translation to DEX
        emit("Translating bytecode to classes.dex...")
        dex_path = os.path.join(bin_dir, "classes.dex")
        run_cmd(f"dx --dex --output={dex_path} {classes_dir}", log_fn=emit)

        # 12. Package APK Container
        emit("Assembling base APK package with AAPT...")
        unaligned_apk = os.path.join(bin_dir, "unaligned.apk")
        run_cmd(f"aapt package -f -F {unaligned_apk} -M {manifest_path} -S {res_dir} -A {os.path.join(build_sandbox, 'assets')} -I {LIBS_JAR}", log_fn=emit)

        # 13. Add DEX into Container
        emit("Adding classes.dex into APK root...")
        run_cmd("aapt add unaligned.apk classes.dex", cwd=bin_dir, log_fn=emit)

        # 14. 4-Byte Alignment
        emit("Aligning APK container (4-byte boundary)...")
        aligned_apk = os.path.join(bin_dir, "aligned.apk")
        run_cmd(f"zipalign -f -p 4 {unaligned_apk} {aligned_apk}", log_fn=emit)

        # 15. Cryptographic Signing
        ks = keystore_path if keystore_path and os.path.exists(keystore_path) else os.path.join(WORKSTATION_ROOT, "keystores", "master.jks")
        emit(f"Signing APK via apksigner with key alias '{key_alias}'...")
        run_cmd(f"apksigner sign --ks {ks} --ks-pass pass:{keystore_pass} --key-pass pass:{key_pass} --ks-key-alias {key_alias} --out {output_apk_path} {aligned_apk}", log_fn=emit)

        # 16. Shared Storage Backup (Never Overwritten)
        if os.path.exists(SHARED_DOWNLOADS):
            target_shared = os.path.join(SHARED_DOWNLOADS, os.path.basename(output_apk_path))
            shutil.copy2(output_apk_path, target_shared)
            emit(f"Archived copy delivered to: {target_shared}")

        emit("Clean single-DEX build sequence completed successfully.")
        return output_apk_path

    finally:
        shutil.rmtree(build_sandbox, ignore_errors=True)
