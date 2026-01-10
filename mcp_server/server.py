 #todo: Need to add more mcp servers from other projects. 
import os
import shutil
import re
import json
import time
from mcp.server.fastmcp import FastMCP
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from pinecone import Pinecone
import dotenv

# Load environment variables
dotenv.load_dotenv()

# Initialize MCP Server
mcp = FastMCP("MagicFolder Search")

# Configuration
SEARCH_RESULTS_ROOT = os.path.expanduser("~/MagicFolder_Search")
CONTEXT_FILE_PATH = os.path.join(SEARCH_RESULTS_ROOT, "last_search_context.json")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "magic-folder-index")

def save_search_context(results):
    """Save search results to a JSON file for persistence."""
    try:
        if not os.path.exists(SEARCH_RESULTS_ROOT):
            os.makedirs(SEARCH_RESULTS_ROOT)
        
        # Ensure results are serialized as dicts, not arbitrary objects
        serializable_results = []
        for item in results:
            if hasattr(item, "to_dict"):
                serializable_results.append(item.to_dict())
            elif isinstance(item, dict):
                serializable_results.append(item)
            else:
                try:
                    serializable_results.append(dict(item))
                except:
                    continue 

        with open(CONTEXT_FILE_PATH, 'w') as f:
            json.dump(serializable_results, f, default=str, indent=2)
    except Exception as e:
        print(f"Error saving context: {e}")

def load_search_context():
    """Load search results from the persistence file."""
    if not os.path.exists(CONTEXT_FILE_PATH):
        return []
    try:
        with open(CONTEXT_FILE_PATH, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
            return []
    except Exception:
        return []

CATEGORY_METADATA_SCHEMA = {
    "Invoices": {
        "invoice_number": "string",
        "total_amount": "number",
        "invoice_date": "string",
        "sender_name": "string",
        "sender_address": "string",
        "order_id": "string",
        "gst_number": "string"
    },
    "TrainTickets": {
        "pnr_number": "string",
        "train_number": "string",
        "journey_date": "string",
        "from_station": "string",
        "to_station": "string",
        "passenger_names": "list",
        "booking_date": "string"
    },
    "IDProofs": {
        "document_type": "string",
        "id_number": "string",
        "name": "string",
        "date_of_birth": "string",
        "issue_date": "string",
        "expiry_date": "string"
    },
    "Credentials": {
        "username": "string",
        "email": "string",
        "service_name": "string",
        "api_key_name": "string",
        "creation_date": "string"
    },
    "Notes": {
        "main_topic": "string",
        "key_points": "list",
        "date_created": "string",
        "tags": "list",
        "mentioned_people": "list"
    },
    "Resume": {
        "candidate_name": "string",
        "email": "string",
        "phone": "string",
        "experience_years": "number",
        "key_skills": "list",
        "education": "string"
    },
    "Screenshots": {
        "captured_date": "string",
        "application_name": "string",
        "main_content": "string"
    },
    "Misc": {
        "main_topic": "string",
        "key_entities": "list",
        "date_if_any": "string"
    }
}

FILTER_EXTRACTION_PROMPT = """
You are an expert search query parser for a vector database.
You have the following metadata schema for different categories:
{schema}

User Query: "{query}"

Your task is to:
1. Identify the likely category (e.g., Invoices, TrainTickets, etc.) based on the query.
2. Extract specific metadata filters (like amount > 30000, date = 2023, etc.) using MongoDB-style operators ($gt, $lt, $eq, $in, $gte, $lte).
3. Formulate a semantic search query string for the remaining context.

Return ONLY a valid JSON object with this structure:
{{
  "semantic_query": "search term",
  "pinecone_filter": {{
      "category": "DetectedCategory",
      "field_name": {{ "$operator": value }}
  }}
}}

Example:
Query: "invoices > 30000"
Result:
{{
  "semantic_query": "invoices high amount",
  "pinecone_filter": {{
      "category": "Invoices",
      "total_amount": {{ "$gt": 30000 }}
  }}
}}

If no specific filter can be extracted, return null for "pinecone_filter".
"""

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
        embeddings_model = GoogleGenerativeAIEmbeddings(
            model="gemini-embedding-001",
            google_api_key=google_api_key,
            output_dimensionality=768
        )
        query_embedding = embeddings_model.embed_query(query)
        pc = Pinecone(api_key=pinecone_api_key)
        index = pc.Index(PINECONE_INDEX_NAME)
        results = index.query(
            vector=query_embedding,
            top_k=6,
            include_metadata=True
        )
        if not results['matches']:
            return f"No matching files found for query: '{query}'"
        # todo: Will make it in-memory later. 
        save_search_context(results['matches'])

        # folder_name = get_safe_filename(query)[:50] # Limit length
        folder_name = "SearchResults"
        result_dir = os.path.join(SEARCH_RESULTS_ROOT, folder_name)
        if os.path.exists(result_dir):
            shutil.rmtree(result_dir)
        os.makedirs(result_dir)
        
        # 4. Symlink Files
        count = 0
        files_found = []
        
        for match in results['matches']:
            #todo: Need to rerank it in future
            if match['score'] < 0.6: 
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

@mcp.tool()
def search_with_filter(query: str) -> str:
    """
    Search for files using a combination of natural language and metadata filters.
    Use this for queries that specify attributes like dates, amounts, names, or specific categories.
    Example: "invoices > 30000", "notes from last week", "tickets to paris"
    """
    google_api_key = os.getenv("GOOGLE_API_KEY")
    pinecone_api_key = os.getenv("PINECONE_API_KEY")

    if not google_api_key or not pinecone_api_key:
        return "Error: Missing API keys."

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            api_key=google_api_key,
            temperature=0
        )
        
        prompt = FILTER_EXTRACTION_PROMPT.format(
            schema=json.dumps(CATEGORY_METADATA_SCHEMA, indent=2),
            query=query
        )
        response = llm.invoke(prompt)
        content = response.content.replace("```json", "").replace("```", "").strip()
        parsed_request = json.loads(content)
        
        semantic_query = parsed_request.get("semantic_query", query)
        pinecone_filter = parsed_request.get("pinecone_filter")
        embeddings_model = GoogleGenerativeAIEmbeddings(
            model="gemini-embedding-001",
            google_api_key=google_api_key,
            output_dimensionality=768
        )
        query_embedding = embeddings_model.embed_query(semantic_query)
        pc = Pinecone(api_key=pinecone_api_key)
        index = pc.Index(PINECONE_INDEX_NAME)
        results = index.query(
            vector=query_embedding,
            filter=pinecone_filter,
            top_k=20,
            include_metadata=True
        )
        if not results['matches']:
            return f"No matches found for '{query}' with filter: {pinecone_filter}"
        save_search_context(results['matches'])
        folder_name = get_safe_filename(query)[:50]
        result_dir = os.path.join(SEARCH_RESULTS_ROOT, folder_name)
        if os.path.exists(result_dir):
            shutil.rmtree(result_dir)
        os.makedirs(result_dir)
        
        count = 0
        files_found = []
        
        for match in results['matches']:
             filepath = match['metadata'].get('filepath')
             filename = match['metadata'].get('filename')
             if not filepath or not os.path.exists(filepath):
                 continue
             target_link = os.path.join(result_dir, filename)
             if os.path.exists(target_link):
                base, ext = os.path.splitext(filename)
                target_link = os.path.join(result_dir, f"{base}_{count}{ext}")
             os.symlink(filepath, target_link)
             files_found.append(filename)
             count += 1

        return f"Found {count} files matching '{query}'.\nFilter Applied: {pinecone_filter}\nLocation: {result_dir}\nFiles:\n" + "\\n".join(files_found)
        
    except Exception as e:
        return f"Error executing structured search: {e}"

@mcp.tool()
def analyze_last_search_results(instruction: str) -> str:
    """
    Analyze, summarize, or extract insights from the files found in the most recent search.
    Use this when the user refers to "these files", "the results", "them", or asks for a summary/report of the search.
    
    Args:
    Args:
        instruction: What to do with the files (e.g., "Summarize them", "Find the total amount", "List all dates")
    """
    last_search_results = load_search_context()
    if not last_search_results:
        return "No search results available in memory. Please perform a search first."
    
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        return "Error: Missing GOOGLE_API_KEY."

    context_items = []
    for match in last_search_results:
        meta = match.get('metadata', {})
        filename = meta.get('filename', 'Unknown file')
        clean_meta = {k:v for k,v in meta.items() if k not in ['filepath', 'hash', 'chunk_text']} 
        
        context_items.append(f"File: {filename}\nMetadata: {json.dumps(clean_meta)}\nSummary: {summary}\n---\n")
    
    context_str = "\n".join(context_items[:50])
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        api_key=google_api_key,
        temperature=0.2
    )
    
    prompt = f"""
    You are analyzing a set of files found in a search.
    
    User Instruction: "{instruction}"
    
    Files Found:
    {context_str}
    
    Perform the requested analysis or summary based strictly on the provided file information.
    """
    
    try:
        response = llm.invoke(prompt)
        return response.content
    except Exception as e:
        return f"Error analyzing results: {e}"

@mcp.tool()
def export_search_results(format: str = "csv") -> str:
    """
    Export the metadata of the last search results to a file (CSV or JSON).
    
    Args:
        format: 'csv' or 'json'
    """
    last_search_results = load_search_context()
    if not last_search_results:
        return "No search results to export."
        
    try:
        folder_name = "exports"
        result_dir = os.path.join(SEARCH_RESULTS_ROOT, folder_name)
        os.makedirs(result_dir, exist_ok=True)
        timestamp = int(time.time())
        filename = f"search_export_{timestamp}.{format}"
        filepath = os.path.join(result_dir, filename)
        data = []
        for match in last_search_results:
            row = match.get('metadata', {}).copy()
            row['score'] = match.get('score')
            data.append(row)
            
        if format.lower() == 'json':
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
        else:
            if not data:
                 with open(filepath, 'w') as f:
                     f.write("No data")
            else:
                keys = set()
                for d in data:
                    keys.update(d.keys())
                
                with open(filepath, 'w') as f:
                    header = ",".join(sorted(list(keys)))
                    f.write(header + "\n")
                    for d in data:
                        row = []
                        for k in sorted(list(keys)):
                            val = str(d.get(k, "")).replace(",", ";").replace("\n", " ")
                            row.append(val)
                        f.write(",".join(row) + "\n")
                        
        return f"Exported {len(data)} results to {filepath}"
        
    except Exception as e:
        return f"Error exporting: {e}"

if __name__ == "__main__":
    mcp.run()
