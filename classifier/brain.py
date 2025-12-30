import zmq
import os
import json
import time

IPC_ADDRESS = "ipc:///tmp/magic_brain.ipc"

def classify(filepath):
    """
    Analyze the file and return a category.
    Currently uses simple extension-based rules.
    """
    filename = os.path.basename(filepath)
    name, ext = os.path.splitext(filename)
    ext = ext.lower()
    
    # Rule Engine
    if ext in ['.pdf', '.doc', '.docx', '.txt', '.md']:
        return "Documents"
    elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg']:
        return "Images"
    elif ext in ['.mp3', '.wav', '.flac']:
        return "Audio"
    elif ext in ['.mp4', '.mov', '.avi', '.mkv']:
        return "Video"
    elif ext in ['.py', '.cpp', '.h', '.js', '.ts', '.html', '.css', '.json']:
        return "Code"
    elif ext in ['.zip', '.tar', '.gz', '.rar']:
        return "Archives"
    elif ext in ['.xls', '.xlsx', '.csv']:
        return "Financials"
    
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
            
            filepath = message.get("path", "")
            
            if not filepath:
                response = {"error": "No path provided"}
            else:
                category = classify(filepath)
                response = {"category": category, "path": filepath}
                print(f"[Brain] Classified as: {category}")
            
            # Send reply back to client
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
