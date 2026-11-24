(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  let activePollTimer = null;
  let cachedProfiles = [];
  let stagedZipBlob = null;
  let stagedZipName = "";
  let stagedIconBlob = null;
  let stagedIconName = "";

  const KS_PASS_STORAGE_KEY = "ws_keystore_passwords_v1";

  function getSavedKsPasswords() {
    try {
      const raw = JSON.parse(localStorage.getItem(KS_PASS_STORAGE_KEY) || "{}");
      return Object.assign({ "master.jks": "password123", "demo.jks": "password123" }, raw);
    } catch (_) {
      return { "master.jks": "password123", "demo.jks": "password123" };
    }
  }

  function saveKsPassword(ksFilename, pass) {
    if (!ksFilename || !pass) return;
    try {
      const map = getSavedKsPasswords();
      map[ksFilename] = pass;
      localStorage.setItem(KS_PASS_STORAGE_KEY, JSON.stringify(map));
    } catch (_) {}
  }

  function syncKeystoreFields(ksFilename, focusIfMissing = false) {
    if (!ksFilename) return;
    const stem = ksFilename.replace(/\.[^.]+$/, "");
    $("keyAlias").value = stem;
    const savedMap = getSavedKsPasswords();
    const hint = $("ksVerifyHint");
    if (savedMap[ksFilename]) {
      $("keyPass").value = savedMap[ksFilename];
      if (hint) {
        hint.textContent = `Loaded alias "${stem}" & saved password`;
        hint.style.color = "var(--accent)";
      }
    } else {
      $("keyPass").value = "";
      $("keyPass").placeholder = `Enter password for ${ksFilename}`;
      if (hint) {
        hint.textContent = `Alias "${stem}" set — enter its password above`;
        hint.style.color = "#fbbf24";
      }
      if (focusIfMissing) $("keyPass").focus();
    }
  }

  function formatCleanBuildError(rawErr) {
    const txt = String(rawErr || "Check console logs.");
    if (txt.includes("keystore password was incorrect")) {
      return "Keystore password was incorrect. Open 'Signing Keystore', enter the right password for your selected .jks file, and tap 'Verify Key' before building.";
    }
    const firstLine = txt.split("\n").map((l) => l.trim()).find((l) => l.startsWith("Error:")) || txt.split("\n")[0];
    return firstLine.length > 220 ? firstLine.slice(0, 220) + "..." : firstLine;
  }

  function escapeHtml(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // --- HARD RELOAD & CACHE CLEANER ---
  async function hardReloadUI() {
    const btn = $("hardReloadBtn");
    if (btn) btn.disabled = true;
    try {
      if ("caches" in window) {
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
      }
      if ("serviceWorker" in navigator) {
        const regs = await navigator.serviceWorker.getRegistrations();
        await Promise.all(regs.map((r) => r.unregister()));
      }
    } catch (_) {}
    window.location.href = window.location.pathname;
  }

  // --- ADAPTIVE NAVIGATION ---
  function switchView(viewName) {
    const isDesktop = window.innerWidth >= 900;
    document.querySelectorAll(".nav-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === viewName);
    });

    const studioView = $("view-studio");
    const buildsView = $("view-builds");
    const keystoresView = $("view-keystores");
    const consoleCol = $("consoleColumn");
    const studioConfig = document.querySelector(".studio-config");

    studioView.classList.remove("active");
    buildsView.classList.remove("active");
    keystoresView.classList.remove("active");
    consoleCol.classList.remove("mobile-visible");

    if (viewName === "studio") {
      studioView.classList.add("active");
      if (studioConfig) studioConfig.style.display = "flex";
    } else if (viewName === "console") {
      studioView.classList.add("active");
      if (!isDesktop) {
        if (studioConfig) studioConfig.style.display = "none";
        consoleCol.classList.add("mobile-visible");
      }
    } else if (viewName === "builds") {
      buildsView.classList.add("active");
      loadBuilds();
    } else if (viewName === "keystores") {
      keystoresView.classList.add("active");
      loadKeystores();
    }
  }

  window.addEventListener("resize", () => {
    if (window.innerWidth >= 900) {
      const cfg = document.querySelector(".studio-config");
      if (cfg) cfg.style.display = "flex";
      const activeBtn = document.querySelector(".nav-item.active");
      if (activeBtn && activeBtn.dataset.view === "console") {
        switchView("studio");
      }
    }
  });

  // --- SAVED APP PROFILES ---
  async function loadProfiles() {
    const bar = $("profilesBar");
    try {
      const res = await fetch("/api/profiles", { cache: "no-store" });
      const data = await res.json();
      cachedProfiles = data.profiles || [];
      if (cachedProfiles.length === 0) {
        bar.innerHTML = '<span class="muted-text">No saved profiles yet — compile an app to save it automatically.</span>';
        return;
      }
      bar.innerHTML = cachedProfiles.map((p) => {
        const nextVc = escapeHtml(p.next_version_code || p.last_version_code || "1");
        const nextVn = escapeHtml(p.next_version_name || p.last_version_name || "1.0.0");
        const pkg = escapeHtml(p.package_id);
        const name = escapeHtml(p.app_name || p.package_id);
        return `
          <div class="profile-chip" data-pkg="${pkg}">
            <span>${name}</span>
            <span class="vc-tag">VC ${nextVc} • v${nextVn}</span>
            <button type="button" class="profile-del" data-del-pkg="${pkg}" title="Remove profile">&times;</button>
          </div>
        `;
      }).join("");

      bar.querySelectorAll(".profile-chip").forEach((chip) => {
        chip.addEventListener("click", (e) => {
          if (e.target.closest(".profile-del")) return;
          applyProfile(chip.dataset.pkg);
          bar.querySelectorAll(".profile-chip").forEach((c) => c.classList.remove("selected"));
          chip.classList.add("selected");
        });
      });

      bar.querySelectorAll(".profile-del").forEach((delBtn) => {
        delBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const pkg = delBtn.dataset.delPkg;
          await fetch(`/api/profiles/${encodeURIComponent(pkg)}`, { method: "DELETE" });
          loadProfiles();
        });
      });
    } catch (err) {
      bar.innerHTML = '<span class="muted-text">Could not load profiles.</span>';
    }
  }

  function applyProfile(pkgId) {
    const p = cachedProfiles.find((item) => item.package_id === pkgId);
    if (!p) return;
    $("appName").value = p.app_name || "";
    $("packageId").value = p.package_id || "";
    $("versionCode").value = p.next_version_code || p.last_version_code || "1";
    $("versionName").value = p.next_version_name || p.last_version_name || "1.0.0";
    $("minSdk").value = p.min_sdk || "21";
    $("targetSdk").value = p.target_sdk || "36";
    $("websiteUrl").value = p.website_url || "";
    $("orientation").value = String(p.orientation ?? 0);

    $("respectSystemBars").checked = p.respect_system_bars !== false;
    $("pullToRefresh").checked = p.pull_to_refresh !== false;
    $("forceOffline").checked = Boolean(p.force_offline);
    $("blockScreenshots").checked = Boolean(p.block_screenshots);
    $("allowCopy").checked = p.allow_copy_paste !== false;
    $("allowZoom").checked = Boolean(p.allow_zoom);
    $("allowCamera").checked = Boolean(p.allow_camera);
    $("allowStorage").checked = Boolean(p.allow_storage);
    $("enableLocation").checked = Boolean(p.enable_location);
    $("enableNotifications").checked = Boolean(p.enable_notifications);

    if (p.keystore) $("keystoreSelect").value = p.keystore;
    if (p.key_alias) $("keyAlias").value = p.key_alias;
    $("localPath").value = p.local_path || "";
  }

  function resetToNewApp() {
    document.querySelectorAll(".profile-chip").forEach((c) => c.classList.remove("selected"));
    $("appName").value = "";
    $("packageId").value = "";
    $("versionCode").value = "1";
    $("versionName").value = "1.0.0";
    $("minSdk").value = "21";
    $("targetSdk").value = "36";
    $("websiteUrl").value = "";
    $("orientation").value = "0";
    $("respectSystemBars").checked = true;
    $("pullToRefresh").checked = true;
    $("forceOffline").checked = true;
    $("blockScreenshots").checked = false;
    $("allowCopy").checked = true;
    $("allowZoom").checked = false;
    $("allowCamera").checked = false;
    $("allowStorage").checked = false;
    $("enableLocation").checked = false;
    $("enableNotifications").checked = false;
    $("localPath").value = "";
    $("projectZip").value = "";
    $("customIcon").value = "";
    stagedZipBlob = null;
    stagedZipName = "";
    stagedIconBlob = null;
    stagedIconName = "";
    $("zipUploadLabel").innerHTML = "<span>Tap to choose web project .ZIP</span>";
    $("iconUploadLabel").innerHTML = "<span>Select square launcher icon (optional)</span>";
    $("appName").focus();
  }

  // --- AUTO-SLUG PACKAGE ID FOR NEW APPS ---
  $("appName").addEventListener("input", () => {
    const selectedChip = document.querySelector(".profile-chip.selected");
    if (selectedChip) return;
    const raw = $("appName").value.trim();
    const slug = raw.toLowerCase().replace(/[^a-z0-9]/g, "");
    if (slug) {
      $("packageId").value = `com.resteus.${slug}`;
    }
  });

  // --- WEBSITE URL AUTO-CONFIG ---
  $("websiteUrl").addEventListener("input", () => {
    const val = $("websiteUrl").value.trim();
    if (val) {
      $("forceOffline").checked = false;
      try {
        const parsed = new URL(val.startsWith("http") ? val : "https://" + val);
        const hostParts = parsed.hostname.replace(/^www\./, "").split(".");
        const cleanHost = hostParts[0] || "webapp";
        if (!$("appName").value.trim() || $("appName").value === "My Custom App") {
          $("appName").value = cleanHost.charAt(0).toUpperCase() + cleanHost.slice(1);
        }
        const selectedChip = document.querySelector(".profile-chip.selected");
        if (!selectedChip && (!$("packageId").value.trim() || $("packageId").value === "com.resteus.store")) {
          const slug = cleanHost.toLowerCase().replace(/[^a-z0-9]/g, "") || "webapp";
          $("packageId").value = `com.resteus.${slug}`;
        }
      } catch (_) {}
    }
  });

  // --- FILE INPUT RAM SNAPSHOT & LABELS ---
  $("projectZip").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) {
      stagedZipBlob = null;
      stagedZipName = "";
      $("zipUploadLabel").innerHTML = "<span>Tap to choose web project .ZIP</span>";
      return;
    }
    try {
      const buf = await file.arrayBuffer();
      stagedZipBlob = new Blob([buf], { type: file.type || "application/zip" });
      stagedZipName = file.name;
    } catch (_) {
      stagedZipBlob = file;
      stagedZipName = file.name;
    }
    $("zipUploadLabel").innerHTML = `<span>Selected: <strong>${escapeHtml(file.name)}</strong> (${(file.size / 1024).toFixed(1)} KB)</span>`;
  });

  $("customIcon").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) {
      stagedIconBlob = null;
      stagedIconName = "";
      $("iconUploadLabel").innerHTML = "<span>Select square launcher icon (optional)</span>";
      return;
    }
    try {
      const buf = await file.arrayBuffer();
      stagedIconBlob = new Blob([buf], { type: file.type || "image/png" });
      stagedIconName = file.name;
    } catch (_) {
      stagedIconBlob = file;
      stagedIconName = file.name;
    }
    $("iconUploadLabel").innerHTML = `<span>Icon: <strong>${escapeHtml(file.name)}</strong></span>`;
  });

  // --- BUILD EXECUTION & LIVE TELEMETRY ---
  function setBuildButtonsDisabled(disabled) {
    document.querySelectorAll(".trigger-build-btn").forEach((b) => {
      b.disabled = disabled;
    });
  }

  async function startBuild() {
    if (activePollTimer) clearInterval(activePollTimer);

    const websiteUrl = $("websiteUrl").value.trim();
    const localPath = $("localPath").value.trim();
    if (!websiteUrl && !stagedZipBlob && !localPath) {
      alert("Please paste a Website URL, select a project .ZIP archive, or enter a local Termux directory path.");
      return;
    }
    if (websiteUrl) {
      $("forceOffline").checked = false;
    }

    if (window.innerWidth < 900) {
      switchView("console");
    }

    setBuildButtonsDisabled(true);
    const statusBox = $("buildStatus");
    const progWrap = $("progressContainer");
    const progBar = $("progressBar");
    const progLabel = $("progressLabel");
    const progPct = $("progressPct");
    const consoleBox = $("consoleBox");

    statusBox.style.display = "none";
    progWrap.style.display = "block";
    progBar.style.width = "10%";
    progLabel.textContent = "Uploading & staging assets...";
    progPct.textContent = "10%";
    $("stageSubtitle").textContent = "Compiling & encrypting APK...";
    consoleBox.value = "[*] Dispatching build job to Termux compiler...\n";

    const fd = new FormData();
    fd.append("app_name", $("appName").value.trim() || "My Custom App");
    fd.append("package_id", $("packageId").value.trim());
    fd.append("version_code", $("versionCode").value.trim() || "1");
    fd.append("version_name", $("versionName").value.trim() || "1.0.0");
    fd.append("min_sdk", $("minSdk").value.trim() || "21");
    fd.append("target_sdk", $("targetSdk").value.trim() || "36");
    fd.append("orientation", $("orientation").value);
    if (websiteUrl) fd.append("website_url", websiteUrl);

    fd.append("respect_system_bars", $("respectSystemBars").checked ? "true" : "false");
    fd.append("pull_to_refresh", $("pullToRefresh").checked ? "true" : "false");
    fd.append("force_offline", $("forceOffline").checked ? "true" : "false");
    fd.append("block_screenshots", $("blockScreenshots").checked ? "true" : "false");
    fd.append("allow_copy_paste", $("allowCopy").checked ? "true" : "false");
    fd.append("allow_zoom", $("allowZoom").checked ? "true" : "false");
    fd.append("allow_camera", $("allowCamera").checked ? "true" : "false");
    fd.append("allow_storage", $("allowStorage").checked ? "true" : "false");
    fd.append("enable_location", $("enableLocation").checked ? "true" : "false");
    fd.append("enable_notifications", $("enableNotifications").checked ? "true" : "false");

    fd.append("keystore", $("keystoreSelect").value || "master.jks");
    fd.append("key_alias", $("keyAlias").value.trim() || "master");
    fd.append("keystore_pass", $("keyPass").value);
    fd.append("key_pass", $("keyPass").value);

    if (stagedZipBlob) fd.append("project_zip", stagedZipBlob, stagedZipName || "project.zip");
    if (localPath) fd.append("local_path", localPath);
    if (stagedIconBlob) fd.append("custom_icon", stagedIconBlob, stagedIconName || "icon.png");

    try {
      // Wake up local socket first so stale keep-alive connections don't drop the POST
      await fetch("/api/builds", { cache: "no-store" }).catch(() => {});
      let res;
      try {
        res = await fetch("/api/build", { method: "POST", body: fd });
      } catch (firstErr) {
        await new Promise((r) => setTimeout(r, 400));
        res = await fetch("/api/build", { method: "POST", body: fd });
      }
      const data = await res.json();
      if (!data.success) {
        throw new Error(data.error || "Build rejected by server.");
      }

      const jobId = data.job_id;
      activePollTimer = setInterval(async () => {
        try {
          const sRes = await fetch(`/api/build/status/${jobId}`, { cache: "no-store" });
          const job = await sRes.json();
          if (job.logs) {
            consoleBox.value = job.logs;
            consoleBox.scrollTop = consoleBox.scrollHeight;
          }
          const pct = job.progress || 15;
          progBar.style.width = `${pct}%`;
          progLabel.textContent = job.stage || "Building...";
          progPct.textContent = `${pct}%`;
          $("stageSubtitle").textContent = job.stage || "Building...";

          if (job.status === "done") {
            saveKsPassword($("keystoreSelect").value, $("keyPass").value);
            clearInterval(activePollTimer);
            activePollTimer = null;
            setBuildButtonsDisabled(false);
            $("stageSubtitle").textContent = "Build completed successfully";
            statusBox.className = "result-banner success";
            statusBox.style.display = "block";
            statusBox.innerHTML = `
              <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <div>
                  <strong>Encrypted APK Ready:</strong><br>
                  <span style="font-size:12px;">${escapeHtml(job.filename)}</span>
                </div>
                <a href="${escapeHtml(job.download_url)}" class="btn-primary" style="width:auto;min-height:38px;padding:6px 14px;text-decoration:none;">
                  Download APK
                </a>
              </div>
            `;
            loadBuilds();
            loadProfiles();
          } else if (job.status === "error") {
            clearInterval(activePollTimer);
            activePollTimer = null;
            setBuildButtonsDisabled(false);
            $("stageSubtitle").textContent = "Build failed";
            statusBox.className = "result-banner error";
            statusBox.style.display = "block";
            statusBox.innerHTML = `<strong>Compilation Error:</strong> ${escapeHtml(formatCleanBuildError(job.error))}`;
          }
        } catch (_) {}
      }, 900);
    } catch (err) {
      setBuildButtonsDisabled(false);
      $("stageSubtitle").textContent = "Build failed";
      statusBox.className = "result-banner error";
      statusBox.style.display = "block";
      statusBox.innerHTML = `<strong>Error:</strong> ${escapeHtml(err.message)}`;
    }
  }

  // --- BUILDS ARCHIVE ---
  async function loadBuilds() {
    const listEl = $("buildsList");
    const badgeEl = $("buildsCountBadge");
    try {
      const res = await fetch("/api/builds", { cache: "no-store" });
      const data = await res.json();
      const builds = (data.builds || []).sort((a, b) => (b.date || "").localeCompare(a.date || ""));
      badgeEl.textContent = String(builds.length);

      if (builds.length === 0) {
        listEl.innerHTML = '<p class="muted-text">No compiled APKs found yet.</p>';
        return;
      }

      listEl.innerHTML = builds.map((b) => {
        const name = escapeHtml(b.name);
        return `
          <div class="list-row">
            <div class="list-row-info">
              <div class="list-row-title">${name}</div>
              <div class="list-row-meta">${escapeHtml(b.size_mb)} MB • ${escapeHtml(b.date)}</div>
            </div>
            <div class="list-row-actions">
              <a href="/builds/${encodeURIComponent(b.name)}" class="btn-ghost btn-sm">Download</a>
              <button type="button" class="btn-ghost btn-sm btn-danger" data-del-apk="${name}">Delete</button>
            </div>
          </div>
        `;
      }).join("");

      listEl.querySelectorAll("[data-del-apk]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const fname = btn.dataset.delApk;
          if (!confirm(`Delete ${fname}?`)) return;
          await fetch(`/api/builds/${encodeURIComponent(fname)}`, { method: "DELETE" });
          loadBuilds();
        });
      });
    } catch (_) {
      listEl.innerHTML = '<p class="muted-text">Failed to load build list.</p>';
    }
  }

  // --- KEYSTORE VAULT ---
  async function loadKeystores() {
    const selectEl = $("keystoreSelect");
    const listEl = $("keystoreList");
    const prevSelected = selectEl.value;
    try {
      const res = await fetch("/api/keystores", { cache: "no-store" });
      const data = await res.json();
      const ksList = data.keystores || [];

      selectEl.innerHTML = ksList.map((k) => {
        const n = escapeHtml(k.name);
        return `<option value="${n}">${n}</option>`;
      }).join("");
      if (prevSelected && ksList.some((k) => k.name === prevSelected)) {
        selectEl.value = prevSelected;
      } else if (ksList.some((k) => k.name === "master.jks")) {
        selectEl.value = "master.jks";
      }
      syncKeystoreFields(selectEl.value, false);

      if (ksList.length === 0) {
        listEl.innerHTML = '<p class="muted-text">No .jks keystores found.</p>';
        return;
      }

      listEl.innerHTML = ksList.map((k) => {
        const name = escapeHtml(k.name);
        const isMaster = k.name === "master.jks";
        return `
          <div class="list-row">
            <div class="list-row-info">
              <div class="list-row-title">${name}</div>
              <div class="list-row-meta">${escapeHtml(k.size_kb)} KB • ${escapeHtml(k.modified)}</div>
            </div>
            <div class="list-row-actions">
              <button type="button" class="btn-ghost btn-sm" data-inspect-ks="${name}">Inspect</button>
              ${isMaster ? "" : `<button type="button" class="btn-ghost btn-sm btn-danger" data-del-ks="${name}">Delete</button>`}
            </div>
          </div>
        `;
      }).join("");

      listEl.querySelectorAll("[data-inspect-ks]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const fname = btn.dataset.inspectKs;
          const pass = $("keyPass").value || "password123";
          $("ksModalTitle").textContent = `Certificate: ${fname}`;
          $("ksModalBody").textContent = "Reading SHA-256 certificate details...";
          $("ksModal").style.display = "flex";
          try {
            const dRes = await fetch(`/api/keystores/${encodeURIComponent(fname)}/details?password=${encodeURIComponent(pass)}`, { cache: "no-store" });
            const dData = await dRes.json();
            $("ksModalBody").textContent = dData.success ? dData.details : (dData.error || "Could not unlock keystore.");
          } catch (err) {
            $("ksModalBody").textContent = err.message;
          }
        });
      });

      listEl.querySelectorAll("[data-del-ks]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const fname = btn.dataset.delKs;
          if (!confirm(`Permanently delete keystore ${fname}?`)) return;
          const delRes = await fetch(`/api/keystores/${encodeURIComponent(fname)}`, { method: "DELETE" });
          const delData = await delRes.json();
          if (!delData.success) alert(delData.error || "Delete failed.");
          loadKeystores();
        });
      });
    } catch (_) {
      listEl.innerHTML = '<p class="muted-text">Failed to load keystores.</p>';
    }
  }

  async function createKeystore() {
    const alias = $("newKsAlias").value.trim();
    const pass = $("newKsPass").value.trim();
    const dname = $("newKsDname").value.trim();
    if (!alias || pass.length < 6) {
      alert("Enter a key alias and a password of at least 6 characters.");
      return;
    }
    const btn = $("createKsBtn");
    btn.disabled = true;
    try {
      const fd = new FormData();
      fd.append("alias", alias);
      fd.append("password", pass);
      fd.append("dname", dname);
      const res = await fetch("/api/keystores", { method: "POST", body: fd });
      const data = await res.json();
      if (!data.success) throw new Error(data.error || "Keystore creation failed.");
      $("newKsAlias").value = "";
      $("newKsPass").value = "";
      saveKsPassword(data.keystore, pass);
      await loadKeystores();
      $("keystoreSelect").value = data.keystore;
      syncKeystoreFields(data.keystore, false);
      alert(`Created ${data.keystore} and selected it for signing.`);
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
    }
  }

  // --- WIRE EVENT LISTENERS ---
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });
  document.querySelectorAll(".trigger-build-btn").forEach((btn) => {
    btn.addEventListener("click", startBuild);
  });
  $("hardReloadBtn").addEventListener("click", hardReloadUI);
  $("resetProfileBtn").addEventListener("click", resetToNewApp);
  $("refreshBuildsBtn").addEventListener("click", loadBuilds);
  $("createKsBtn").addEventListener("click", createKeystore);
  $("keystoreSelect").addEventListener("change", (e) => {
    syncKeystoreFields(e.target.value, true);
  });
  $("togglePassBtn").addEventListener("click", () => {
    const inp = $("keyPass");
    const isHidden = inp.type === "password";
    inp.type = isHidden ? "text" : "password";
    $("togglePassBtn").textContent = isHidden ? "Hide" : "Show";
  });
  $("testKsBtn").addEventListener("click", async () => {
    const ksName = $("keystoreSelect").value;
    const pass = $("keyPass").value;
    const hint = $("ksVerifyHint");
    if (!ksName || !pass) {
      hint.textContent = "Enter a password first to verify";
      hint.style.color = "var(--danger)";
      return;
    }
    hint.textContent = "Verifying keystore...";
    hint.style.color = "var(--text-muted)";
    try {
      const res = await fetch(`/api/keystores/${encodeURIComponent(ksName)}/details?password=${encodeURIComponent(pass)}`, { cache: "no-store" });
      const data = await res.json();
      if (data.success) {
        saveKsPassword(ksName, pass);
        hint.textContent = `Verified & saved password for ${ksName}`;
        hint.style.color = "var(--accent)";
      } else {
        hint.textContent = "Wrong password for " + ksName;
        hint.style.color = "var(--danger)";
      }
    } catch (err) {
      hint.textContent = err.message;
      hint.style.color = "var(--danger)";
    }
  });
  $("closeKsModalBtn").addEventListener("click", () => {
    $("ksModal").style.display = "none";
  });
  $("ksModal").addEventListener("click", (e) => {
    if (e.target === $("ksModal")) $("ksModal").style.display = "none";
  });
  $("clearLogsBtn").addEventListener("click", () => {
    $("consoleBox").value = "";
  });
  $("copyLogsBtn").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("consoleBox").value);
      const btn = $("copyLogsBtn");
      btn.textContent = "Copied";
      setTimeout(() => { btn.textContent = "Copy"; }, 1400);
    } catch (_) {}
  });

  let lastWasDesktop = window.innerWidth >= 900;
  function initAccordions() {
    document.querySelectorAll("details.accordion-card").forEach((el) => {
      if (lastWasDesktop) el.setAttribute("open", "");
      else el.removeAttribute("open");
    });
  }
  window.addEventListener("resize", () => {
    const isDesktop = window.innerWidth >= 900;
    if (isDesktop !== lastWasDesktop) {
      lastWasDesktop = isDesktop;
      initAccordions();
    }
  });
  initAccordions();

  async function loadSdkInfo() {
    const badge = $("sdkApiBadge");
    const info = $("sdkInfoText");
    if (!badge || !info) return;
    try {
      const res = await fetch("/api/sdk", { cache: "no-store" });
      const data = await res.json();
      if (data.exists) {
        badge.textContent = data.api_level || "Installed";
        info.textContent = `Active framework: ${data.path} (${data.size_mb} MB • Updated ${data.modified}). Manifest targetSdkVersion can be set to any future API level (36, 37, 38, 100+).`;
      } else {
        badge.textContent = "Missing";
        info.textContent = "libs/android.jar not found.";
      }
    } catch (_) {
      badge.textContent = "Error";
    }
  }

  $("sdkJarInput")?.addEventListener("change", (e) => {
    const f = e.target.files[0];
    $("sdkJarLabel").innerHTML = f
      ? `<span>Selected: <strong>${escapeHtml(f.name)}</strong> (${(f.size / (1024 * 1024)).toFixed(2)} MB)</span>`
      : "<span>Tap to select updated android.jar</span>";
  });

  $("uploadSdkBtn")?.addEventListener("click", async () => {
    const inp = $("sdkJarInput");
    const f = inp && inp.files[0];
    if (!f) {
      alert("Select an updated android.jar file first.");
      return;
    }
    const btn = $("uploadSdkBtn");
    btn.disabled = true;
    btn.textContent = "Installing SDK...";
    try {
      const fd = new FormData();
      fd.append("sdk_jar", f);
      const res = await fetch("/api/sdk/upload", { method: "POST", body: fd });
      const data = await res.json();
      if (!data.success) throw new Error(data.error || "SDK update failed.");
      inp.value = "";
      $("sdkJarLabel").innerHTML = "<span>Tap to select updated android.jar</span>";
      await loadSdkInfo();
      alert(data.message);
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Install Updated Platform SDK";
    }
  });

  // --- INITIAL BOOT ---
  loadSdkInfo();
  loadKeystores();
  loadBuilds();
  loadProfiles();
})();
