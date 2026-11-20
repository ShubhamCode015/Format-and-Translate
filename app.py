from flask import Flask, send_from_directory, jsonify, request, send_file
from flask_cors import CORS
import os
import io
from PIL import Image

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

@app.route('/health')
def health():
    return jsonify({"status": "ok", "message": "FileMorph Backend Live Hai!"})

# --- 1. TRANSLATE ---
@app.route('/api/translate-text', methods=['POST'])
def translate_text():
    try:
        data = request.get_json(force=True, silent=True) or {}
        text = data.get('text', '') or data.get('input', '') or ''
        target = data.get('target_lang') or data.get('target') or data.get('to') or data.get('lang') or 'hi'
        source = data.get('source_lang') or data.get('source') or data.get('from') or 'auto'
        if not text.strip():
            return jsonify({"error": "Text khali hai"}), 400
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source=source, target=target).translate(text)
        return jsonify({"success": True, "translatedText": translated, "translated_text": translated, "target": target})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 2. COMPRESS IMAGE ---
@app.route('/api/compress-image', methods=['POST'])
def compress_image():
    try:
        # File kisi bhi naam se aaye - file, image, photo
        file = request.files.get('file') or request.files.get('image') or request.files.get('photo')
        if not file:
            return jsonify({"error": "Image file nahi mili"}), 400

        # Quality Frontend se aaye to wahi, nahi to 60%
        try:
            quality = int(request.form.get('quality', 60))
        except:
            quality = 60
        if quality < 10: quality = 10
        if quality > 95: quality = 95

        img = Image.open(file.stream)
        # PNG me transparency hoti hai, JPEG me nahi - isliye white background
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

        # Frontend ko file bhej rahe hai
        return send_file(output, mimetype="image/jpeg", as_attachment=True, download_name="compressed.jpg")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Baaki API ke liye
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
