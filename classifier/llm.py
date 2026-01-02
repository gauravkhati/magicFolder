import dotenv
import os
import json
dotenv.load_dotenv()
CATEGORISATION_PROMPT = """
Classify the following files into one of these categories:

[
  "Screenshots",
  "Invoices",
  "TrainTickets",
  "IDProofs",
  "Misc",
  "Notes",
  "Credentials",
  "Resume",
]

Classification rules:
- Base your decision on filename, extension, and content.
- If the file is an image clearly captured from a screen → Screenshots
- If it contains billing, GST, totals, invoice numbers → Invoices
- If it contains IRCTC, PNR, journey details → TrainTickets
- If it contains government-issued identity info → IDProofs
- If it contains usernames, passwords, API keys → Credentials
- If it resembles a CV or professional profile → Resume
- If it is meeting notes, ideas, todos → Notes
- If confidence is low → Misc

Input:
[{
filepath: "<file_path>",
content: "<extracted_text_content>"
},
...
}]

Return output as JSON with this schema:

{
  "<file_id>": {
    "category": "<one of the categories>",
    "confidence": <number between 0 and 1>,
    "reason": "<short explanation>"
  }
}

Files to classify:
{{FILES_JSON}}
"""

def classifyUsingLLMClassification(llmClassificationInput):
    """
    Use a Language Model to classify the files based on its content.
    Placeholder function for LLM integration.
    """
    try:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            print("[LLM] Warning: 'langchain-google-genai' not found. LLM classification disabled.")
            return []
        apikey = os.getenv("GOOGLE_API_KEY")
        print(apikey)
        if not apikey:
            print("[LLM] Warning: GOOGLE_API_KEY not set. LLM classification disabled.")
            return []
        
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            api_key=apikey,
            temperature=0.5,
            max_output_tokens=2000,
        )
        
        # Ensure input is a JSON string
        if isinstance(llmClassificationInput, list):
            files_json = json.dumps(llmClassificationInput)
        else:
            files_json = str(llmClassificationInput)
            
        prompt = CATEGORISATION_PROMPT.replace("{{FILES_JSON}}", files_json)
        response = llm.invoke(prompt)
        
        # Extract content from AIMessage
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Clean up markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        return json.loads(content)
    except Exception as e:
        print(f"[LLM] LLM classification failed: {e}")
    return []
