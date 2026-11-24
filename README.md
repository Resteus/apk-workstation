# APK Workstation

**Author:** Resteus  
**Platform:** Android (Termux / ARM64) & Python

Mobile-first HTML/URL-to-APK studio that builds
standalone, signed Android APKs directly on an
Android device without Android Studio or a PC.

## Core Features

- **Encrypted Offline Archive (.zip):** Bundles web
  projects with per-build AES-256-CBC asset
  encryption bound to the signing certificate.
- **Local Directory Mode:** Compiles directly from
  a local folder containing `index.html`.
- **Live Website URL (`https://`):** Wraps live
  web apps with 1:1 mobile scaling and safe-area
  system bar insets.
- **Future-Proof SDK Matrix:** Configurable
  `minSdkVersion` and `targetSdkVersion` (36+),
  plus UI uploader for `libs/android.jar`.
- **Native Runtime Bridge:** Chunked Blob/File
  downloads, pull-to-refresh, runtime permissions,
  and `FLAG_SECURE` screenshot protection.

## Termux Setup

Install required CLI tools and Python packages:

    pkg install python openjdk-17 aapt apksigner dx
    pip install bottle waitress

Place an Android platform `android.jar` inside
`libs/android.jar`, then start the studio:

    python server.py

Open `http://127.0.0.1:8080` in your browser.
