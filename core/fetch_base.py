import urllib.request
import json
import sys

headers = {'User-Agent': 'ApkWorkstation/1.0'}
repos = [
    'mgks/Android-SmartWebView',
    'theapache64/webview-template',
    'emergent-design/android-webview-template'
]

downloaded = False

# 1. Check known top WebView repositories
for repo in repos:
    try:
        url = f'https://api.github.com/repos/{repo}/releases'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            releases = json.loads(r.read().decode())
            for rel in releases:
                for asset in rel.get('assets', []):
                    if asset.get('name', '').endswith('.apk'):
                        print(f"[*] Found release APK in {repo}: {asset['name']}")
                        urllib.request.urlretrieve(asset['browser_download_url'], 'templates/base.apk')
                        downloaded = True
                        break
                if downloaded:
                    break
    except Exception:
        continue
    if downloaded:
        break

# 2. Fallback: Search GitHub API for active webview templates with releases
if not downloaded:
    try:
        url = 'https://api.github.com/search/repositories?q=android+webview+template&sort=stars'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            items = json.loads(r.read().decode()).get('items', [])
            for item in items[:5]:
                repo_name = item['full_name']
                rel_url = f'https://api.github.com/repos/{repo_name}/releases'
                req_rel = urllib.request.Request(rel_url, headers=headers)
                try:
                    with urllib.request.urlopen(req_rel, timeout=10) as rr:
                        for rel in json.loads(rr.read().decode()):
                            for asset in rel.get('assets', []):
                                if asset.get('name', '').endswith('.apk'):
                                    print(f"[*] Found release APK in {repo_name}: {asset['name']}")
                                    urllib.request.urlretrieve(asset['browser_download_url'], 'templates/base.apk')
                                    downloaded = True
                                    break
                            if downloaded:
                                break
                except Exception:
                    continue
                if downloaded:
                    break
    except Exception:
        pass

if downloaded:
    print("[+] Successfully saved base template to templates/base.apk")
else:
    print("[-] Automated download could not find an active release asset.")
    sys.exit(1)
