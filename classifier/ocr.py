import os

try:
    from PIL import Image
    import pytesseract
    from pdf2image import convert_from_path
except ImportError:
    print("[OCR] Warning: 'Pillow', 'pytesseract', or 'pdf2image' not found. OCR/PDF disabled.")
    Image = None
    pytesseract = None
    convert_from_path = None

def ocr_extract(filepath):
    """
    Extract text from image or PDF using Tesseract OCR.
    """
    if Image is None or pytesseract is None:
        return ""
        
    try:
        text = ""
        if filepath.lower().endswith('.pdf'):
            if convert_from_path is None:
                print(f"[OCR] PDF OCR skipped for {os.path.basename(filepath)}: pdf2image not available")
                return ""
            
            # Convert PDF to images (first 5 pages to save time)
            pages = convert_from_path(filepath, first_page=1, last_page=5)
            for page in pages:
                text += pytesseract.image_to_string(page) + "\n"
        else:
            # Image file
            text = pytesseract.image_to_string(Image.open(filepath))
            
        return text
    except Exception as e:
        print(f"[OCR] OCR failed for {os.path.basename(filepath)}: {e}")
        return ""
