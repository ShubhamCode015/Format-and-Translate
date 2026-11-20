const $ = (s) => document.querySelector(s);

function updateStatus() {
  const el = $("#status");
  if (navigator.onLine) { el.textContent = "Online"; el.classList.remove("offline"); }
  else { el.textContent = "Offline"; el.classList.add("offline"); }
}
window.addEventListener("online", updateStatus);
window.addEventListener("offline", updateStatus);
updateStatus();

document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    $("#tab-" + btn.dataset.tab).classList.add("active");
  });
});

function setProgress(bar, pct) { if (bar) bar.style.width = Math.min(100, Math.max(0, pct)) + "%"; }

async function downloadResponse(res, fallbackName) {
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  // try filename from content-disposition
  let name = fallbackName;
  const cd = res.headers.get("content-disposition");
  if (cd) {
    const m = cd.match(/filename="?([^"]+)"?/);
    if (m) name = m[1];
  }
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function postFile(url, formData) {
  return fetch(url, { method: "POST", body: formData, cache: "no-store" });
}

// ---------- Convert ----------
$("#convertBtn").addEventListener("click", async () => {
  const file = $("#convFile").files[0];
  if (!file) { $("#cMsg").textContent = "Please select a file."; return; }
  const tgt = $("#targetFmt").value;
  $("#convertBtn").disabled = true;
  $("#cMsg").textContent = "Converting...";
  setProgress($("#cProgress"), 10);
  try {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("target", tgt);
    const res = await postFile("/api/convert", fd);
    if (!res.ok) {
      const j = await res.json().catch(()=>({error:res.statusText}));
      throw new Error(j.error || res.statusText);
    }
    setProgress($("#cProgress"), 90);
    await downloadResponse(res, file.name.replace(/\.[^.]+$/, "") + "." + tgt);
    setProgress($("#cProgress"), 100);
    $("#cMsg").textContent = "Done.";
  } catch (e) {
    $("#cMsg").textContent = "Error: " + e.message;
  } finally {
    $("#convertBtn").disabled = false;
  }
});

// ---------- Translate file ----------
$("#translateFileBtn").addEventListener("click", async () => {
  const file = $("#trFile").files[0];
  if (!file) { $("#tfMsg").textContent = "Please select a file."; return; }
  const src = $("#srcLang").value;
  const tgt = $("#tgtLang").value;
  const casual = $("#casual").checked;
  $("#translateFileBtn").disabled = true;
  $("#tfMsg").textContent = "Translating...";
  setProgress($("#tfProgress"), 10);
  try {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("src", src);
    fd.append("tgt", tgt);
    fd.append("casual", casual ? "true" : "false");
    const res = await postFile("/api/translate-file", fd);
    if (!res.ok) {
      const j = await res.json().catch(()=>({error:res.statusText}));
      throw new Error(j.error || res.statusText);
    }
    setProgress($("#tfProgress"), 90);
    await downloadResponse(res, file.name);
    setProgress($("#tfProgress"), 100);
    $("#tfMsg").textContent = "Done. Downloaded.";
  } catch (e) {
    const m = (e && e.message) ? e.message : String(e);
    $("#tfMsg").textContent = "Error: " + (m === "Failed to fetch" ? "Server se connect nahi ho paya. server.py run karo aur http://localhost:5000 use karo." : m);
  } finally {
    $("#translateFileBtn").disabled = false;
  }
});

// ---------- Manual text ----------
$("#manualBtn").addEventListener("click", async () => {
  const q = $("#manualInput").value.trim();
  if (!q) { $("#manualOut").value = ""; return; }
  $("#manualBtn").disabled = true;
  $("#manualOut").value = "Translating...";
  try {
    const src = $("#srcLang").value;
    const tgt = $("#tgtLang").value;
    const casual = $("#casual").checked;
    const res = await fetch("/api/translate-text", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      cache: "no-store",
      body: JSON.stringify({q, src, tgt, casual})
    });
    const j = await res.json();
    if (!res.ok) throw new Error(j.error || res.statusText);
    $("#manualOut").value = j.text;
  } catch (e) {
    const m = (e && e.message) ? e.message : String(e);
    $("#manualOut").value = "Error: " + (m === "Failed to fetch" ? "Server se connect nahi ho paya. server.py run karo aur http://localhost:5000 use karo." : m);
  } finally {
    $("#manualBtn").disabled = false;
  }
});

// ---------- Tools ----------
$("#compBtn").addEventListener("click", async () => {
  const file = $("#compFile").files[0];
  if (!file) { $("#compMsg").textContent = "Select an image."; return; }
  $("#compBtn").disabled = true;
  $("#compMsg").textContent = "Compressing...";
  try {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("quality", $("#compQuality").value);
    const res = await postFile("/api/compress-image", fd);
    if (!res.ok) throw new Error((await res.json()).error || res.statusText);
    await downloadResponse(res, file.name);
    $("#compMsg").textContent = "Done.";
  } catch (e) {
    $("#compMsg").textContent = "Error: " + e.message;
  } finally {
    $("#compBtn").disabled = false;
  }
});

$("#mergeBtn").addEventListener("click", async () => {
  const files = $("#mergeFiles").files;
  if (!files || files.length < 2) { $("#mergeMsg").textContent = "Select at least 2 PDFs."; return; }
  $("#mergeBtn").disabled = true;
  $("#mergeMsg").textContent = "Merging...";
  try {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    const res = await postFile("/api/pdf-merge", fd);
    if (!res.ok) throw new Error((await res.json()).error || res.statusText);
    await downloadResponse(res, "merged.pdf");
    $("#mergeMsg").textContent = "Done.";
  } catch (e) {
    $("#mergeMsg").textContent = "Error: " + e.message;
  } finally {
    $("#mergeBtn").disabled = false;
  }
});

$("#splitBtn").addEventListener("click", async () => {
  const file = $("#splitFile").files[0];
  if (!file) { $("#splitMsg").textContent = "Select a PDF."; return; }
  $("#splitBtn").disabled = true;
  $("#splitMsg").textContent = "Splitting...";
  try {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("pages", $("#splitPages").value);
    const res = await postFile("/api/pdf-split", fd);
    if (!res.ok) throw new Error((await res.json()).error || res.statusText);
    await downloadResponse(res, "split.pdf");
    $("#splitMsg").textContent = "Done.";
  } catch (e) {
    $("#splitMsg").textContent = "Error: " + e.message;
  } finally {
    $("#splitBtn").disabled = false;
  }
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}