import zmq
import sys
import json
import os

IPC_ADDRESS = "ipc:///tmp/magic_brain.ipc"

def test_classification(filepaths):
    context = zmq.Context()
    
    print(f"Connecting to server at {IPC_ADDRESS}...")
    socket = context.socket(zmq.REQ)
    socket.connect(IPC_ADDRESS)
    
    # Construct batch request
    request = {"files": filepaths}
    print(f"Sending request: {json.dumps(request, indent=2)}")
    
    socket.send_json(request)
    
    # Receive response
    message = socket.recv_json()
    print(f"Received reply: {json.dumps(message, indent=2)}")
    
    return message

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Use command line arguments as file paths
        filepaths = sys.argv[1:]
    else:
        # Default test cases
        print("No files provided. Using default test cases.")
        filepaths = [
            "/Users/gauravkhati/.magicFolder/raw/2147886351.pdf",
            "/Users/gauravkhati/.magicFolder/raw/10th.pdf"
        ]
        
    test_classification(filepaths)
