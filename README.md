# APK Workstation

**Creator & Maintainer:** Resteus  
**AI Co-Architect:** Gemini  
**Repository:** https://github.com/Resteus/apk-workstation  
**Project Started:** November 11, 2026  
**Public Release:** November 24, 2026 (`v1.0.0`)  
**License:** MIT (see repository license)  
**Target Platform:** Android (Termux / ARM64)

APK Workstation is a self-hosted, mobile-first HTML/URL-to-APK compiler and studio engineered to run natively inside Termux on an Android smartphone—with zero PC, zero Android Studio, and zero Gradle overhead.

---

## Project Origin & Development Timeline

If you inspect the Git commit timestamps, you will see a clean initial baseline from **November 24, 2026**. Before publishing `v1.0.0`, the repository history was intentionally squashed and scrubbed to remove early scratch scripts, local test builds, and private development artifacts.

- **November 11, 2026 — Project Inception:** Built the initial Bottle/Waitress backend, low-level `aapt` + `javac` + `dx` + `apksigner` compilation flow, and local keystore generation directly on an Android smartphone.
- **November 12, 2026 — Security Vault & Real-World App Testing:** Implemented per-build **AES-256-CBC** asset encryption bound to the APK signing certificate, added JSON app profiles with auto-incrementing version codes, created `backup_vault.sh`, and validated real offline/online builds.
- **November 24, 2026 — Android 15/16 Polish & Public Release:** Added edge-to-edge `WindowInsets` safe-area protection, universal pull-to-refresh, `NativeBridge` chunked file exports, full documentation, and published `v1.0.0` under **Resteus**.

---

## About the Builders

- **Resteus (Creator & Lead Developer):** Conceived, built, and stress-tested the mobile-first architecture, runtime requirements, and Termux build workflow entirely on a smartphone.
- **Gemini (AI Co-Architect):** Collaborated as technical pair-programmer and systems architect—helping design the pure-Java compilation pipeline, certificate-bound AES-256 asset vault, Android 15/16 window-inset wrapper, and Java-to-JavaScript bridge.

---

## Reference Device & Build Environment

Every build stage, memory constraint, and touch UI component was developed and verified on the following hardware:

- **Device:** realme RMX5020
- **Operating System:** Android 16 (realme UI 7.0, `aarch64` / ARM64)
- **Processor (SoC):** MediaTek MT6769 (Octa-core @ 2.0 GHz)
- **Graphics (GPU):** Mali-G52 MC2
- **Memory:** 8 GB RAM
- **Runtime Shell:** Termux (`bash`) + Python (`Bottle` & `Waitress`)

---

## Detailed Features

### 1. Three Flexible Build Modes
- **Encrypted Offline Archive (`.zip`):** Unpacks any web project containing `index.html`, encrypts every asset in-place, and packages a standalone offline APK.
- **Local Termux Directory Build:** Compiles directly from a local folder path on your device without manually zipping files first.
- **Live Website URL (`https://`):** Wraps hosted web apps in a tuned mobile WebView with 1:1 viewport scaling (`setLoadWithOverviewMode(false)`), clean Chrome mobile User-Agent headers, and `adjustResize` soft-keyboard handling.

### 2. Zero-Gradle Native Compilation Pipeline (`core/builder.py`)
- **Pure CLI Toolchain:** Generates `AndroidManifest.xml` and `MainActivity.java` dynamically, compiles resources with `aapt`, compiles Java 8 bytecode with `javac`, converts classes to Dalvik bytecode with `dx`, aligns with `zipalign`, and signs with `apksigner`.
- **Certificate-Bound AES-256-CBC Asset Vault:** For offline builds, every HTML, CSS, JS, font, and media asset is encrypted with a random 16-byte IV. The decryption key is obfuscated inside compiled Java bytecode (`SEALED_KEY ^ MASK_KEY ^ certHash`) and reconstructed at runtime from the APK's live **SHA-256 signing certificate fingerprint**. Re-signing or tampering with the APK automatically breaks decryption.
- **Virtual HTTPS Origin:** Decrypted offline assets stream directly from memory over `https://appassets.androidplatform.net/` via `WebResourceResponse`—leaving zero plaintext files extracted on device storage.

### 3. Future-Proof SDK Matrix & Platform Inspector
- **Configurable SDK Targets:** Customize `minSdkVersion` (default `21`) and `targetSdkVersion` (default `36`, adjustable to `37`, `38`, `100+` to meet future Android requirements).
- **Built-In `android.jar` Manager:** Inspect the active platform API level or upload a newer `libs/android.jar` directly from the web UI.

### 4. Modern Android 15/16 Runtime & `window.NativeBridge`
- **Safe-Area System Bars:** Wraps the WebView inside a `FrameLayout` that applies `WindowInsets` (`systemBars`, `displayCutout`, and `ime`) prior to initial page load so status bars, notches, and navigation bars never overlap website headers or bottom toolbars.
- **Universal Pull-to-Refresh:** Built-in touch gesture that reloads websites, encrypted ZIPs, and local projects when pulling down from the top without hijacking inner scrollable lists.
- **Chunked File & Blob Downloads:** Supports 512 KB chunked `Blob` / `File` exports straight to Android `Downloads/`, complete with `showSaveFilePicker` and `navigator.share` polyfills.
- **Granular Device & Security Controls:** Per-build toggles for Camera, Storage, Location, and Notification permissions, screen orientation lock (`Portrait`, `Landscape`, `Auto`), pinch-to-zoom, text selection/copy-paste, and `FLAG_SECURE` screenshot/screen-recording protection.

### 5. Keystore Vault, App Profiles & Automated Backups
- **Keystore Manager:** Generate `.jks` signing keys in-app, inspect certificate fingerprints/aliases, and sign release builds cleanly.
- **App Profiles:** Automatically saves per-package build configurations (`profiles/`) and increments `versionCode` and `versionName` for seamless Android app updates.
- **Snapshot Backups (`backup_vault.sh`):** Archives `keystores/`, `profiles/`, and `libs/android.jar` into timestamped `.tar.gz` snapshots (`backups/`) and mirrors them to `/sdcard/Archives/apk-workstation/`.

---

## Repository Layout

    apk-workstation/
    |-- server.py            # Bottle + Waitress web server & REST API
    |-- backup_vault.sh      # Timestamped keystore & profile backup script
    |-- requirements.txt     # Python dependencies (Bottle, Waitress)
    |-- INSTALLATION.md      # Step-by-step Termux setup & troubleshooting guide
    |-- core/
    |   `-- builder.py       # Pure-Java APK compiler, AES-256 vault & WebView bridge
    |-- static/
    |   |-- index.html       # Mobile-first Studio UI
    |   `-- assets/          # Studio CSS & client-side state logic
    |-- custom-base/
    |   `-- res/             # Base Android resource templates
    |-- libs/                # Place platform android.jar here (git-ignored)
    |-- keystores/           # Local .jks signing keys (git-ignored)
    |-- profiles/            # Saved per-app build configurations (git-ignored)
    `-- builds/              # Compiled output APKs (git-ignored)

---

## Quick Start

For full Termux package installation, `android.jar` setup, and troubleshooting, read **`INSTALLATION.md`**.

    git clone https://github.com/Resteus/apk-workstation.git
    cd apk-workstation
    pip install -r requirements.txt
    python server.py

Open `http://127.0.0.1:8080` in your mobile browser.

---

## Reporting Issues & Feedback

Encountered a bug, device-specific quirk, or build error? Please open an issue on GitHub so it can be investigated and improved:

- **Issue Tracker:** https://github.com/Resteus/apk-workstation/issues

To help diagnose problems quickly, please include:
1. Your **Android version** and **device architecture** (e.g., Android 16, `aarch64`).
2. The **build mode** used (`.zip` archive, local folder, or `https://` URL) and target SDK settings.
3. The relevant snippet from your **APK Workstation build log** or `server.log`.

Feature suggestions and pull requests from fellow Termux and mobile developers are always welcome.

---

## Disclaimer

- **Intended Use:** APK Workstation is built for personal development, educational exploration, offline web-app packaging, and testing applications you own or have explicit permission to distribute.
- **Third-Party Websites & Content:** When using Live Website URL mode, users are solely responsible for respecting website Terms of Service, copyrights, trademarks, and applicable laws. Do not package or redistribute third-party websites or intellectual property without authorization.
- **Keystore Responsibility:** Android app updates require the exact `.jks` keystore and alias used to sign the original release. Always back up your `keystores/` directory—lost signing keys cannot be recovered.
- **No Warranty:** This software is provided "as is", without warranty of any kind, under the terms of the repository's MIT License.
