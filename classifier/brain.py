import zmq
import os
import json
import time
from ocr import ocr_extract
from llm import classifyUsingLLMClassification

IPC_ADDRESS = "ipc:///tmp/magic_brain.ipc"
#need to get file as well as data
# analyze file using llm and put down into specific categories
categories=['Screenshots','Invoices','TrainTickers','IDProofs','Misc',"Notes","Credentials","Resume","Audio","Video","Archives"]
# File → Fast Preprocessing → Heuristic Classification
#                      ↓ (uncertain)
#                   LLM Classification

    # Readable text files
text_extensions = [
        '.txt', '.md', '.csv', '.json', '.xml', '.html', '.css', '.js', 
        '.py', '.cpp', '.h', '.c', '.java', '.sh', '.yaml', '.yml', 
        '.ini', '.conf', '.log'
    ]
    
    # OCR candidates
ocr_extensions = ['.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.pdf']

def extract_content(filepath):
    """
    Extract content from file based on type.
    """
    if not os.path.exists(filepath):
        return ""
        
    filename = os.path.basename(filepath)
    name, ext = os.path.splitext(filename)
    ext = ext.lower()
    
    content = ""
    try:
        if ext in text_extensions:
            with open(filepath, 'r', errors='ignore') as f:
                content = f.read()
        elif ext in ocr_extensions:
            content = ocr_extract(filepath)
    except Exception as e:
        print(f"[Brain] Error extracting content from {filename}: {e}")
        
    return content

def classifyUsingHeuristicClassification(filepath, content=None):
    """
    Analyze the file and return a category.
    Currently uses simple extension-based rules.
    """
    filename = os.path.basename(filepath)
    name, ext = os.path.splitext(filename)
    ext = ext.lower()

    # Rule Engine
    if ext in ['.mp3', '.wav', '.flac']:
        return "Audio"
    elif ext in ['.mp4', '.mov', '.avi', '.mkv']:
        return "Video"
    elif ext in ['.zip', '.tar', '.gz', '.rar']:
        return "Archives"
    
    if content is not None and content != "":
        #create a heuristic and keyword based classification
        text = content.lower()
        # ---------------- Train Tickets ----------------
        if any(
            kw in text
            for kw in [
                "irctc",
                "pnr",
                "reservation slip",
                "train no",
                "journey date",
            ]
            ):
            return "TrainTickets"
        
        # ---------------- Invoices ----------------
        if any(kw in text for kw in [
            "invoice",
            "invoice no",
            "gstin",
            "total amount",
            "bill to",
            "tax invoice",]):
            return "Invoices"
         # ---------------- Marksheets ----------------
        if any(
            kw in text
            for kw in [
                "marksheet",
                "grade",
                "percentage",
                "cgpa",
                "semester",
                "university",
                "board of education",
            ]
        ):
            return "Marksheets"
        # ---------------- ID Proofs ----------------
        if any(
            kw in text
            for kw in [
                "aadhaar",
                "government of india",
                "passport",
                "pan card",
                "date of birth",
                "dob",
            ]
        ):
            return "IDProofs"

          # ---------------- Credentials ----------------
        if any(
            kw in text
            for kw in [
                "username",
                "password",
                "api key",
                "secret key",
                "access token",
            ]
        ):
            return "Credentials"
        # ---------------- Notes ----------------
        if any(
            kw in text
            for kw in [
                "javascript",
                "system design",
                "meeting",
                "",
                "discussion points",
            ]
        ):
            return "Notes"
    return "Misc"

def main():
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind(IPC_ADDRESS)
    
    print(f"[Brain] Analysis Engine running...")
    print(f"[Brain] Listening on {IPC_ADDRESS}")
    
    while True:
        try:
            # Wait for next request from client
            message = socket.recv_json()
            print(f"[Brain] Received request: {message}")
            
            files = message.get("files", [])
            results = []
            
            if not files:
                # Fallback for single file legacy request (optional, but good for robustness)
                single_path = message.get("path")
                if single_path:
                    files = [single_path]
            
            # 1. Extract content for all files
            file_contents = []
            for filepath in files:
                content = extract_content(filepath)
                file_contents.append({"filepath": filepath, "content": content})
            print(file_contents)
            llmClassificationInput = []
            # 2. Process files (Classification)
            for item in file_contents:
                filepath = item["filepath"]
                content = item["content"]
                try:
                    category = classifyUsingHeuristicClassification(filepath, content)
                    if(category == "Misc" and content and content.strip()!=""):
                        llmClassificationInput.append({filepath, content})
                    results.append({"category": category, "path": filepath})
                    print(f"[Brain] Classified '{os.path.basename(filepath)}' as: {category}")
                except Exception as e:
                    print(f"[Brain] Error classifying {filepath}: {e}")
                    results.append({"category": "Misc", "path": filepath, "error": str(e)})
            # 3. LLM Classification for uncertain files

            print(llmClassificationInput)
         
            if(len(llmClassificationInput)>0):
                llmBasedClassificationResult=classifyUsingLLMClassification(llmClassificationInput)
                for res in llmBasedClassificationResult:
                    filepath=res.get("filepath")
                    category=res.get("category")
                    for r in results:
                        if r["path"]==filepath:
                            r["category"]=category
                            print(f"[Brain] LLM Classified '{os.path.basename(filepath)}' as: {category}")

            response = {"results": results}           # Send reply back to client
            print(f"[Brain] Sending response: {response}")
            socket.send_json(response)
            
        except KeyboardInterrupt:
            print("\n[Brain] Shutting down...")
            break
        except Exception as e:
            print(f"[Brain] Error: {e}")
            # Try to send error back if socket is in a state to send
            try:
                socket.send_json({"error": str(e)})
            except:
                pass

if __name__ == "__main__":
    main()
