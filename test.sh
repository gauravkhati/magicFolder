#!/bin/bash
# Test script for MagicFolder

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOUNT_POINT="/tmp/magicFolder"
BACKING_STORE="$HOME/.magicFolder/raw"

echo "=== MagicFolder Test Script ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if mounted
check_mounted() {
    if ! mount | grep -q "${MOUNT_POINT}"; then
        echo -e "${RED}Error: MagicFolder is not mounted${NC}"
        echo "Run ./mount.sh in another terminal first"
        exit 1
    fi
    echo -e "${GREEN}✓ MagicFolder is mounted at ${MOUNT_POINT}${NC}"
}

# Test 1: Create a file
test_create_file() {
    echo ""
    echo -e "${YELLOW}Test 1: Creating a file...${NC}"
    
    TEST_FILE="${MOUNT_POINT}/test_file.txt"
    echo "Hello, MagicFolder!" > "${TEST_FILE}"
    
    if [[ -f "${BACKING_STORE}/test_file.txt" ]]; then
        echo -e "${GREEN}✓ File exists in backing store${NC}"
    else
        echo -e "${RED}✗ File NOT found in backing store${NC}"
        return 1
    fi
}

# Test 2: Verify the "vanish" trick
test_vanish() {
    echo ""
    echo -e "${YELLOW}Test 2: Checking 'vanish' trick...${NC}"
    
    # List files in mount point
    FILES=$(ls -la "${MOUNT_POINT}" 2>/dev/null | grep -v "^total" | grep -v "^\." | wc -l | tr -d ' ')
    
    echo "Files visible in mount point: ${FILES}"
    
    if [[ "${FILES}" == "0" ]]; then
        echo -e "${GREEN}✓ VANISH TRICK WORKS! File is hidden from listing${NC}"
    else
        echo -e "${YELLOW}⚠ File is visible (vanish trick may not be active for existing files)${NC}"
    fi
    
    # Verify file still exists in backing store
    if [[ -f "${BACKING_STORE}/test_file.txt" ]]; then
        echo -e "${GREEN}✓ File still exists in backing store${NC}"
        echo "  Content: $(cat "${BACKING_STORE}/test_file.txt")"
    fi
}

# Test 3: Copy multiple files
test_multiple_files() {
    echo ""
    echo -e "${YELLOW}Test 3: Copying multiple files...${NC}"
    
    for i in {1..5}; do
        echo "File content ${i}" > "${MOUNT_POINT}/batch_file_${i}.txt"
    done
    
    BACKING_COUNT=$(ls "${BACKING_STORE}" | wc -l | tr -d ' ')
    MOUNT_COUNT=$(ls "${MOUNT_POINT}" 2>/dev/null | wc -l | tr -d ' ')
    
    echo "Files in backing store: ${BACKING_COUNT}"
    echo "Files visible in mount: ${MOUNT_COUNT}"
    
    if [[ "${BACKING_COUNT}" -gt "${MOUNT_COUNT}" ]]; then
        echo -e "${GREEN}✓ Files are being hidden (vanish trick active)${NC}"
    fi
}

# Test 4: Direct file access
test_direct_access() {
    echo ""
    echo -e "${YELLOW}Test 4: Testing direct file access...${NC}"
    
    # Even hidden files should be accessible if you know the name
    if cat "${MOUNT_POINT}/test_file.txt" 2>/dev/null | grep -q "Hello"; then
        echo -e "${GREEN}✓ Direct file access works (file readable by name)${NC}"
    else
        echo -e "${YELLOW}⚠ File not accessible by direct path${NC}"
    fi
}

# Cleanup
cleanup() {
    echo ""
    echo -e "${YELLOW}Cleaning up test files...${NC}"
    rm -f "${BACKING_STORE}/test_file.txt"
    rm -f "${BACKING_STORE}"/batch_file_*.txt
    echo -e "${GREEN}✓ Cleanup complete${NC}"
}

# Run tests
main() {
    check_mounted
    test_create_file
    test_vanish
    test_multiple_files
    test_direct_access
    
    echo ""
    echo -e "${YELLOW}Run cleanup? (y/n)${NC}"
    read -r response
    if [[ "${response}" == "y" ]]; then
        cleanup
    fi
    
    echo ""
    echo "=== Tests Complete ==="
}

main
