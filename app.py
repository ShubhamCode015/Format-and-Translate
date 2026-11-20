from flask import Flask, send_from_directory, jsonify, request, send_file
from flask_cors import CORS
import os
import io
import time
from PIL import Image

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

@app.route('/health')
def health():
    return jsonify({"status": "ok", "message": "FileMorph Backend Live Hai!"})

# --- 1. TRANSLATE - Ab Library nahi, Sidha API ---
@app.route('/api/translate-text', methods=['POST'])
def translate_text():
    try:
        data = {}
        if request.is_json:
            data = request.get_json(silent=True) or {}
        if not data:
            data = request.form.to_dict() or {}
        if not data and request.data:
            try:
                import json
                data = json.loads(request.data.decode('utf-8'))
            except:
                data = {"text": request.data.decode('utf-8')}

        text = ""
        for key in ['text','input','content','q','query','sentence','sourceText','originalText','inputText','source_text','toTranslate','data']:
            if data.get(key):
                text = str(data.get(key))
                break
        
        target = data.get('target_lang') or data.get('target') or data.get('to') or data.get('lang') or data.get('targetLanguage') or 'hi'
        source = data.get('source_lang') or data.get('source') or data.get('from') or data.get('sourceLanguage') or 'auto'
        if source == 'auto':
            source = 'en'
        # MyMemory ko 'en-GB' jaisa chahiye, 'en' nahi
        # Isliye short ko long me badlo
        MAP = {'en':'en-GB','hi':'hi-IN','es':'es-ES','fr':'fr-FR','de':'de-DE','it':'it-IT','pt':'pt-PT','ru':'ru-RU','ja':'ja-JP','ko':'ko-KR','zh':'zh-CN','ar':'ar-SA','bn':'bn-IN','ta':'ta-IN','te':'te-IN','mr':'mr-IN','gu':'gu-IN','pa':'pa-IN','ur':'ur-PK','ne':'ne-NP'}
        mm_source = MAP.get(source.lower(), source)
        mm_target = MAP.get(target.lower(), target)

        if not text or not text.strip():
            return jsonify({"error": "Text khali hai"}), 400

        import requests
        translated = None
        last_error = ""

        # TRY 1: MyMemory Direct API - Sabse Pehle, No Limit
        try:
            r = requests.get("https://api.mymemory.translated.net/get", params={
                "q": text,
                "langpair": f"{source}|{target}"
            }, timeout=10)
            if r.status_code == 200:
                j = r.json()
                t = j.get('responseData', {}).get('translatedText', '')
                # Agar MyMemory ne same hi wapas diya to matlab usko nahi aata, agle pe jao
                if t and t.lower() != text.lower():
                    translated = t
                else:
                    # Kabhi-kabhi matches me milta hai
                    matches = j.get('matches', [])
                    for m in matches:
                        if m.get('translation') and m.get('translation').lower() != text.lower():
                            translated = m.get('translation')
                            break
        except Exception as e:
            last_error = str(e)

        # TRY 2: Google ka Free Wala Link (Library wala nahi)
        if not translated:
            try:
                r = requests.get("https://translate.googleapis.com/translate_a/single", params={
                    "client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text
                }, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    j = r.json()
                    translated = "".join([x[0] for x in j[0] if x[0]])
            except Exception as e:
                last_error = str(e)

        # TRY 3: LibreTranslate
        if not translated:
            try:
                r = requests.post("https://libretranslate.com/translate", data={
                    "q": text, "source": source, "target": target, "format": "text"
                }, timeout=10)
                if r.status_code == 200:
                    translated = r.json().get('translatedText')
            except Exception as e:
                last_error = str(e)

        if not translated:
            return jsonify({"error": "Server Error: Abhi teeno Translator busy hai. 1 Minute ruk ke try karo. " + last_error}), 429

# --- 1. TRANSLATE - Final, Language Naam Fix + Detail Error ---
@app.route('/api/translate-text', methods=['POST'])
def translate_text():
    try:
        data = {}
        if request.is_json:
            data = request.get_json(silent=True) or {}
        if not data:
            data = request.form.to_dict() or {}
        if not data and request.data:
            try:
                import json
                data = json.loads(request.data.decode('utf-8'))
            except:
                data = {"text": request.data.decode('utf-8')}

        text = ""
        for key in ['text','input','content','q','query','sentence','sourceText','originalText','inputText','source_text','toTranslate','data']:
            if data.get(key):
                text = str(data.get(key))
                break
        
        raw_target = str(data.get('target_lang') or data.get('target') or data.get('to') or data.get('lang') or data.get('targetLanguage') or 'hi')
        raw_source = str(data.get('source_lang') or data.get('source') or data.get('from') or data.get('sourceLanguage') or 'auto')

        # --- Language Naam -> Code ---
        # Hindi, hindi, HINDI, hi, hi-IN - sabko 'hi' bana dega
        LANG_MAP = {
            'hindi':'hi','english':'en','spanish':'es','french':'fr','german':'de','italian':'it',
            'portuguese':'pt','russian':'ru','japanese':'ja','korean':'ko','chinese':'zh','arabic':'ar',
            'bengali':'bn','bangla':'bn','tamil':'ta','telugu':'te','marathi':'mr','gujarati':'gu',
            'punjabi':'pa','urdu':'ur','nepali':'ne','malayalam':'ml','kannada':'kn','odia':'or',
            'assamese':'as','auto':'en','detect':'en','autodetect':'en'
        }
        def clean_lang(v):
            v = str(v).lower().strip()
            if v in LANG_MAP:
                return LANG_MAP[v]
            if '-' in v:  # hi-IN -> hi
                v = v.split('-')[0]
            if '_' in v:
                v = v.split('_')[0]
            return v[:2] if len(v) > 2 and v not in LANG_MAP else v

        source = clean_lang(raw_source)
        target = clean_lang(raw_target)

        if not text or not text.strip():
            return jsonify({"error": "Text khali hai"}), 400

        import requests
        translated = None
        errors = []

        # TRY 1: MyMemory Direct
        try:
            r = requests.get("https://api.mymemory.translated.net/get", params={
                "q": text, "langpair": f"{source}|{target}", "de": "test@test.com"
            }, timeout=15)
            if r.status_code == 200:
                j = r.json()
                t = j.get('responseData', {}).get('translatedText', '')
                if t and t.lower() != text.lower():
                    translated = t
                else:
                    for m in j.get('matches', []):
                        if m.get('translation') and m.get('translation').lower() != text.lower():
                            translated = m.get('translation')
                            break
                    if not translated:
                        errors.append(f"MyMemory: same text wapas aaya - {j.get('responseStatus')}")
            else:
                errors.append(f"MyMemory: Status {r.status_code} - {r.text[:100]}")
        except Exception as e:
            errors.append(f"MyMemory: {str(e)[:100]}")

        # TRY 2: Lingva - Google ka Free Proxy, No Limit
        if not translated:
            try:
                r = requests.get(f"https://lingva.ml/api/v1/{source}/{target}/{requests.utils.quote(text)}", timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    translated = r.json().get('translation')
                else:
                    errors.append(f"Lingva: Status {r.status_code} - {r.text[:100]}")
            except Exception as e:
                errors.append(f"Lingva: {str(e)[:100]}")

        # TRY 3: Google GTX Direct
        if not translated:
            try:
                r = requests.get("https://translate.googleapis.com/translate_a/single", params={
                    "client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text
                }, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    j = r.json()
                    translated = "".join([x[0] for x in j[0] if x[0]])
                else:
                    errors.append(f"GoogleGTX: Status {r.status_code}")
            except Exception as e:
                errors.append(f"GoogleGTX: {str(e)[:100]}")

        if not translated:
            return jsonify({"error": f"Teeno fail. Source={source} Target={target} | " + " | ".join(errors)}), 429

        return jsonify({"success": True, "translatedText": translated, "translated_text": translated, "target": target})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 2. COMPRESS IMAGE ---
@app.route('/api/compress-image', methods=['POST'])
def compress_image():
    try:
        file = request.files.get('file') or request.files.get('image') or request.files.get('photo')
        if not file:
            return jsonify({"error": "Image file nahi mili"}), 400
        try:
            quality = int(request.form.get('quality', 60))
        except:
            quality = 60
        quality = max(10, min(95, quality))
        img = Image.open(file.stream)
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=quality, optimize=True)
        output.seek(0)
        return send_file(output, mimetype="image/jpeg", as_attachment=True, download_name="compressed.jpg")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 3. CONVERT ---
@app.route('/api/convert', methods=['POST'])
def convert():
    try:
        file = request.files.get('file') or request.files.get('image') or request.files.get('document')
        if not file:
            return jsonify({"error": "File nahi mili"}), 400
        target = (request.form.get('target') or request.form.get('format') or request.form.get('to') or request.form.get('outputFormat') or 'png').lower().replace('.', '')
        filename = file.filename or "file"
        name = os.path.splitext(filename)[0]
        try:
            img = Image.open(file.stream)
            file.stream.seek(0)
            is_image = True
        except:
            is_image = False
        if is_image:
            if target in ['jpg', 'jpeg']:
                fmt = 'JPEG'; out_name = name + '.jpg'; mime = 'image/jpeg'
            elif target in ['webp']:
                fmt = 'WEBP'; out_name = name + '.webp'; mime = 'image/webp'
            else:
                fmt = 'PNG'; out_name = name + '.png'; mime = 'image/png'
            if img.mode in ("RGBA", "LA", "P") and fmt == 'JPEG':
                bg = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = bg
            elif img.mode != "RGB" and fmt == 'JPEG':
                img = img.convert("RGB")
            output = io.BytesIO()
            img.save(output, format=fmt)
            output.seek(0)
            return send_file(output, mimetype=mime, as_attachment=True, download_name=out_name)
        if filename.lower().endswith('.pdf') and target == 'txt':
            import fitz
            doc = fitz.open(stream=file.read(), filetype="pdf")
            txt = ""
            for page in doc:
                txt += page.get_text() + "\n"
            output = io.BytesIO(txt.encode('utf-8'))
            return send_file(output, mimetype="text/plain", as_attachment=True, download_name=name + ".txt")
        return jsonify({"error": "Is file ko " + target + " me convert nahi kar sakte"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def api_fallback(path):
    return jsonify({"error": "API /api/" + path + " abhi bana nahi hai"}), 404

@app.route('/<path:path>')
def static_files(path):
    if os.path.exists(path):
        return send_from_directory('.', path)
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
