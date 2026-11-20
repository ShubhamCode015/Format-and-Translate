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

function downloadTextFile(text, filename) {
  const blob = new Blob([text], {type: "text/plain;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function postFile(url, formData) {
  return fetch(url, { method: "POST", body: formData, cache: "no-store" });
}

// ---------- NAYA: Browser se Translate, Server beech me nahi ----------
function cleanLang(v) {
  v = String(v || "en").toLowerCase().trim();
  const map = {hindi:"hi", english:"en", spanish:"es", french:"fr", german:"de", bengali:"bn", bangla:"bn", tamil:"ta", telugu:"te", marathi:"mr", urdu:"ur", auto:"en", detect:"en"};
  if (map[v]) return map[v];
  if (v.includes("-")) v = v.split("-")[0];
  if (v.includes("_")) v = v.split("_")[0];
  return v;
}

function applyCasual(text, tgt) {
  if (tgt !== "hi") return text;
  const map = {"आप":"तुम", "आपका":"तुम्हारा", "आपकी":"तुम्हारी", "आपको":"तुमको", "कृपया":"please", "धन्यवाद":"thanks", "नमस्ते":"hi", "कैसे हैं":"कैसे हो"};
  let out = text;
  for (const k in map) out = out.split(k).join(map[k]);
  return out;
}

async function translateOneChunk(text, src, tgt) {
  // TRY 1: MyMemory - Browser se
  try {
    const r = await fetch(`https://api.mymemory.translated.net/get?q=${encodeURIComponent(text)}&langpair=${src}|${tgt}&de=test@test.com`);
    if (r.ok) {
      const j = await r.json();
      let t = j.responseData?.translatedText || "";
      if (t && t.toLowerCase() !== text.toLowerCase()) return t;
      if (j.matches) {
        for (let m of j.matches) {
          if (m.translation && m.translation.toLowerCase() !== text.toLowerCase()) return m.translation;
        }
      }
    }
  } catch(e) {}
  // TRY 2: Lingva
  try {
    const r = await fetch(`https://lingva.ml/api/v1/${src}/${tgt}/${encodeURIComponent(text)}`);
    if (r.ok) {
      const j = await r.json();
      if (j.translation) return j.translation;
    }
  } catch(e) {}
  // TRY 3: Google GTX - Browser se
  try {
    const r = await fetch(`https://translate.googleapis.com/translate_a/single?client=gtx&sl=${src}&tl=${tgt}&dt=t&q=${encodeURIComponent(text)}`);
    if (r.ok) {
      const j = await r.json();
      return j[0].map(x => x[0]).join("");
    }
  } catch(e) {}
  throw new Error("Teeno Translator busy hai, 10 sec ruk ke try karo");
}

async function translateBrowser(text, srcRaw, tgtRaw, casual, onProgress) {
  const src = cleanLang(srcRaw);
  const tgt = cleanLang(tgtRaw);
  if (src === tgt) return text;
  // MyMemory ko 500 char se zyada ek baar me nahi dena, tukdo me todo
  const chunks = [];
  let lines = text.split("\n");
  let cur = "";
  for (let line of lines) {
    if ((cur + "\n" + line).length > 450) {
      if (cur) chunks.push(cur);
      cur = line;
    } else {
      cur = cur ? cur + "\n" + line : line;
    }
  }
  if (cur) chunks.push(cur);
  let out = [];
  for (let i = 0; i < chunks.length; i++) {
    if (!chunks[i].trim()) { out.push(chunks[i]); continue; }
    const t = await translateOneChunk(chunks[i], src, tgt);
    out.push(t);
    if (onProgress) onProgress(Math.round(((i+1)/chunks.length)*100));
    // Thoda ruk jao taaki Block na ho
    if (i < chunks.length - 1) await new Promise(r => setTimeout(r, 300));
  }
  let finalText = out.join("\n");
  if (casual) finalText = applyCasual(finalText, tgt);
  return finalText;
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

// ---------- Translate file - AB BROWSER SE ----------
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
    const name = file.name.toLowerCase();
    // TXT, SRT, VTT, ASS - Browser me hi Translate
    if (name.endsWith(".txt") || name.endsWith(".srt") || name.endsWith(".vtt") || name.endsWith(".ass")) {
      const text = await file.text();
      const translated = await translateBrowser(text, src, tgt, casual, (p) => setProgress($("#tfProgress"), p));
      downloadTextFile(translated, file.name.replace(/\.[^.]+$/, "") + "_translated" + file.name.slice(file.name.lastIndexOf(".")));
      setProgress($("#tfProgress"), 100);
      $("#tfMsg").textContent = "Done. Downloaded.";
      return;
    }
    // PDF / DOCX - Abhi Server se (Render pe try karega)
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
    $("#tfMsg").textContent = "Error: " + m;
  } finally {
    $("#translateFileBtn").disabled = false;
  }
});

// ---------- Manual text - AB BROWSER SE ----------
$("#manualBtn").addEventListener("click", async () => {
  const q = $("#manualInput").value.trim();
  if (!q) { $("#manualOut").value = ""; return; }
  $("#manualBtn").disabled = true;
  $("#manualOut").value = "Translating...";
  try {
    const src = $("#srcLang").value;
    const tgt = $("#tgtLang").value;
    const casual = $("#casual").checked;
    const translated = await translateBrowser(q, src, tgt, casual, null);
    $("#manualOut").value = translated;
  } catch (e) {
    const m = (e && e.message) ? e.message : String(e);
    $("#manualOut").value = "Error: " + m;
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
