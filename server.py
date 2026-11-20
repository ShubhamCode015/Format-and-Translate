import os, io, uuid, zipfile, subprocess, shutil, tempfile
from pathlib import Path
from flask import Flask, request, send_file, jsonify

import fitz  # PyMuPDF
from PIL import Image
import pillow_heif
pillow_heif.register_heif_opener()
import docx
from docx import Document
import openpyxl
import csv
from deep_translator import GoogleTranslator

try:
    from imageio_ffmpeg import get_ffmpeg_exe
    FFMPEG = get_ffmpeg_exe()
except Exception:
    FFMPEG = None

UPLOAD_DIR = Path(tempfile.gettempdir()) / "filemorph"
UPLOAD_DIR.mkdir(exist_ok=True)

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")

casualMap = {
  "धन्यवाद": "शुक्रिया", "कृपया": "प्लीज़", "क्षमा करें": "सॉरी",
  "अलविदा": "बाय", "नमस्ते": "नमस्ते", "अच्छा": "अच्छा",
  "बहुत": "बहुत", "ठीक है": "ठीक है", "हाँ": "हाँ", "नहीं": "नहीं",
  "क्या": "क्या", "कैसे": "कैसे", "कब": "कब", "कहाँ": "कहाँ",
  "क्यों": "क्यों", "मैं": "मैं", "तुम": "तू", "आप": "तुम",
  "श्रीमान": "भाई", "श्रीमती": "बहन", "बहुत अच्छा": "बहुत बढ़िया",
  "बहुत बढ़िया": "कमाल", "ठीक": "ठीक", "जरूर": "ज़रूर",
  "कोई बात नहीं": "कोई ना", "माफ़ कीजिए": "सॉरी",
  "माफ करें": "सॉरी", "कैसे हैं": "कैसे हो",
  "आप कैसे हैं": "तुम कैसे हो", "मैं ठीक हूँ": "मैं ठीक हूँ",
  "ध्यान रखें": "ध्यान रखना", "फिर मिलेंगे": "फिर मिलते हैं",
  "शुभ रात्रि": "गुड नाइट", "शुभ प्रभात": "गुड मॉर्निंग",
  "बहुत धन्यवाद": "बहुत शुक्रिया", "स्वागत है": "वेलकम",
  "कोई चिंता नहीं": "टेंशन मत लो",
}

def casualize(text):
    out = text
    for k in sorted(casualMap, key=len, reverse=True):
        out = out.replace(k, casualMap[k])
    return out

def workdir():
    d = UPLOAD_DIR / uuid.uuid4().hex
    d.mkdir()
    return d

import urllib.parse, requests as _req

def _gtx_one(q, src, tgt):
    src_code = "auto" if src == "auto" else src
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx"
           "&sl=" + urllib.parse.quote(src_code) + "&tl=" + urllib.parse.quote(tgt)
           + "&dt=t&q=" + urllib.parse.quote(q))
    r = _req.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    data = r.json()
    out = []
    for seg in (data[0] if data and data[0] else []):
        if seg and seg[0]:
            out.append(seg[0])
    return "".join(out) if out else q

def _gtx(q, src, tgt):
    q = str(q)
    if len(q) <= 1500:
        return _gtx_one(q, src, tgt)
    parts = q.split("\n")
    out = []
    for p in parts:
        if not p.strip():
            out.append("")
            continue
        if len(p) <= 1500:
            try:
                out.append(_gtx_one(p, src, tgt))
            except Exception:
                try:
                    out.append(_mymemory(p, src, tgt))
                except Exception:
                    out.append(p)
            continue
        # split long paragraph into chunks
        chunks = []
        chunk = ""
        for word in p.split(" "):
            if len(chunk) + len(word) + 1 > 1500:
                if chunk:
                    chunks.append(chunk)
                chunk = word
            else:
                chunk = (chunk + " " + word).strip()
        if chunk:
            chunks.append(chunk)
        translated = []
        for ch in chunks:
            try:
                translated.append(_gtx_one(ch, src, tgt))
            except Exception:
                try:
                    translated.append(_mymemory(ch, src, tgt))
                except Exception:
                    translated.append(ch)
        out.append(" ".join(translated))
    return "\n".join(out)

def _mymemory(q, src, tgt):
    src_code = "en" if src == "auto" else src
    url = "https://api.mymemory.translated.net/get?q=" + urllib.parse.quote(q) + "&langpair=" + src_code + "|" + tgt
    r = _req.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    # pick best match containing target script when possible
    import re
    matches = data.get("matches") or []
    target_script = None
    if tgt == "hi":
        target_script = re.compile(r"[\u0900-\u097F]")
    best = None
    for m in matches:
        tr = m.get("translation") or ""
        if not tr or tr == q:
            continue
        if target_script and not target_script.search(tr):
            continue
        key = (int(m.get("quality") or 0), int(m.get("usage-count") or 0))
        if best is None or key > best[0]:
            best = (key, tr)
    if best:
        return best[1]
    return (data.get("responseData", {}).get("translatedText")) or q

def translate_text(q, src, tgt, casual=False):
    if not isinstance(q, str):
        q = "" if q is None else str(q)
    if not q.strip():
        return q
    try:
        t = _gtx(q, src, tgt)
    except Exception:
        try:
            from deep_translator import GoogleTranslator
            t = GoogleTranslator(source="auto" if src == "auto" else src, target=tgt).translate(q)
        except Exception:
            try:
                t = _mymemory(q, src, tgt)
            except Exception:
                t = q
    if tgt == "hi" and casual:
        t = casualize(t)
    return t

# ---------- subtitle helpers ----------
def parse_srt(text):
    blocks = text.strip().split("\n\n")
    cues = []
    for b in blocks:
        lines = b.strip().split("\n")
        if len(lines) < 2:
            continue
        idx = 1 if (lines and lines[0].strip().isdigit()) else 0
        m = None
        import re
        m = __import__("re").match(r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})", lines[idx])
        if not m:
            continue
        body = lines[idx+1:]
        cues.append({"start": m.group(1), "end": m.group(2), "text": "\n".join(body)})
    return cues

def cues_to_srt(cues):
    out = []
    for i, c in enumerate(cues, 1):
        s = c["start"].replace(".", ",")
        e = c["end"].replace(".", ",")
        out.append(f"{i}\n{s} --> {e}\n{c['text']}\n")
    return "\n".join(out)

def parse_vtt(text):
    import re
    cleaned = re.sub(r"^WEBVTT[^\n]*\n", "", text)
    blocks = cleaned.strip().split("\n\n")
    cues = []
    for b in blocks:
        lines = b.strip().split("\n")
        if len(lines) < 2:
            continue
        i = 0 if "-->" in lines[0] else 1
        m = re.match(r"(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})", lines[i])
        if not m:
            continue
        cues.append({"start": m.group(1), "end": m.group(2), "text": "\n".join(lines[i+1:])})
    return cues

def cues_to_vtt(cues):
    out = "WEBVTT\n\n"
    for c in cues:
        out += f"{c['start']} --> {c['end']}\n{c['text']}\n\n"
    return out

def parse_ass(text):
    cues = []
    for line in text.split("\n"):
        if not line.startswith("Dialogue:"):
            continue
        rest = line[len("Dialogue:"):].strip()
        parts = rest.split(",")
        if len(parts) < 10:
            continue
        cues.append({"start": parts[1].strip(), "end": parts[2].strip(), "text": ",".join(parts[9:]).strip()})
    return cues

def cues_to_ass(cues):
    out = "[Script Info]\nTitle: Translated\nScriptType: v4.00+\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    for c in cues:
        out += f"Dialogue: 0,{c['start']},{c['end']},Default,,0,0,0,,{c['text']}\n"
    return out

def translate_subtitle(text, ext, src, tgt, casual):
    if ext == "ass":
        cues = parse_ass(text)
        conv_out = cues_to_ass
    elif ext == "vtt":
        cues = parse_vtt(text)
        conv_out = cues_to_vtt
    else:
        cues = parse_srt(text)
        conv_out = cues_to_srt
    for c in cues:
        orig = c["text"].replace("{", "").replace("}", "")
        import re
        orig = re.sub(r"<[^>]*>", "", orig)
        c["text"] = translate_text(orig, src, tgt, casual)
    return conv_out(cues)

def docx_text(path):
    d = Document(path)
    return [p.text for p in d.paragraphs]

def make_docx(paragraphs, path):
    d = Document()
    for p in paragraphs:
        d.add_paragraph(p)
    d.save(path)

def pdf_to_text(path):
    doc = fitz.open(path)
    pages = []
    for pg in doc:
        pages.append(pg.get_text())
    doc.close()
    return pages

_FONT_CANDIDATES = [
    str(Path(__file__).resolve().parent / "fonts" / "NotoSansDevanagari-Regular.ttf"),
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagariUI-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

def _font_candidates():
    out = []
    # built-in latin
    out.append((None, None))  # (fontfile, None) marker for helv
    seen = set()
    for p in _FONT_CANDIDATES:
        if os.path.exists(p) and p not in seen:
            seen.add(p)
            out.append((p, p))
    # discover system fonts (cap)
    for root in ("/usr/share/fonts", str(Path(__file__).resolve().parent / "fonts")):
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            for fn in files:
                if fn.lower().endswith((".ttf", ".otf")):
                    full = os.path.join(dirpath, fn)
                    if full not in seen:
                        seen.add(full)
                        out.append((full, full))
            if len(out) > 80:
                break
    return out

_FONT_SPECS = None
def _font_specs():
    global _FONT_SPECS
    if _FONT_SPECS is not None:
        return _FONT_SPECS
    specs = []
    # built-in helv
    try:
        specs.append({"file": None, "font": fitz.Font("helv"), "name": "helv"})
    except Exception:
        pass
    for item in _font_candidates():
        fpath = item[0]
        if fpath is None:
            continue
        try:
            font = fitz.Font(fontfile=fpath)
            specs.append({"file": fpath, "font": font, "name": f"F{len(specs)}"})
        except Exception:
            continue
    if not specs:
        specs.append({"file": None, "font": fitz.Font("helv"), "name": "helv"})
    _FONT_SPECS = specs
    return specs

def _pick_font(ch):
    specs = _font_specs()
    for spec in specs:
        try:
            if spec["font"].has_glyph(ord(ch)):
                return spec
        except Exception:
            continue
    return specs[0]

def _font_path():
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None

def text_to_pdf(text, path):
    doc = fitz.open()
    specs = _font_specs()
    for chunk in text.split("\f"):
        page = None
        y = 72
        for line in chunk.split("\n"):
            if page is None or y > 770:
                page = doc.new_page()
                y = 72
            segs = [line[i:i+95] for i in range(0, len(line), 95)] or [""]
            for seg in segs:
                # group chars by chosen font
                groups = []
                cur_spec = None
                cur_text = ""
                for ch in seg:
                    sp = _pick_font(ch)
                    if sp is not cur_spec:
                        if cur_text:
                            groups.append((cur_spec, cur_text))
                        cur_text = ch
                        cur_spec = sp
                    else:
                        cur_text += ch
                if cur_text:
                    groups.append((cur_spec, cur_text))
                x = 72
                for sp, run in groups:
                    if sp["file"]:
                        page.insert_text((x, y), run, fontname=sp["name"], fontfile=sp["file"], fontsize=11)
                    else:
                        page.insert_text((x, y), run, fontname=sp["name"], fontsize=11)
                    try:
                        x += sp["font"].text_length(run, fontsize=11)
                    except Exception:
                        x += 6 * len(run)
                y += 14
    if len(doc) == 0:
        doc.new_page()
    doc.save(path)
    doc.close()

# ---------- conversion ----------
def run_ffmpeg(inp, outp):
    if not FFMPEG:
        raise RuntimeError("ffmpeg not available")
    outp = Path(outp)
    cmd = [FFMPEG, "-y", "-i", str(inp)]
    if outp.suffix.lower().lstrip(".") in {"mp3","m4a","wav","ogg","aac","flac"}:
        cmd += ["-vn"]
    cmd.append(str(outp))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(msg[-500:] if msg else f"ffmpeg failed ({r.returncode})")

def convert_file(inp, target, outdir):
    inp = Path(inp)
    ext = inp.suffix.lower().lstrip(".")
    target = target.lower().lstrip(".")
    outp = outdir / f"output.{target}"

    # image <-> image
    img_exts = {"png","jpg","jpeg","webp","gif","bmp","tiff","heic","heif"}
    if ext in img_exts and target in img_exts:
        im = Image.open(inp)
        if target in ("jpg","jpeg"):
            im = im.convert("RGB")
        fmt_map = {"jpg":"JPEG","jpeg":"JPEG","tif":"TIFF","tiff":"TIFF","heic":"HEIF","heif":"HEIF"}
        fmt = fmt_map.get(target, target.upper())
        if fmt == "HEIF" and im.mode not in ("RGB","RGBA"):
            im = im.convert("RGB")
        im.save(outp, format=fmt)
        return outp

    # image -> pdf
    if ext in img_exts and target == "pdf":
        im = Image.open(inp).convert("RGB")
        im.save(outp, "PDF")
        return outp

    # pdf -> image (first page or all pages zipped)
    if ext == "pdf" and target in img_exts:
        doc = fitz.open(inp)
        fmt_map = {"jpg":"JPEG","jpeg":"JPEG","tif":"TIFF","tiff":"TIFF","heic":"HEIF","heif":"HEIF"}
        pil_fmt = fmt_map.get(target, target.upper())
        def _save_pix(pix, path):
            tmp = path.with_name(path.stem + "_tmp.png")
            pix.save(str(tmp))
            im = Image.open(tmp)
            if pil_fmt in ("JPEG","HEIF") and im.mode not in ("RGB","RGBA"):
                im = im.convert("RGB")
            if pil_fmt == "JPEG":
                im = im.convert("RGB")
            im.save(path, format=pil_fmt)
            try:
                tmp.unlink()
            except Exception:
                pass
        if len(doc) == 1:
            pg = doc[0]
            pix = pg.get_pixmap(dpi=150)
            _save_pix(pix, outp)
            doc.close()
            return outp
        # multiple pages -> zip
        zp = outdir / "images.zip"
        with zipfile.ZipFile(zp, "w") as z:
            for i, pg in enumerate(doc):
                pix = pg.get_pixmap(dpi=150)
                img_path = outdir / f"page_{i+1}.{target}"
                _save_pix(pix, img_path)
                z.write(img_path, img_path.name)
        doc.close()
        return zp

    # pdf -> docx
    if ext == "pdf" and target == "docx":
        pages = pdf_to_text(inp)
        paras = []
        for i, t in enumerate(pages):
            paras.append(f"--- Page {i+1} ---")
            for line in t.split("\n"):
                if line.strip():
                    paras.append(line)
        make_docx(paras, outp)
        return outp

    # docx -> pdf
    if ext == "docx" and target == "pdf":
        paras = docx_text(inp)
        text_to_pdf("\n".join(paras), outp)
        return outp

    # docx <-> txt
    if ext == "docx" and target == "txt":
        paras = docx_text(inp)
        outp.write_text("\n".join(paras), encoding="utf-8")
        return outp
    if ext == "txt" and target == "docx":
        lines = inp.read_text(encoding="utf-8", errors="ignore").split("\n")
        make_docx(lines, outp)
        return outp

    # xlsx <-> csv
    if ext == "xlsx" and target == "csv":
        wb = openpyxl.load_workbook(inp)
        ws = wb.active
        with open(outp, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            for row in ws.iter_rows(values_only=True):
                w.writerow(row)
        return outp
    if ext == "csv" and target == "xlsx":
        wb = openpyxl.Workbook()
        ws = wb.active
        with open(inp, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                ws.append(row)
        wb.save(outp)
        return outp

    # media via ffmpeg
    media_exts = {"mp4","mkv","webm","avi","mov","mp3","m4a","wav","ogg","aac","flac"}
    if ext in media_exts and target in media_exts:
        run_ffmpeg(inp, outp)
        return outp
    if ext in media_exts or target in media_exts:
        raise ValueError(f"Unsupported conversion: {ext} -> {target}")

    # pdf -> txt
    if ext == "pdf" and target == "txt":
        pages = pdf_to_text(inp)
        outp.write_text("\n\n".join(pages), encoding="utf-8")
        return outp
    # txt -> pdf
    if ext == "txt" and target == "pdf":
        text_to_pdf(inp.read_text(encoding="utf-8", errors="ignore"), outp)
        return outp

    # same format: just copy
    if ext == target:
        shutil.copyfile(inp, outp)
        return outp

    # generic text-based conversions
    text_exts = {"txt", "pdf", "docx", "csv", "xlsx", "srt", "vtt", "ass"}
    if ext in text_exts and target in text_exts:
        # extract text
        if ext == "pdf":
            text = "\n".join(pdf_to_text(inp))
        elif ext == "docx":
            text = "\n".join(docx_text(inp))
        elif ext == "xlsx":
            wb = openpyxl.load_workbook(inp)
            ws = wb.active
            lines = []
            for row in ws.iter_rows(values_only=True):
                lines.append("\t".join("" if c is None else str(c) for c in row))
            text = "\n".join(lines)
        elif ext in ("csv","srt","vtt","ass"):
            text = inp.read_text(encoding="utf-8", errors="ignore")
        else:
            text = inp.read_text(encoding="utf-8", errors="ignore")
        if target == "txt":
            outp.write_text(text, encoding="utf-8")
        elif target == "pdf":
            text_to_pdf(text, outp)
        elif target == "docx":
            make_docx(text.split("\n"), outp)
        elif target == "csv":
            with open(outp, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                for line in text.split("\n"):
                    w.writerow([line])
        elif target == "xlsx":
            wb = openpyxl.Workbook()
            ws = wb.active
            for line in text.split("\n"):
                ws.append([line])
            wb.save(outp)
        return outp

    raise ValueError(f"Unsupported conversion: {ext} -> {target}")

@app.route("/")
def index():
    return send_file(BASE_DIR / "index.html")

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/<path:p>")
def static_files(p):
    target = (BASE_DIR / p).resolve()
    if not str(target).startswith(str(BASE_DIR)):
        return jsonify({"error": "not found"}), 404
    if not target.is_file():
        return jsonify({"error": "not found"}), 404
    return send_file(target)

@app.route("/api/convert", methods=["POST"])
def api_convert():
    f = request.files.get("file")
    target = request.form.get("target", "").strip()
    if not f or not target:
        return jsonify({"error": "file and target required"}), 400
    d = workdir()
    inp = d / f.filename
    f.save(inp)
    try:
        outp = convert_file(inp, target, d)
        mime = {
            "png":"image/png","jpg":"image/jpeg","jpeg":"image/jpeg","webp":"image/webp",
            "gif":"image/gif","bmp":"image/bmp","pdf":"application/pdf",
            "docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "txt":"text/plain","csv":"text/csv",
            "xlsx":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "mp4":"video/mp4","mkv":"video/x-matroska","webm":"video/webm",
            "avi":"video/x-msvideo","mov":"video/quicktime","mp3":"audio/mpeg",
            "m4a":"audio/mp4","wav":"audio/wav","ogg":"audio/ogg","aac":"audio/aac",
            "flac":"audio/flac","zip":"application/zip",
        }.get(outp.suffix.lstrip(".").lower(), "application/octet-stream")
        return send_file(outp, as_attachment=True, download_name=f.filename.rsplit(".",1)[0]+outp.suffix, mimetype=mime)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/translate-file", methods=["POST"])
def api_translate_file():
    f = request.files.get("file")
    src = request.form.get("src", "auto")
    tgt = request.form.get("tgt", "hi")
    casual = request.form.get("casual", "false") == "true"
    if not f:
        return jsonify({"error": "file required"}), 400
    d = workdir()
    inp = d / f.filename
    f.save(inp)
    ext = inp.suffix.lower().lstrip(".")
    try:
        if ext in ("srt","vtt","ass"):
            text = inp.read_text(encoding="utf-8", errors="ignore")
            out_text = translate_subtitle(text, ext, src, tgt, casual)
            outp = d / f"translated.{ext}"
            outp.write_text(out_text, encoding="utf-8")
            return send_file(outp, as_attachment=True, download_name=inp.stem+"."+tgt+"."+ext, mimetype="text/plain")
        if ext == "txt":
            lines = inp.read_text(encoding="utf-8", errors="ignore").split("\n")
            out_lines = [translate_text(l, src, tgt, casual) if l.strip() else l for l in lines]
            outp = d / "translated.txt"
            outp.write_text("\n".join(out_lines), encoding="utf-8")
            return send_file(outp, as_attachment=True, download_name=inp.stem+"."+tgt+".txt", mimetype="text/plain")
        if ext == "pdf":
            pages = pdf_to_text(inp)
            new_pages = [translate_text(p, src, tgt, casual) for p in pages]
            outp = d / "translated.pdf"
            text_to_pdf("\f".join(new_pages), outp)
            return send_file(outp, as_attachment=True, download_name=inp.stem+"."+tgt+".pdf", mimetype="application/pdf")
        if ext == "docx":
            paras = docx_text(inp)
            new_paras = [translate_text(p, src, tgt, casual) for p in paras]
            outp = d / "translated.docx"
            make_docx(new_paras, outp)
            return send_file(outp, as_attachment=True, download_name=inp.stem+"."+tgt+".docx", mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        return jsonify({"error": "unsupported file type"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/compress-image", methods=["POST"])
def api_compress():
    f = request.files.get("file")
    quality = int(request.form.get("quality", "70"))
    if not f:
        return jsonify({"error": "file required"}), 400
    d = workdir()
    inp = d / f.filename
    f.save(inp)
    try:
        im = Image.open(inp).convert("RGB")
        outp = d / "compressed.jpg"
        im.save(outp, "JPEG", quality=quality, optimize=True)
        return send_file(outp, as_attachment=True, download_name=inp.stem+"_compressed.jpg", mimetype="image/jpeg")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/pdf-merge", methods=["POST"])
def api_pdf_merge():
    files = request.files.getlist("files")
    if len(files) < 2:
        return jsonify({"error": "need at least 2 pdfs"}), 400
    d = workdir()
    out = fitz.open()
    for f in files:
        p = d / f.filename
        f.save(p)
        doc = fitz.open(p)
        out.insert_pdf(doc)
        doc.close()
    outp = d / "merged.pdf"
    out.save(outp)
    out.close()
    return send_file(outp, as_attachment=True, download_name="merged.pdf", mimetype="application/pdf")

@app.route("/api/pdf-split", methods=["POST"])
def api_pdf_split():
    f = request.files.get("file")
    pages = request.form.get("pages", "")
    if not f:
        return jsonify({"error": "file required"}), 400
    d = workdir()
    inp = d / f.filename
    f.save(inp)
    doc = fitz.open(inp)
    out = fitz.open()
    # parse "1-3,5"
    sel = []
    for part in pages.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a,b = part.split("-")
            sel.extend(range(int(a), int(b)+1))
        else:
            sel.append(int(part))
    for pno in sel:
        if 1 <= pno <= len(doc):
            out.insert_pdf(doc, from_page=pno-1, to_page=pno-1)
    outp = d / "split.pdf"
    out.save(outp)
    out.close()
    doc.close()
    return send_file(outp, as_attachment=True, download_name="split.pdf", mimetype="application/pdf")

@app.route("/api/translate-text", methods=["POST"])
def api_translate_text():
    data = request.get_json(force=True)
    q = data.get("q", "")
    src = data.get("src", "auto")
    tgt = data.get("tgt", "hi")
    casual = bool(data.get("casual", False))
    t = translate_text(q, src, tgt, casual)
    return jsonify({"text": t})

@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

@app.route("/api/<path:_>", methods=["OPTIONS"])
def options_handler(_):
    return ("", 204)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
