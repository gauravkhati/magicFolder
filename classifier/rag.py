import os
import json
import time
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from pinecone import Pinecone, ServerlessSpec

# Prompt for summarization
SUMMARY_PROMPT = """
Summarize the following file content in a concise manner (max 150 words).
Focus on key information that would be useful for searching later.

File: {filename}
Content:
{content}

Summary:
"""

def process_and_store_embeddings(file_data_list):
    """
    1. Summarize content using LLM.
    2. Generate embeddings for the summary.
    3. Store in Pinecone DB.
    
    Args:
        file_data_list: List of dicts with 'filepath', 'content', 'category'
    """
    print(f"[RAG] Starting post-processing for {len(file_data_list)} files...")
    
    # 1. Setup Clients
    google_api_key = os.getenv("GOOGLE_API_KEY")
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    pinecone_index_name = os.getenv("PINECONE_INDEX_NAME", "magic-folder-index")
    
    if not google_api_key:
        print("[RAG] Error: GOOGLE_API_KEY not set. Skipping RAG.")
        return
    
    if not pinecone_api_key:
        print("[RAG] Error: PINECONE_API_KEY not set. Skipping RAG.")
        return
    print(pinecone_api_key)
    try:
        # Initialize LLM for summarization
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            api_key=google_api_key,
            temperature=0.3,
        )
        
        # Initialize Embeddings
        embeddings_model = GoogleGenerativeAIEmbeddings(
            model="gemini-embedding-001",
            google_api_key=google_api_key,
            output_dimensionality=768
        )
        
        # Initialize Pinecone
        pc = Pinecone(api_key=pinecone_api_key)
        
        # Check if index exists, create if not
        existing_indexes = [index.name for index in pc.list_indexes()]
        if pinecone_index_name not in existing_indexes:
            print(f"[RAG] Creating Pinecone index: {pinecone_index_name}")
            pc.create_index(
                name=pinecone_index_name,
                dimension=768, # Dimension for embedding-001
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            # Wait for index to be ready
            while not pc.describe_index(pinecone_index_name).status['ready']:
                time.sleep(1)
        
        index = pc.Index(pinecone_index_name)
        
        vectors_to_upsert = []
        
        for item in file_data_list:
            filepath = item.get("filepath")
            content = item.get("content")
            category = item.get("category", "Misc")
            
            if not content or len(content.strip()) < 10:
                print(f"[RAG] Skipping {os.path.basename(filepath)}: Content too short.")
                continue
                
            filename = os.path.basename(filepath)
            
            # A. Summarize
            try:
                prompt = SUMMARY_PROMPT.format(filename=filename, content=content[:10000]) # Truncate if too long
                response = llm.invoke(prompt)
                summary = response.content
                print(f"[RAG] Summarized {filename}")
            except Exception as e:
                print(f"[RAG] Summarization failed for {filename}: {e}")
                summary = content[:500] # Fallback to first 500 chars
            
            # B. Embed
            try:
                embedding = embeddings_model.embed_query(summary)
            except Exception as e:
                print(f"[RAG] Embedding failed for {filename}: {e}")
                continue
                
            # C. Prepare for Pinecone
            # ID can be filename or hash. Filename is simple but might collide if paths differ.
            # Using full path hash or just path string as ID (Pinecone IDs must be strings)
            vector_id = filepath
            
            metadata = {
                "filename": filename,
                "filepath": filepath,
                "category": category,
                "summary": summary,
                "created_at": time.time()
            }
            
            vectors_to_upsert.append((vector_id, embedding, metadata))
            
        # D. Upsert to Pinecone
        if vectors_to_upsert:
            index.upsert(vectors=vectors_to_upsert)
            print(f"[RAG] Successfully stored {len(vectors_to_upsert)} vectors in Pinecone.")
            
    except Exception as e:

        print(f"[RAG] Critical Error in RAG pipeline: {e}")

