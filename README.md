# APK Workstation

**Creator & Maintainer:** Resteus  
**AI Co-Architect:** Gemini  
**Repository:** https://github.com/Resteus/apk-workstation  
**License:** MIT (see repository license)  
**Target Platform:** Android (Termux / ARM64)

APK Workstation is a self-hosted, mobile-first HTML/URL-to-APK compiler and studio built to run natively inside Termux on an Android smartphone—with zero PC, zero Android Studio, and zero Gradle overhead.

---

## About the Builders

- **Resteus (Creator & Lead Developer):** Designed, tested, and engineered the mobile-first workflow, runtime requirements, and local Termux toolchain entirely on a smartphone.
- **Gemini (AI Co-Architect):** Collaborated as the technical pair-programmer and systems architect—helping design the pure-Java compilation pipeline, AES-256 certificate-bound asset vault, Android 15/16 window-inset handling, and native JavaScript bridge.

---

## Reference Device & Build Environment

Every build pipeline, memory limit, and UI layout in this repository was engineered and verified directly on the following mobile hardware:

- **Device:** realme RMX5020
- **Operating System:** Android 16 (realme UI 7.0, `aarch64` / ARM64)
- **Processor (SoC):** MediaTek MT6769 (Octa-core @ 2.0 GHz)
- **Graphics (GPU):** Mali-G52 MC2
- **Memory:** 8 GB RAM
- **Runtime Shell:** Termux (`bash`) + Python (`Bottle` & `Waitress`)

---

## How APK Workstation Works

Instead of relying on heavy desktop SDK wrappers, APK Workstation drives Android's low-level CLI build utilities directly from Python (`core/builder.py`) while exposing a touch-friendly dark-mode control panel (`server.py` on `http://127.0.0.1:8080`).

### 1. Three Build Modes
- **Encrypted Offline Archive (`.zip`):** Unpacks a web project containing `index.html`, encrypts every asset in-place, and packages it into a self-contained offline APK.
- **Local Directory Build:** Compiles directly from a local Termux folder path without manually zipping files first.
- **Live Website URL (`https://`):** Wraps an online web application inside a tuned mobile WebView with 1:1 viewport scaling (`setLoadWithOverviewMode(false)`), clean Chrome mobile User-Agent headers, and `adjustResize` keyboard handling.

### 2. Zero-Gradle Compilation Pipeline
When a build is triggered, `core/builder.py` executes an isolated 14-stage native pipeline:
1. **Asset Staging & Encryption:** For offline builds, every HTML, CSS, JS, and media file is encrypted in-place using **AES-256-CBC** with a random 16-byte IV per file.
2. **Signature-Locked Key Derivation:** The decryption key is obfuscated inside compiled Java bytecode (`SEALED_KEY ^ MASK_KEY ^ certHash`) and reconstructed at runtime using the APK's live **SHA-256 signing certificate fingerprint**. If an APK is tampered with or re-signed with an unauthorized key, decryption fails automatically.
3. **Dynamic Manifest & SDK Matrix:** Generates `AndroidManifest.xml` on the fly with custom package IDs, version codes/names, launcher icons, permission flags, and configurable `minSdkVersion` (default `21`) and `targetSdkVersion` (default `36`, ready for `37`, `38`, and beyond).
4. **Native Binary Packaging:** Compiles resources via `aapt`, compiles `MainActivity.java` via `javac` (Java 8 target), translates bytecode into `classes.dex` via `dx`, aligns the archive on a 4-byte boundary via `zipalign`, and signs the final APK with `apksigner`.

### 3. In-App Runtime & NativeBridge
Generated APKs ship with an injected Java-to-JavaScript bridge (`window.NativeBridge`) and modern Android runtime polish:
- **Virtual HTTPS Origin:** Offline encrypted assets stream directly from memory over `https://appassets.androidplatform.net/` via `WebResourceResponse`—leaving zero plaintext files on device storage.
- **Safe-Area System Bars:** Wraps the WebView in a `FrameLayout` that reads Android 15/16 `WindowInsets` (`systemBars`, `displayCutout`, and `ime`) prior to initial page load so status bars and navigation bars never clip website headers or footers.
- **Universal Pull-to-Refresh:** Lightweight touch gesture that triggers a clean page reload when pulling down at the top of a view without interfering with inner scrollable containers.
- **File Export & Hardware Controls:** Supports 512 KB chunked `Blob` / `File` downloads to Android `Downloads/`, `showSaveFilePicker` and `navigator.share` polyfills, runtime permissions (Camera, Storage, Location, Notifications), screen orientation lock, and `FLAG_SECURE` screenshot blocking.

---

## Repository Layout

    apk-workstation/
    |-- server.py            # Bottle + Waitress web server & REST API
    |-- backup_vault.sh      # Timestamped keystore & profile backup script
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

For complete Termux package installation, `android.jar` setup, and CLI launcher instructions, see **`INSTALLATION.md`**.

    git clone https://github.com/Resteus/apk-workstation.git
    cd apk-workstation
    python server.py

Once running, open `http://127.0.0.1:8080` in your mobile browser.

---

## Disclaimer

- **Intended Use:** APK Workstation is built for personal development, educational exploration, offline web-app packaging, and testing applications you own or have explicit permission to distribute.
- **Third-Party Websites & Content:** When using Live Website URL mode, users are solely responsible for respecting website Terms of Service, copyrights, trademarks, and applicable laws. Do not package or redistribute third-party websites or intellectual property without authorization.
- **Keystore Responsibility:** Android app updates require the exact `.jks` keystore and alias used to sign the original release. Always back up your `keystores/` directory—lost signing keys cannot be recovered.
- **No Warranty:** This software is provided "as is", without warranty of any kind, under the terms of the repository's MIT License.
