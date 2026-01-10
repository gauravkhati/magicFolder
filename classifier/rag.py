import os
import json
import time
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from pinecone import Pinecone, ServerlessSpec

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

COMBINED_SUMMARY_METADATA_PROMPT = """
You are an intelligent document analysis assistant. Analyze the document and return a JSON response with both a summary and extracted metadata.

**Document Category:** {category}
**File Name:** {filename}

**Document Content:**
{content}

**Required Metadata Fields for {category}:**
{fields_with_types}

**Instructions:**
1. Create a concise summary (max 150 words) optimized for semantic search that captures:
   - Document type and purpose
   - Key dates, names, amounts, or identifiers
   - Main topics or action items

2. Extract the required metadata fields listed above with the correct data types:
   - "string": Extract as text (e.g., "John Doe")
   - "number": Extract as numeric value without quotes (e.g., 150.50, not "150.50")
   - "list": Extract as JSON array (e.g., ["item1", "item2"])
   - If a field is not found, set it to null (without quotes)

3. Return ONLY valid JSON in this EXACT format:
{{
  "summary": "your summary here",
  "metadata": {{
    "field1": "string value or null",
    "field2": 123.45,
    "field3": ["item1", "item2"]
  }}
}}

**Response (JSON only):**
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
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            api_key=google_api_key,
            temperature=0.3,
        )
        
        embeddings_model = GoogleGenerativeAIEmbeddings(
            model="gemini-embedding-001",
            google_api_key=google_api_key,
            output_dimensionality=768
        )
        
        pc = Pinecone(api_key=pinecone_api_key)
        
        existing_indexes = [index.name for index in pc.list_indexes()]
        if pinecone_index_name not in existing_indexes:
            print(f"[RAG] Creating Pinecone index: {pinecone_index_name}")
            pc.create_index(
                name=pinecone_index_name,
                dimension=768, 
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
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
            
            # Summarization + Metadata Extraction
            summary = ""
            metadata_fields = {}
            
            try:
                fields_dict = CATEGORY_METADATA_SCHEMA.get(category, {"main_topic": "string", "key_entities": "list"})
                # Format fields with types for the prompt
                fields_with_types = "\n".join([f"- {field}: {dtype}" for field, dtype in fields_dict.items()])
                prompt = COMBINED_SUMMARY_METADATA_PROMPT.format(
                    category=category,
                    filename=filename,
                    content=content[:10000], 
                    fields_with_types=fields_with_types
                )
                response = llm.invoke(prompt)
                response_text = response.content.strip()
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()
                parsed = json.loads(response_text)
                summary = parsed.get("summary", "")
                metadata_fields = parsed.get("metadata", {})
                
                print(f"[RAG] Processed {filename} - Summary: {len(summary)} chars, Metadata: {list(metadata_fields.keys())}")
                
            except Exception as e:
                print(f"[RAG] Combined processing failed for {filename}: {e}")
                summary = content[:500]
                metadata_fields = {}
            
            # Embedding
            try:
                embedding = embeddings_model.embed_query(summary)
            except Exception as e:
                print(f"[RAG] Embedding failed for {filename}: {e}")
                continue
            vector_id = filepath
            metadata = {
                "filename": filename,
                "filepath": filepath,
                "category": category,
                "summary": summary,
                "created_at": time.time()
            }
            
            for key, value in metadata_fields.items():
                if value is not None:
                    if isinstance(value, (list, dict)):
                        metadata[key] = json.dumps(value) 
                    else:
                        metadata[key] = value
            
            vectors_to_upsert.append((vector_id, embedding, metadata))
            
        #Upsert to Vector DB
        if vectors_to_upsert:
            index.upsert(vectors=vectors_to_upsert)
            print(f"[RAG] Successfully stored {len(vectors_to_upsert)} vectors in Pinecone.")
            
    except Exception as e:

        print(f"[RAG] Critical Error in RAG pipeline: {e}")

