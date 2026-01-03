import os
import shutil
import re
from mcp.server.fastmcp import FastMCP
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from pinecone import Pinecone
import dotenv

# Load environment variables
dotenv.load_dotenv()

# Initialize MCP Server
mcp = FastMCP("MagicFolder Search")

# Configuration
SEARCH_RESULTS_ROOT = os.path.expanduser("~/MagicFolder_Search")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "magic-folder-index")

def get_safe_filename(s):
    """Sanitize string to be used as a filename."""
    s = str(s).strip().replace(' ', '_')
    return re.sub(r'(?u)[^-\w.]', '', s)

@mcp.tool()
def search_magic_folder(query: str) -> str:
    """
    Search for files in the MagicFolder using semantic search and create a folder with the results.
    
    Args:
        query: The natural language search query (e.g., "Show me all invoices from January", "Meeting notes about Python")
    
    Returns:
        A message indicating where the files have been collected.
    """
    google_api_key = os.getenv("GOOGLE_API_KEY")
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    
    if not google_api_key or not pinecone_api_key:
        return "Error: Missing API keys (GOOGLE_API_KEY or PINECONE_API_KEY)."

    try:
        # 1. Generate Embedding for Query
        embeddings_model = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=google_api_key
        )
        query_embedding = embeddings_model.embed_query(query)
        
        # 2. Query Pinecone
        pc = Pinecone(api_key=pinecone_api_key)
        index = pc.Index(PINECONE_INDEX_NAME)
        
        # Fetch top 20 matches
        results = index.query(
            vector=query_embedding,
            top_k=20,
            include_metadata=True
        )
        
        if not results['matches']:
            return f"No matching files found for query: '{query}'"
            
        # 3. Create Result Directory
        folder_name = get_safe_filename(query)[:50] # Limit length
        result_dir = os.path.join(SEARCH_RESULTS_ROOT, folder_name)
        
        # Clean up if exists
        if os.path.exists(result_dir):
            shutil.rmtree(result_dir)
        os.makedirs(result_dir)
        
        # 4. Symlink Files
        count = 0
        files_found = []
        
        for match in results['matches']:
            # Score threshold (optional)
            if match['score'] < 0.4: # Adjust based on testing
                continue
                
            filepath = match['metadata'].get('filepath')
            filename = match['metadata'].get('filename')
            
            if not filepath or not os.path.exists(filepath):
                continue
                
            # Create symlink
            # Handle duplicate filenames in results
            target_link = os.path.join(result_dir, filename)
            if os.path.exists(target_link):
                base, ext = os.path.splitext(filename)
                target_link = os.path.join(result_dir, f"{base}_{count}{ext}")
            
            os.symlink(filepath, target_link)
            files_found.append(filename)
            count += 1
            
        if count == 0:
            return f"Found matches but files were missing or score was too low. (Top match score: {results['matches'][0]['score']})"
            
        return f"Found {count} files matching '{query}'.\nThey are available in: {result_dir}\n\nFiles:\n" + "\n".join(files_found)

    except Exception as e:
        return f"Error performing search: {str(e)}"

if __name__ == "__main__":
    # Run the server
    mcp.run()
