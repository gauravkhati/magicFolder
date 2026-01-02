import os
import json
import sys

# Add current directory to sys.path so we can import from llm
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from llm import classifyUsingLLMClassification

def test_llm():
    print("Testing LLM Classification...")
    
    # Sample input data
    test_files = [
        {
            "filepath": "/Users/user/Downloads/invoice_123.pdf",
            "content": "TAX INVOICE\nInvoice No: INV-2023-001\nDate: 2023-01-01\nTotal: $500.00\nBill To: John Doe"
        },
        {
            "filepath": "/Users/user/Documents/resume.docx",
            "content": "John Doe\nSoftware Engineer\nExperience: 5 years in Python, C++\nEducation: BS Computer Science"
        },
        {
            "filepath": "/Users/user/Desktop/random_note.txt",
            "content": "Meeting notes:\n- Discuss project roadmap\n- Fix bugs in login page"
        }
    ]
    
    # The current implementation of llm.py expects a JSON string or list?
    # Based on code reading, it does .replace("{{FILES_JSON}}", input), so it expects a string.
    # But brain.py passes a list. 
    # I will pass a list and let's see if we need to fix llm.py (which we likely do).
    
    # For now, let's try passing the list, as that's how the integration is intended.
    try:
        result = classifyUsingLLMClassification(test_files)
        print("\nClassification Result:")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"\nError during classification: {e}")

if __name__ == "__main__":
    test_llm()
