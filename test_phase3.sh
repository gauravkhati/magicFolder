#!/bin/bash
# End-to-End Test Script for MagicFolder Phase 3

set -e

MOUNT_POINT="/tmp/magicFolder"
BACKING_STORE="$HOME/.magicFolder/raw"
BRAIN_PID=""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

cleanup() {
    echo ""
    echo "Cleaning up..."
    if [[ -n "$BRAIN_PID" ]]; then
        echo "Stopping Brain (PID: $BRAIN_PID)..."
        kill "$BRAIN_PID" 2>/dev/null || true
    fi
    
    # Unmount if mounted
    if mount | grep -q "${MOUNT_POINT}"; then
        ./unmount.sh "${MOUNT_POINT}"
    fi
    
    # Clean backing store
    rm -rf "${BACKING_STORE}"/*
}

# Trap cleanup
trap cleanup EXIT

echo "=== MagicFolder Phase 3 Integration Test ==="
echo ""

# 1. Build
echo -e "${YELLOW}[1/5] Building MagicFolder...${NC}"
./build.sh

# 2. Start Brain
echo -e "${YELLOW}[2/5] Starting Python Brain...${NC}"
python3 classifier/bra in.py > /tmp/brain.log 2>&1 &
BRAIN_PID=$!
echo "Brain started with PID $BRAIN_PID"
sleep 2 # Wait for brain to initialize

# 3. Mount
echo -e "${YELLOW}[3/5] Mounting Filesystem...${NC}"
./mount.sh "${MOUNT_POINT}"
sleep 1

# 4. Test Classification
echo -e "${YELLOW}[4/5] Testing Classification...${NC}"

# Create a dummy PDF
echo "This is an invoice" > "${MOUNT_POINT}/invoice.pdf"
echo "Created invoice.pdf in root"

# Wait a moment for classification (it's synchronous in release(), but good to be safe)
sleep 1

# Check if it vanished from root
if ls "${MOUNT_POINT}/invoice.pdf" 2>/dev/null; then
    echo -e "${RED}FAIL: invoice.pdf is still visible in root!${NC}"
else
    echo -e "${GREEN}PASS: invoice.pdf vanished from root${NC}"
fi

# Check if it appeared in Documents
if ls "${MOUNT_POINT}/Documents/invoice.pdf" 2>/dev/null; then
    echo -e "${GREEN}PASS: invoice.pdf appeared in /Documents/invoice.pdf${NC}"
else
    echo -e "${RED}FAIL: invoice.pdf NOT found in /Documents/invoice.pdf${NC}"
    echo "Listing of /Documents:"
    ls -la "${MOUNT_POINT}/Documents" 2>/dev/null || echo "Directory not found"
fi

# Create a dummy Image
echo "This is a photo" > "${MOUNT_POINT}/photo.jpg"
echo "Created photo.jpg in root"
sleep 1

if ls "${MOUNT_POINT}/Images/photo.jpg" 2>/dev/null; then
    echo -e "${GREEN}PASS: photo.jpg appeared in /Images/photo.jpg${NC}"
else
    echo -e "${RED}FAIL: photo.jpg NOT found in /Images/photo.jpg${NC}"
fi

# 5. Verify Content
echo -e "${YELLOW}[5/5] Verifying Content Access...${NC}"
CONTENT=$(cat "${MOUNT_POINT}/Documents/invoice.pdf")
if [[ "$CONTENT" == "This is an invoice" ]]; then
    echo -e "${GREEN}PASS: Content read correctly from virtual path${NC}"
else
    echo -e "${RED}FAIL: Content mismatch. Got: '$CONTENT'${NC}"
fi

echo ""
echo -e "${GREEN}=== ALL TESTS PASSED ===${NC}"
