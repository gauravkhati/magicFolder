import os
from dotenv import load_dotenv
from pinecone import Pinecone

# Load environment variables
load_dotenv()

def delete_all_vectors():
    """
    Delete all vectors from the Pinecone index.
    WARNING: This operation cannot be undone!
    """
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    pinecone_index_name = os.getenv("PINECONE_INDEX_NAME", "magic-folder-index")
    
    if not pinecone_api_key:
        print("[ERROR] PINECONE_API_KEY not set.")
        return
    
    print(f"[WARNING] This will delete ALL vectors from index: {pinecone_index_name}")
    confirm = input("Type 'DELETE' to confirm: ")
    
    if confirm != "DELETE":
        print("[CANCELLED] Operation cancelled.")
        return
    
    try:
        pc = Pinecone(api_key=pinecone_api_key)
        index = pc.Index(pinecone_index_name)
        
        # Delete all vectors by deleting all namespaces
        # For serverless indexes, use delete_all with namespace
        print(f"[DELETING] Removing all vectors from {pinecone_index_name}...")
        index.delete(delete_all=True)
        
        print(f"[SUCCESS] All vectors deleted from {pinecone_index_name}.")
        
    except Exception as e:
        print(f"[ERROR] Failed to delete vectors: {e}")

if __name__ == "__main__":
    delete_all_vectors()
