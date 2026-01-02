import sys
import os

# Add the current directory to sys.path so we can import ocr
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import ocr

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_ocr_real.py <path_to_image_or_pdf>")
        sys.exit(1)

    filepath = sys.argv[1]
    
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.")
        sys.exit(1)

    print(f"--- Testing OCR on: {filepath} ---")
    
    try:
        text = ocr.ocr_extract(filepath)
        
        if text:
            print("\n[SUCCESS] Extracted Text:")
            print("-" * 40)
            print(text)
            print("-" * 40)
        else:
            print("\n[WARNING] No text extracted. (Check if OCR dependencies are installed or if the file is empty/unreadable)")
            
    except Exception as e:
        print(f"\n[ERROR] An exception occurred: {e}")

if __name__ == "__main__":
    main()
