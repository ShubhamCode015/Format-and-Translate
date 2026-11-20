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

# --- 1. TRANSLATE - Ab MyMemory ka naam bhi thik hai ---
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

        if not text or not text.strip():
            return jsonify({"error": "Text khali hai"}), 400

        # MyMemory ke liye Language ka Poora Naam
        MYMEMORY_MAP = {
            'en': 'en-GB', 'hi': 'hi-IN', 'es': 'es-ES', 'fr': 'fr-FR', 'de': 'de-DE',
            'it': 'it-IT', 'pt': 'pt-PT', 'ru': 'ru-RU', 'ja': 'ja-JP', 'ko': 'ko-KR',
            'zh': 'zh-CN', 'ar': 'ar-SA', 'bn': 'bn-IN', 'ta': 'ta-IN', 'te': 'te-IN',
            'mr': 'mr-IN', 'gu': 'gu-IN', 'pa': 'pa-IN', 'ur': 'ur-PK', 'ne': 'ne-NP',
            'nl': 'nl-NL', 'sv': 'sv-SE', 'pl': 'pl-PL', 'tr': 'tr-TR', 'th': 'th-TH',
            'vi': 'vi-VN', 'id': 'id-ID', 'ms': 'ms-MY', 'kn': 'kn-IN', 'ml': 'ml-IN',
            'or': 'or-IN', 'as': 'as-IN', 'sa': 'sa-IN'
        }
        def to_mymemory(code):
            if '-' in str(code):
                return code
            return MYMEMORY_MAP.get(str(code).lower(), str(code))

        translated = None
        last_error = ""

        # TRY 1: Google
        try:
            from deep_translator import GoogleTranslator
            translated = GoogleTranslator(source='auto', target=target).translate(text)
        except Exception as e:
            last_error = str(e)
            print("Google fail:", e)
            time.sleep(1)

        # TRY 2: MyMemory - Ab sahi naam se
        if not translated:
            try:
                from deep_translator import MyMemoryTranslator
                translated = MyMemoryTranslator(source=to_mymemory(source), target=to_mymemory(target)).translate(text)
            except Exception as e:
                last_error = str(e)
                print("MyMemory fail:", e)

        # TRY 3: LibreTranslate
        if not translated:
            try:
                import requests
                r = requests.post("https://libretranslate.com/translate", data={
                    "q": text, "source": source, "target": target, "format": "text"
                }, timeout=10)
                if r.status_code == 200:
                    translated = r.json().get('translatedText')
            except Exception as e:
                last_error = str(e)

        if not translated:
            return jsonify({"error": "Server Error: Google ne limit laga di hai. 1 Minute ruk ke try karo. " + last_error}), 429

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
