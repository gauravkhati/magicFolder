import sys
import os
import dotenv

# Load environment variables from .env file if present
dotenv.load_dotenv()

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from rag import process_and_store_embeddings

def main():
    print("--- Testing RAG Pipeline ---")
    
    # Check keys
    if not os.getenv("GOOGLE_API_KEY"):
        print("Error: GOOGLE_API_KEY is missing. Please set it in .env or environment.")
        return
    if not os.getenv("PINECONE_API_KEY"):
        print("Error: PINECONE_API_KEY is missing. Please set it in .env or environment.")
        return

    # Sample data simulating files processed by the Brain
    sample_data = [
        {
            "filepath": "/tmp/magic_folder_test_invoice.txt",
            "content": """
            INVOICE #INV-2024-001
            Date: 2024-01-15
            To: Jane Smith
            
            Description              Amount
            -------------------------------
            Consulting Services      $500.00
            Software License         $150.00
            
            Total                    $650.00
            
            Payment due within 30 days.
            """,
            "category": "Invoices"
        },
        {
            "filepath": "/tmp/magic_folder_test_notes.md",
            "content": """
            # Project Alpha Meeting Notes
            Date: 2024-01-20
            Attendees: Alice, Bob, Charlie
            
            ## Key Decisions
            1. We will use Python for the backend.
            2. The database will be PostgreSQL.
            3. Launch date set for Q3 2024.
            
            ## Action Items
            - Alice: Setup repo
            - Bob: Design schema
            """,
            "category": "Notes"
        }
    ]
    
    print(f"Sending {len(sample_data)} sample items to RAG pipeline...")
    print("-" * 50)
    
    try:
        process_and_store_embeddings(sample_data)
        print("-" * 50)
        print("\n[SUCCESS] Test completed. Check your Pinecone dashboard to verify vectors were added.")
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")

if __name__ == "__main__":
    main()
