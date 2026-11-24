# Installation & Setup Guide

**Project:** APK Workstation  
**Author:** Resteus  
**Repository:** https://github.com/Resteus/apk-workstation

This guide walks through setting up **APK Workstation** from scratch on an Android smartphone using **Termux**—no PC or Android Studio required.

---

## 1. System & Hardware Requirements

- **Device:** Android smartphone or tablet (`aarch64` / ARM64 recommended)
- **OS Version:** Android 10 or newer (verified on Android 16 / realme UI 7.0)
- **RAM:** 4 GB minimum (8 GB recommended for fast `javac` + `dx` compilation)
- **Free Storage:** ~600 MB (for OpenJDK 17, Android CLI build tools, `android.jar`, and compiled APKs)
- **Terminal App:** **Termux** installed from [F-Droid](https://f-droid.org/) or [Termux GitHub Releases](https://github.com/termux/termux-app/releases) *(avoid the outdated Google Play Store build)*

---

## 2. Prepare Termux & Storage Access

Open Termux, update the package index, and grant shared storage permission so you can access compiled APKs and vault backups from your Android file manager:

    pkg update && pkg upgrade -y
    termux-setup-storage

If `pkg update` fails due to a slow mirror, switch mirrors first:

    termux-change-repo

---

## 3. Install Required CLI Build Tools & Python Packages

Install OpenJDK 17, Android packaging utilities (`aapt`, `dx`, `apksigner`), OpenSSL (for AES-256 asset encryption), Git, and Python:

    pkg install -y python openjdk-17 aapt apksigner dx openssl-tool git curl

Verify that every required binary is available in your `PATH`:

    which python javac keytool aapt dx zipalign apksigner openssl

*(If any command returns "not found", re-run `pkg install` for that package.)*

---

## 4. Clone the Repository & Install Python Dependencies

Clone **APK Workstation** into your Termux home directory:

    cd ~
    git clone https://github.com/Resteus/apk-workstation.git
    cd ~/apk-workstation

*(Optional)* Create and activate an isolated Python virtual environment:

    python -m venv .venv
    source .venv/bin/activate

Install the required Python web server libraries (`Bottle` and `Waitress`):

    pip install --upgrade pip
    pip install -r requirements.txt

---

## 5. Add the Android Platform SDK (`libs/android.jar`)

Because `android.jar` is a ~21 MB Android SDK binary, it is excluded from Git. You need **one** valid `android.jar` file (API 33, 34, 35, or 36+) placed at `~/apk-workstation/libs/android.jar`.

You can set this up in either of two ways:

### Option A: Copy via Termux Terminal
If you already have an `android.jar` saved in your phone's `Download` folder:

    mkdir -p ~/apk-workstation/libs
    cp ~/storage/downloads/android.jar ~/apk-workstation/libs/android.jar

### Option B: Upload via the Web UI
1. Start the server first (see Section 6).
2. Open `http://127.0.0.1:8080` in your browser.
3. Go to the **Keystores** tab, scroll to **Platform SDK (`android.jar`)**, and upload your `android.jar` file directly.

---

## 6. Start APK Workstation

Launch the server in the foreground:

    cd ~/apk-workstation
    python server.py

Or run it in the background so it stays active while you switch to your browser:

    cd ~/apk-workstation
    nohup python -u server.py > server.log 2>&1 &

Open your mobile browser (Chrome, Brave, Firefox, or Via) and navigate to:

    http://127.0.0.1:8080

---

## 7. Generate Your First Signing Keystore & Test Build

1. Open the **Keystores** tab in the web UI.
2. Under **Generate New Keystore**, enter a filename (e.g., `master.jks`), alias, and password (minimum 6 characters), then tap **Generate Keystore**.
3. Switch back to the **Builder** tab:
   - Select **Website URL (`https://`)** and enter `https://example.com` (or upload a `.zip` containing `index.html`).
   - Set **App Name** and **Package ID** (e.g., `com.example.myapp`).
   - Confirm `minSdkVersion` (`21`) and `targetSdkVersion` (`36`).
4. Tap **Compile & Sign APK**.
5. Once the build log finishes, tap **Download APK** and install it on your device.

---

## 8. Back Up Your Keystores & Profiles

Never lose your `.jks` signing keys—Android blocks updates to an existing app if the signing certificate changes. Run the built-in backup utility regularly:

    cd ~/apk-workstation
    ./backup_vault.sh

This creates a timestamped `.tar.gz` archive inside `~/apk-workstation/backups/` and mirrors a copy to `/sdcard/Archives/apk-workstation/`.

---

## 9. Troubleshooting

- **Port `8080` already in use:**
  Stop any existing server instance before starting a new one:

      pkill -f "server.py"

- **`INSTALL_FAILED_UPDATE_INCOMPATIBLE` during APK install:**
  An app with the same **Package ID** is already installed on your phone using a different signing keystore. Uninstall the previous app once, then build future updates using the same `.jks` keystore and a higher `versionCode`.

- **Java heap or memory errors on 4 GB RAM devices:**
  Close background apps before compiling large `.zip` projects so `javac` and `dx` have at least 1.5 GB of free memory.

- **Website top/bottom bars covered on Android 15/16:**
  Ensure **Safe-Area System Bars** is toggled **ON** in the Builder's runtime flags before compiling.
