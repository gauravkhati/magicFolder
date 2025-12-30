# MagicFolder - Self-Organizing FUSE Filesystem

A FUSE-based filesystem that automatically organizes files. Files written to the mount point "vanish" from the visible listing and are queued for automatic classification.

## Phase 1: Passthrough Driver with "Vanish" Trick

This implementation creates a FUSE filesystem that:
1. **Mirrors a backing store**: All files are actually stored in `~/.magicFolder/raw`
2. **Intercepts writes**: When files are written to the root of the mount point, they're marked for classification
3. **Implements the "Vanish" trick**: Files in the classification queue are hidden from directory listings

## Phase 2: The Python Brain (Analysis Engine)

The "Brain" is a standalone Python service that classifies files based on their content or metadata. It communicates with the FUSE driver (in future phases) or test scripts via ZeroMQ IPC.

### Setup

1. **Install Python dependencies**:
   ```bash
   pip install -r classifier/requirements.txt
   ```

2. **Run the Brain service**:
   ```bash
   python classifier/brain.py
   ```

3. **Test the Brain**:
   In a separate terminal:
   ```bash
   python classifier/test_brain.py invoice.pdf
   # Output: {'category': 'Documents', 'path': 'invoice.pdf'}
   
   python classifier/test_brain.py vacation.jpg
   # Output: {'category': 'Images', 'path': 'vacation.jpg'}
   ```

## Prerequisites

### macOS
```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install required packages
brew install cmake pkg-config

# Install macFUSE
brew install --cask macfuse

# IMPORTANT: After installing macFUSE:
# 1. Restart your computer
# 2. Go to System Preferences > Security & Privacy
# 3. Allow the kernel extension from "Benjamin Fleischer"
```

### Linux (Ubuntu/Debian)
```bash
sudo apt-get update
sudo apt-get install cmake pkg-config libfuse3-dev fuse3
```

## Building

```bash
# Make scripts executable
chmod +x build.sh mount.sh unmount.sh test.sh

# Build the project
./build.sh
```

## Usage

### 1. Mount the filesystem
```bash
# In terminal 1 - this runs in foreground
./mount.sh /tmp/magicFolder

# Or with debug output
./mount.sh /tmp/magicFolder -d
```

### 2. Test the vanish trick
```bash
# In terminal 2
# Copy a file to the mount point
cp test.txt /tmp/magicFolder/

# The copy succeeds! But...
ls /tmp/magicFolder/
# Shows nothing! The file has "vanished"

# However, the file actually exists in the backing store
ls ~/.magicFolder/raw/
# Shows: test.txt
```

### 3. Run the test suite
```bash
./test.sh
```

### 4. Unmount
```bash
./unmount.sh /tmp/magicFolder
# Or press Ctrl+C in the mount terminal
```

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Space                            │
│  ┌─────────────┐    ┌───────────────────────────────┐   │
│  │   cp file   │───▶│      magic_folder (FUSE)      │   │
│  └─────────────┘    │  ┌─────────────────────────┐  │   │
│                     │  │   MagicFolderState      │  │   │
│                     │  │  - unclassified_queue   │  │   │
│                     │  │  - hidden_files set     │  │   │
│                     │  └─────────────────────────┘  │   │
│                     └───────────────┬───────────────┘   │
└─────────────────────────────────────┼───────────────────┘
                                      │
┌─────────────────────────────────────┼───────────────────┐
│                    Kernel Space     │                    │
│                     ┌───────────────▼───────────────┐   │
│                     │         FUSE Kernel           │   │
│                     └───────────────┬───────────────┘   │
└─────────────────────────────────────┼───────────────────┘
                                      │
┌─────────────────────────────────────┼───────────────────┐
│                    Filesystem       │                    │
│                     ┌───────────────▼───────────────┐   │
│                     │   ~/.magicFolder/raw/         │   │
│                     │   (Backing Store)             │   │
│                     └───────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### The Vanish Trick

1. **File Creation (`create`)**: When a file is created in the root directory, it's added to `hidden_files` set and `unclassified_queue`

2. **File Write (`write`)**: Data is written to the actual file in the backing store

3. **File Close (`release`)**: The file is marked as ready for classification

4. **Directory Listing (`readdir`)**: Files in `hidden_files` are excluded from the listing

### Key Components

- **`MagicFolderState`**: Singleton class managing the filesystem state
  - `unclassified_queue`: Vector of files awaiting classification
  - `hidden_files`: Set of filenames to hide from root listing

- **FUSE Operations**: Standard FUSE callbacks that pass through to the backing store
  - `magic_getattr`: Get file attributes
  - `magic_readdir`: List directory (with vanish trick)
  - `magic_create`: Create new files (trigger vanish)
  - `magic_read/write`: Read/write file data
  - `magic_release`: Close file (finalize vanish)

## Project Structure

```
MagicFolder/
├── CMakeLists.txt      # CMake build configuration
├── README.md           # This file
├── build.sh            # Build script
├── mount.sh            # Mount script
├── unmount.sh          # Unmount script
├── test.sh             # Test script
└── src/
    └── magic_folder.cpp  # Main FUSE driver implementation
```

## Next Phases

### Phase 2: File Classification
- Integrate Python API for content analysis
- Analyze file headers and content
- Categorize files (Financials, Code, Documents, Images, etc.)

### Phase 3: Virtual Directories
- Create virtual category directories
- Move file inodes to appropriate subdirectories
- Implement real-time file organization

## Troubleshooting

### macOS: "Operation not permitted"
- Ensure macFUSE kernel extension is allowed in System Preferences
- Restart your computer after installing macFUSE

### "fusermount: command not found"
- On macOS, use `diskutil unmount` or `umount` instead
- The unmount.sh script handles this automatically

### Files not vanishing
- Ensure you're writing to the root of the mount point
- Check the terminal running the FUSE driver for log messages

## License

MIT License
