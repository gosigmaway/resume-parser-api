from flask import Flask, request, jsonify
import os, re, shutil, tempfile, zipfile, pathlib
import pandas as pd
import gdown
import pdfplumber
from docx import Document

try:
    import textract  # for .doc
except ImportError:
    textract = None

app = Flask(__name__)

@app.route("/process", methods=["POST"])
def process_drive_links():
    data = request.get_json()
    links = data.get("attachment_link")

    if not links:
        return jsonify({"error": "No attachment_link provided"}), 400

    # Support single string or list of links
    if isinstance(links, str):
        links = [links]

    output_rows = []
    root_dl = tempfile.mkdtemp(prefix='resume_dl_')
    print('Download folder:', root_dl)

    for idx, link in enumerate(links):
        print(f'Processing link {idx + 1}/{len(links)}: {link}')
        m = re.search(r'/d/([A-Za-z0-9_-]+)', link) or re.search(r'/folders/([A-Za-z0-9_-]+)', link)
        if not m:
            print('Could not parse id from', link)
            continue

        file_or_folder_id = m.group(1)
        out_dir = os.path.join(root_dl, file_or_folder_id)
        os.makedirs(out_dir, exist_ok=True)

        try:
            gdown.download_folder(url=link, output=out_dir, quiet=True)
        except Exception as e:
            print('Folder download failed, trying file...', e)
            try:
                gdown.download(id=file_or_folder_id, output=os.path.join(out_dir, 'file'), quiet=True)
            except Exception as e2:
                print('Download failed for', link, e2)
                continue

        # Unzip files if needed
        for path in pathlib.Path(out_dir).rglob('*'):
            if path.is_dir():
                continue
            if path.suffix.lower() == '.zip':
                unzip_dir = path.parent / (path.stem + '_unzipped')
                os.makedirs(unzip_dir, exist_ok=True)
                with zipfile.ZipFile(path, 'r') as zf:
                    zf.extractall(unzip_dir)
                path.unlink()

        # Parse files
        for file_path in pathlib.Path(out_dir).rglob('*'):
            if file_path.is_dir():
                continue
            ext = file_path.suffix.lower()
            if ext not in ['.pdf', '.docx', '.doc']:
                continue
            try:
                if ext == '.pdf':
                    with pdfplumber.open(str(file_path)) as pdf:
                        text = ''.join(page.extract_text() or '' for page in pdf.pages)
                elif ext == '.docx':
                    doc = Document(str(file_path))
                    text = '\n'.join(p.text for p in doc.paragraphs)
                elif ext == '.doc':
                    if textract is None:
                        print('textract not installed; skipping .doc file', file_path)
                        continue
                    text = textract.process(str(file_path)).decode('utf-8', errors='ignore')
                output_rows.append({
                    "source_file": str(file_path),
                    "resume_text": text[:10000]  # limit to 10k chars
                })
            except Exception as e:
                print('Failed to read', file_path, e)

    return jsonify({"resumes": output_rows})


@app.route("/", methods=["GET"])
def home():
    return "Resume parser is running. Use POST /process with {attachment_link}", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
