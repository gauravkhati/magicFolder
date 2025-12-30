import zmq
import sys
import json

IPC_ADDRESS = "ipc:///tmp/magic_brain.ipc"

def test_classification(filepath):
    context = zmq.Context()
    
    print(f"Connecting to server at {IPC_ADDRESS}...")
    socket = context.socket(zmq.REQ)
    socket.connect(IPC_ADDRESS)
    
    request = {"path": filepath}
    print(f"Sending request: {request}")
    
    socket.send_json(request)
    
    message = socket.recv_json()
    print(f"Received reply: {message}")
    
    return message

if __name__ == "__main__":
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = "invoice.pdf"
        
    test_classification(filepath)
