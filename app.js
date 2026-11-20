const $ = (s) => document.querySelector(s);
let ffmpegInstance = null;
let ffmpegLoading = false;

const casualMap = {
  "धन्यवाद": "शुक्रिया",
  "कृपया": "प्लीज़",
  "क्षमा करें": "सॉरी",
  "अलविदा": "बाय",
  "नमस्ते": "नमस्ते",
  "अच्छा": "अच्छा",
  "बहुत": "बहुत",
  "ठीक है": "ठीक है",
  "हाँ": "हाँ",
  "नहीं": "नहीं",
  "क्या": "क्या",
  "कैसे": "कैसे",
  "कब": "कब",
  "कहाँ": "कहाँ",
  "क्यों": "क्यों",
  "मैं": "मैं",
  "तुम": "तू",
  "आप": "तुम",
  "श्रीमान": "भाई",
  "श्रीमती": "बहन",
  "बहुत अच्छा": "बहुत बढ़िया",
  "बहुत बढ़िया": "कमाल",
  "ठीक": "ठीक",
  "जरूर": "ज़रूर",
  "कोई बात नहीं": "कोई ना",
  "माफ़ कीजिए": "सॉरी",
  "माफ करें": "सॉरी",
  "कैसे हैं": "कैसे हो",
  "आप कैसे हैं": "तुम कैसे हो",
  "मैं ठीक हूँ": "मैं ठीक हूँ",
  "ध्यान रखें": "ध्यान रखना",
  "फिर मिलेंगे": "फिर मिलते हैं",
  "शुभ रात्रि": "गुड नाइट",
  "शुभ प्रभात": "गुड मॉर्निंग",
  "जल्दी": "जल्दी",
  "बहुत धन्यवाद": "बहुत शुक्रिया",
  "स्वागत है": "वेलकम",
  "कोई चिंता नहीं": "टेंशन मत लो"
};

function casualize(text) {
  let out = text;
  const keys = Object.keys(casualMap).sort((a, b) => b.length - a.length);
  for (const k of keys) {
    out = out.split(k).join(casualMap[k]);
  }
  return out;
}

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

function setProgress(bar, pct) { bar.style.width = Math.min(100, Math.max(0, pct)) + "%"; }

function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------- Subtitle parsing ----------
function parseSRT(text) {
  const blocks = text.trim().split(/\n\s*\n/);
  const cues = [];
  for (const b of blocks) {
    const lines = b.trim().split("\n");
    if (lines.length < 2) continue;
    let idx = 0;
    if (/^\d+$/.test(lines[0].trim())) idx = 1;
    const timeLine = lines[idx];
    const m = timeLine.match(/(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})/);
    if (!m) continue;
    const start = m[1], end = m[2];
    const body = lines.slice(idx + 1).join("\n");
    cues.push({ start, end, text: body });
  }
  return cues;
}

function parseVTT(text) {
  const cleaned = text.replace(/^WEBVTT[^\n]*\n/, "");
  const blocks = cleaned.trim().split(/\n\s*\n/);
  const cues = [];
  for (const b of blocks) {
    const lines = b.trim().split("\n");
    if (lines.length < 2) continue;
    let i = 0;
    if (!lines[0].includes("-->")) i = 1;
    const m = lines[i].match(/(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})/);
    if (!m) continue;
    const body = lines.slice(i + 1).join("\n");
    cues.push({ start: m[1], end: m[2], text: body });
  }
  return cues;
}

function parseASS(text) {
  const cues = [];
  for (const line of text.split("\n")) {
    if (!line.startsWith("Dialogue:")) continue;
    const rest = line.slice("Dialogue:".length).trim();
    const parts = rest.split(",");
    // first 9 fields then text
    if (parts.length < 10) continue;
    const start = parts[1].trim();
    const end = parts[2].trim();
    const txt = parts.slice(9).join(",").trim();
    cues.push({ start, end, text: txt });
  }
  return cues;
}

function detectFormat(name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  return ext;
}

function cuesToSRT(cues) {
  return cues.map((c, i) => {
    const s = c.start.replace(".", ",");
    const e = c.end.replace(".", ",");
    return `${i + 1}\n${s} --> ${e}\n${c.text}\n`;
  }).join("\n");
}

function cuesToVTT(cues) {
  let out = "WEBVTT\n\n";
  for (const c of cues) {
    out += `${c.start} --> ${c.end}\n${c.text}\n\n`;
  }
  return out;
}

function cuesToASS(cues) {
  let out = "[Script Info]\nTitle: Translated\nScriptType: v4.00+\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n";
  for (const c of cues) {
    out += `Dialogue: 0,${c.start},${c.end},Default,,0,0,0,,${c.text}\n`;
  }
  return out;
}

async function translateChunk(q, src, tgt) {
  if (!q.trim()) return q;
  const srcCode = src === "auto" ? "en" : src;
  const url = `https://api.mymemory.translated.net/get?q=${encodeURIComponent(q)}&langpair=${srcCode}|${tgt}`;
  let res;
  for (let attempt = 0; attempt < 3; attempt++) {
    try { res = await fetch(url); if (res.ok) break; } catch (e) {}
    await sleep(300);
  }
  if (!res || !res.ok) throw new Error("Translation request failed");
  const data = await res.json();
  let t = (data.responseData && data.responseData.translatedText) || q;
  // MyMemory sometimes returns uppercase; keep
  if (tgt === "hi" && $("#casual").checked) t = casualize(t);
  return t;
}

async function translateText(q, src, tgt) {
  if (!q.trim()) return q;
  if (q.length <= 400) return translateChunk(q, src, tgt);
  // split into sentences for long text
  const parts = q.split(/(?<=[.!?。！？])\s+/);
  const out = [];
  for (const part of parts) {
    if (!part.trim()) { out.push(part); continue; }
    try { out.push(await translateChunk(part, src, tgt)); }
    catch (e) { out.push(part); }
    await sleep(80);
  }
  return out.join(" ");
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

$("#translateBtn").addEventListener("click", async () => {
  const file = $("#subFile").files[0];
  if (!file) { $("#tMsg").textContent = "Please select a subtitle file."; return; }
  const src = $("#srcLang").value;
  const tgt = $("#tgtLang").value;
  $("#translateBtn").disabled = true;
  $("#tMsg").textContent = "Reading file...";
  setProgress($("#tProgress"), 0);
  try {
    const text = await file.text();
    const ext = detectFormat(file.name);
    let cues = [];
    if (ext === "ass") cues = parseASS(text);
    else if (ext === "vtt") cues = parseVTT(text);
    else cues = parseSRT(text);
    if (cues.length === 0) { $("#tMsg").textContent = "No cues found."; $("#translateBtn").disabled = false; return; }

    const total = cues.length;
    for (let i = 0; i < cues.length; i++) {
      const original = cues[i].text.replace(/\{[^}]*\}/g, "").replace(/<[^>]*>/g, "");
      try {
        const tr = await translateText(original, src, tgt);
        cues[i].text = tr;
      } catch (e) {
        cues[i].text = original;
      }
      setProgress($("#tProgress"), ((i + 1) / total) * 100);
      $("#tMsg").textContent = `Translating ${i + 1}/${total}...`;
      await sleep(80);
    }

    let out = "";
    let outName = file.name.replace(/\.[^.]+$/, "") + "." + tgt + "." + ext;
    if (ext === "ass") out = cuesToASS(cues);
    else if (ext === "vtt") out = cuesToVTT(cues);
    else out = cuesToSRT(cues);

    $("#preview").value = out.slice(0, 4000);
    downloadBlob(new Blob([out], { type: "text/plain;charset=utf-8" }), outName);
    $("#tMsg").textContent = `Done. Downloaded ${outName}`;
  } catch (e) {
    $("#tMsg").textContent = "Error: " + e.message;
  } finally {
    $("#translateBtn").disabled = false;
  }
});

$("#manualBtn").addEventListener("click", async () => {
  const q = $("#manualInput").value.trim();
  if (!q) { $("#manualOut").value = ""; return; }
  $("#manualBtn").disabled = true;
  $("#manualOut").value = "Translating...";
  try {
    const src = $("#srcLang").value;
    const tgt = $("#tgtLang").value;
    // split into chunks by newline to handle long text
    const lines = q.split("\n");
    const outLines = [];
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (!line.trim()) { outLines.push(""); continue; }
      try {
        const tr = await translateText(line, src, tgt);
        outLines.push(tr);
      } catch (e) {
        outLines.push(line);
      }
      await sleep(100);
    }
    $("#manualOut").value = outLines.join("\n");
  } catch (e) {
    $("#manualOut").value = "Error: " + e.message;
  } finally {
    $("#manualBtn").disabled = false;
  }
});

// ---------- Conversion ----------
async function loadFFmpeg() {
  if (ffmpegInstance) return ffmpegInstance;
  if (ffmpegLoading) {
    while (ffmpegLoading) await sleep(200);
    return ffmpegInstance;
  }
  ffmpegLoading = true;
  try {
    const FFmpegCtor = (window.FFmpeg && window.FFmpeg.FFmpeg) ? window.FFmpeg.FFmpeg : (window.FFmpeg || null);
    if (!FFmpegCtor) throw new Error("ffmpeg.js not loaded");
    const ffmpeg = new FFmpegCtor();
    const { fetchFile, toBlobURL } = window.FFmpegUtil || {};
    if (!fetchFile || !toBlobURL) throw new Error("ffmpeg util not loaded");
    const baseURL = "https://cdn.jsdelivr.net/npm/@ffmpeg/core@0.12.6/dist/umd";
    await ffmpeg.load({
      coreURL: await toBlobURL(`${baseURL}/ffmpeg-core.js`, "text/javascript"),
      wasmURL: await toBlobURL(`${baseURL}/ffmpeg-core.wasm`, "application/wasm"),
      workerURL: await toBlobURL(`${baseURL}/ffmpeg-core.worker.js`, "text/javascript")
    });
    ffmpegInstance = { ffmpeg, fetchFile };
    return ffmpegInstance;
  } finally {
    ffmpegLoading = false;
  }
}

$("#convertBtn").addEventListener("click", async () => {
  const file = $("#convFile").files[0];
  if (!file) { $("#cMsg").textContent = "Please select a file."; return; }
  const tgt = $("#targetFmt").value;
  $("#convertBtn").disabled = true;
  $("#cMsg").textContent = "Loading converter...";
  setProgress($("#cProgress"), 5);
  try {
    const { ffmpeg, fetchFile } = await loadFFmpeg();
    setProgress($("#cProgress"), 15);
    const inName = "input." + (file.name.split(".").pop() || "bin");
    const outName = "output." + tgt;
    await ffmpeg.writeFile(inName, await fetchFile(file));
    setProgress($("#cProgress"), 30);
    $("#cMsg").textContent = "Converting...";
    await ffmpeg.exec(["-i", inName, "-y", outName]);
    setProgress($("#cProgress"), 80);
    const data = await ffmpeg.readFile(outName);
    const mime = guessMime(tgt);
    const blob = new Blob([data.buffer], { type: mime });
    downloadBlob(blob, file.name.replace(/\.[^.]+$/, "") + "." + tgt);
    setProgress($("#cProgress"), 100);
    $("#cMsg").textContent = "Done.";
    try { await ffmpeg.deleteFile(inName); await ffmpeg.deleteFile(outName); } catch (e) {}
  } catch (e) {
    $("#cMsg").textContent = "Error: " + e.message;
  } finally {
    $("#convertBtn").disabled = false;
  }
});

function guessMime(ext) {
  const map = {
    mp4: "video/mp4", mkv: "video/x-matroska", webm: "video/webm", avi: "video/x-msvideo",
    mov: "video/quicktime", mp3: "audio/mpeg", m4a: "audio/mp4", wav: "audio/wav",
    ogg: "audio/ogg", aac: "audio/aac", flac: "audio/flac", png: "image/png",
    jpg: "image/jpeg", webp: "image/webp", gif: "image/gif", bmp: "image/bmp"
  };
  return map[ext] || "application/octet-stream";
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
