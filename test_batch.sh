#!/bin/bash

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

MOUNT_POINT="$HOME/MagicFolder"
RAW_DIR="$HOME/.magicFolder/raw"

echo -e "${GREEN}=== MagicFolder Batch Test ===${NC}"

# 1. Cleanup
echo "Cleaning up..."
pkill -f "magic_folder"
pkill -f "brain.py"
sleep 1
umount "$MOUNT_POINT" 2>/dev/null
rm -rf "$MOUNT_POINT"
rm -rf "$RAW_DIR"
mkdir -p "$MOUNT_POINT"

# 2. Start Brain
echo "Starting Brain..."
python3 classifier/brain.py > brain.log 2>&1 &
BRAIN_PID=$!
sleep 2

# 3. Start MagicFolder
echo "Starting MagicFolder..."
./build/magic_folder "$MOUNT_POINT" > magic.log 2>&1 &
MAGIC_PID=$!
sleep 2

# 4. Create multiple files quickly
echo "Creating batch of files..."
touch "$MOUNT_POINT/doc1.txt"
touch "$MOUNT_POINT/doc2.txt"
touch "$MOUNT_POINT/img1.jpg"
touch "$MOUNT_POINT/img2.png"
touch "$MOUNT_POINT/code1.py"

# Wait for processing
echo "Waiting for classification..."
sleep 5

# 5. Verify
echo "Verifying results..."

check_file() {
    local file=$1
    local category=$2
    if [ -f "$MOUNT_POINT/$category/$file" ]; then
        echo -e "${GREEN}[PASS] $file found in $category${NC}"
    else
        echo -e "${RED}[FAIL] $file NOT found in $category${NC}"
        ls -R "$MOUNT_POINT"
    fi
}

check_file "doc1.txt" "Documents"
check_file "doc2.txt" "Documents"
check_file "img1.jpg" "Images"
check_file "img2.png" "Images"
check_file "code1.py" "Code"

# Cleanup
echo "Stopping processes..."
kill $BRAIN_PID
kill $MAGIC_PID
umount "$MOUNT_POINT"

echo "Done."
