from flask import Flask, request, jsonify
import os, re, tempfile, pathlib, zipfile
import pdfplumber
from docx import Document
import gdown

try:
    import textract
except ImportError:
    textract = None

app = Flask(__name__)

@app.route("/process", methods=["POST"])
def process_drive_file():
    data = request.get_json()
    link = data.get("attachment_link")

    if not link:
        return jsonify({"error": "No attachment_link provided"}), 400

    # Extract file ID from the Google Drive file URL
    match = re.search(r"/d/([A-Za-z0-9_-]+)", link)
    if not match:
        return jsonify({"error": "Invalid Google Drive file link"}), 400

    file_id = match.group(1)

    download_dir = tempfile.mkdtemp(prefix='resume_dl_')
    output_path = os.path.join(download_dir, 'resume_file')

    try:
        gdown.download(id=file_id, output=output_path, quiet=True)
    except Exception as e:
        return jsonify({"error": f"Download failed: {str(e)}"}), 500

    # Debug Log
    print("Downloaded file path:", output_path)
    print("File exists:", os.path.exists(output_path))
    print("File size (KB):", os.path.getsize(output_path) / 1024)

    with open(output_path, 'rb') as f:
        head = f.read(512)
        print("First 512 bytes of file:", head[:512])

    # Handle zip extraction
    if output_path.endswith(".zip"):
        with zipfile.ZipFile(output_path, 'r') as zf:
            zf.extractall(download_dir)
        os.remove(output_path)

    # Find the first valid resume file
    resume_text = ""
    for file_path in pathlib.Path(download_dir).rglob('*'):
        if file_path.is_dir():
            continue

        ext = file_path.suffix.lower()
        try:
            if ext == ".pdf":
                with pdfplumber.open(str(file_path)) as pdf:
                    resume_text = ''.join(page.extract_text() or '' for page in pdf.pages)
            elif ext == ".docx":
                doc = Document(str(file_path))
                resume_text = '\n'.join(p.text for p in doc.paragraphs)
            elif ext == ".doc" and textract:
                resume_text = textract.process(str(file_path)).decode("utf-8", errors="ignore")
            else:
                continue

            if resume_text.strip():
                break  # Stop after first valid file
        except Exception as e:
            print(f"Failed to read {file_path}: {e}")
            continue

    return jsonify({
        "resume_text": resume_text
    })


@app.route("/", methods=["GET"])
def home():
    return "Resume parser is running. Use POST /process with {attachment_link}", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
