from flask import Flask, request, jsonify
import os, re, tempfile, pathlib, zipfile
import fitz  # PyMuPDF
from docx import Document
import gdown
import magic

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
        print(file_path)
        if file_path.is_dir():
            continue

        ext = ""

        # Detect file type using magic (MIME type)
        mime = magic.from_file(str(file_path), mime=True)
        print(f"Detected MIME type: {mime}")

        # Map MIME type to extension
        if mime == "application/pdf":
            ext = ".pdf"
        elif mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            ext = ".docx"
        elif mime in ["application/msword", "application/vnd.ms-word.document.macroenabled.12"]:
            ext = ".doc"
        else:
            print(f"Unsupported MIME type: {mime}")

        print(f"Processing file: {file_path} with extension: {ext}")
        try:
            if ext == ".pdf":
                doc = fitz.open(str(file_path))
                print("="*30, "PDF DEBUG", "="*30)
                print(f"Opened PDF: {file_path}, Pages: {doc.page_count}")

                resume_text = ""
                for i, page in enumerate(doc):
                    blocks = page.get_text("dict")["blocks"]
                    for block in blocks:
                        if "lines" in block:
                            for line in block["lines"]:
                                for span in line["spans"]:
                                    resume_text += span["text"] + " "
                doc.close()
                print(f"Total extracted text length: {len(resume_text)} characters")
                print("="*75)
            elif ext == ".docx":
                doc = Document(str(file_path))
                resume_text = '\n'.join(p.text for p in doc.paragraphs)
            elif ext == ".doc" and textract:
                resume_text = textract.process(str(file_path)).decode(
                    "utf-8", errors="ignore")
            else:
                continue

            if resume_text.strip():
                break  # Stop after first valid file
        except Exception as e:
            print(f"Failed to read {file_path}: {e}")
            continue

    return jsonify({"resume_text": resume_text})


@app.route("/", methods=["GET"])
def home():
    return "Resume parser is running. Use POST /process with {attachment_link}", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
