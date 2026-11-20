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
    return jsonify({"status": "ok"})

@app.route('/api/translate-text', methods=['POST'])
def translate_text():
    # Ab Translate Browser me hota hai, ye sirf backup hai
    return jsonify({"success": True, "translatedText": "Browser se translate karo, Server se nahi", "text": "Browser se translate karo"})

@app.route('/api/compress-image', methods=['POST'])
def compress_image():
    try:
        file = request.files.get('file') or request.files.get('image')
        if not file:
            return jsonify({"error": "Image nahi mili"}), 400
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

@app.route('/api/convert', methods=['POST'])
def convert():
    try:
        file = request.files.get('file') or request.files.get('image') or request.files.get('document')
        if not file:
            return jsonify({"error": "File nahi mili"}), 400
        target = (request.form.get('target') or request.form.get('format') or 'png').lower().replace('.', '')
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
                fmt = 'JPEG'
                out_name = name + '.jpg'
                mime = 'image/jpeg'
            elif target in ['webp']:
                fmt = 'WEBP'
                out_name = name + '.webp'
                mime = 'image/webp'
            else:
                fmt = 'PNG'
                out_name = name + '.png'
                mime = 'image/png'
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

@app.route('/api/translate-file', methods=['POST'])
def translate_file():
    return jsonify({"error": "PDF/DOCX ke liye TXT file use karo, wo Browser se Translate hoga"}), 400

@app.route('/api/pdf-merge', methods=['POST'])
def pdf_merge():
    return jsonify({"error": "PDF Merge abhi bana nahi hai"}), 404

@app.route('/api/pdf-split', methods=['POST'])
def pdf_split():
    return jsonify({"error": "PDF Split abhi bana nahi hai"}), 404

@app.route('/<path:path>')
def static_files(path):
    if os.path.exists(path):
        return send_from_directory('.', path)
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
