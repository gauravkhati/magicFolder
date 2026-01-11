# MagicFolder 📂✨

**A Self-Organizing, AI-Powered FUSE Filesystem**

MagicFolder isn't just a place to store files—it's an intelligent system that organizes them for you. Drop a messy pile of PDFs, images, and text files into the mount point, and watch them **vanish**. Behind the scenes, a C++ FUSE driver hands them off to a Python "Brain" which reads, classifies, and indexes them into a vector database using Google Gemini and Pinecone.

Once processed, you don't browse folders manually. You use the **Sci-Fi Terminal Interface (TUI)** to ask questions like *"Find my train tickets from last month"* or *"Summarize the invoices from January,"* and the system pulls the exact files you need.

Demo - https://drive.google.com/file/d/1fYBXTjMOY7DTYI43Nrr9SP1xjMMQuGRy/view?usp=share_link

---

## 🏗 Architecture

```text
       USER
         │ (Copy File)
         ▼
    [/tmp/magicFolder]
         │
         ▼
┌─────────────────────────┐
│  LAYER 1: FUSE DRIVER   │
│ (Intercepts & "Vanishes")
└────────┬────────────────┘
         │ (Write Raw)
         ▼
  [~/.magicFolder/raw] <──────────────────────────┐
         │                                        │
         │ (Signal via ZeroMQ)                    │
         ▼                                        │ (Read Content)
┌─────────────────────────┐        ┌──────────────┴──────────┐
│  LAYER 2: THE BRAIN     │        │  LAYER 3: NEURAL LINK   │
│ (OCR, Embed, Classify)  │        │      (TUI Client)       │
└────────┬────────────────┘        └──────────────┬──────────┘
         │ (Store Vectors)                        │ (Query)
         ▼                                        ▼
    [PINECONE DB] <─────────────────────── [MCP SERVER]
```

The system consists of three distinct layers communicating via IPC and Vector Search:

1.  **The "Vanish" Filesystem (C++ / FUSE)**: 
    - Intercepts file writes at the kernel level.
    - Files written to the mount point are immediately moved to a hidden backing store (`~/.magicFolder/raw`) and queued for processing.
    - Uses ZeroMQ to signal the Brain when a file is fully written.

2.  **The Brain (Python / Gemini / Pinecone)**:
    - Listens for new file events.
    - Performs OCR on images/PDFs and reads text files.
    - Uses **Google Gemini** to classify documents and extract structured metadata (amounts, dates, PNRs).
    - Generates embeddings and stores them in a **Pinecone** vector database.

3.  **The Neural Link (MCP Server & TUI)**:
    - An **MCP (Model Context Protocol)** server exposes search tools to AI agents.
    - A **Textual-based TUI** (Terminal User Interface) acts as the client, allowing natural language queries to interact with your file knowledge base.

---

## 🛠 Prerequisites

### System Requirements
- **macOS** (requires macFUSE) or **Linux** (requires libfuse3).
- **Python 3.12+**
- **CMake** and C++ build tools.

### API Keys
You will need API keys for the AI backend:
- **Google Gemini API Key** (for embedding and reasoning).
- **Pinecone API Key** (for vector storage).

---

## 🚀 Installation

### 1. Clone the repository
```bash
git clone https://github.com/gauravkhati/MagicFolder.git
cd MagicFolder
```

### 2. Install System Dependencies

**macOS:**
```bash
# Install CMake and macFUSE
brew install cmake macfuse

# Note: After installing macFUSE, you must allow the kernel extension 
# in System Preferences > Security & Privacy using the restart instructions provided by the installer.
```

**Ubuntu/Linux:**
```bash
sudo apt-get update
sudo apt-get install cmake pkg-config libfuse3-dev fuse3
```

### 3. Build the FUSE Driver
We have a build script to handle the compilation:
```bash
chmod +x build.sh mount.sh unmount.sh
./build.sh
```

### 4. Setup Python Environment
Create a virtual environment and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Configure Secrets
Create a `.env` file in the root directory:
```bash
touch .env
```

Add your keys to `.env`:
```ini
GOOGLE_API_KEY=your_gemini_key_here
PINECONE_API_KEY=your_pinecone_key_here
```

---

## 🕹 Usage

Running MagicFolder involves three moving parts. You'll likely want three terminal tabs open.

### Terminal 1: The Brain 🧠
This service needs to run first to listen for incoming files.
```bash
source venv/bin/activate
python classifier/brain.py
```
*You'll see it waiting for ZeroMQ messages...*

### Terminal 2: The Filesystem 📂
Mount the MagicFolder. Replace `/tmp/magicFolder` with your desired mount point.
```bash
# Create mount point if it doesn't exist
mkdir -p /tmp/magicFolder

# Mount it
./mount.sh /tmp/magicFolder
```
*Any file you drop into `/tmp/magicFolder` will now vanish and be processed by the Brain.*

### Terminal 3: The Interface 🖥
Launch the TUI to search and interact with your processed files.
```bash
source venv/bin/activate
python tui_client/app.py
```

### Testing the Loop
1.  **Drop a file**: Copy an invoice or an image into `/tmp/magicFolder`.
    ```bash
    cp ~/Downloads/invoice_123.pdf /tmp/magicFolder/
    ```
2.  **Watch it vanish**: The file will disappear from `/tmp/magicFolder` instantly.
3.  **Check the Brain**: Terminal 1 will show logs: "Processing invoice_123.pdf... Classified as Invoices."
4.  **Query the TUI**: In Terminal 3, type:
    > "Find the invoice I just uploaded and tell me the total amount."

---

## 🔒 Privacy: Running Locally

If you require absolute privacy, the MagicFolder architecture is designed to be modular allows replacing cloud services with local equivalents.

*   **LLM**: You can run [Ollama](https://ollama.com) (e.g., with `llama3` or `mistral`) instead of Google Gemini.
*   **Vector DB**: You can swap Pinecone for a local **ChromaDB** or **Qdrant** instance running in Docker.

*Note: This currently requires modifying the `langchain` initialization in `classifier/rag.py` and `tui_client/app.py` to point to your local endpoints.*

---

## 🔧 Troubleshooting

**"Operation not permitted" on macOS**:
This is usually a permission issue with macFUSE. Ensure you have allowed the extension in System Settings and restarted your Mac.

**Files not vanishing?**:
Ensure the FUSE process (Terminal 2) is actually running and you are writing to the *mount point*, not the backing store.

**TUI crashing on startup?**:
Check that your `.env` file has valid API keys and that you are running inside the python virtual environment.

**How to restart?**:
If things get stuck:
1.  Run `./unmount.sh /tmp/magicFolder` to safely detach the filesystem.
2.  Kill the Python processes.
3.  Start over from Terminal 1.

---

## 📝 License
MIT License. Built with ☕️ and code.
