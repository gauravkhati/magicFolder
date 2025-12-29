#!/bin/bash
# Mount script for MagicFolder

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
BINARY="${BUILD_DIR}/magic_folder"
MOUNT_POINT="${1:-/tmp/magicFolder}"
BACKING_STORE="$HOME/.magicFolder/raw"

echo "=== MagicFolder Mount Script ==="
echo ""

# Check if binary exists
if [[ ! -f "${BINARY}" ]]; then
    echo "Error: magic_folder binary not found"
    echo "Run ./build.sh first to compile"
    exit 1
fi

# Create mount point if it doesn't exist
if [[ ! -d "${MOUNT_POINT}" ]]; then
    echo "Creating mount point: ${MOUNT_POINT}"
    mkdir -p "${MOUNT_POINT}"
fi

# Create backing store
if [[ ! -d "${BACKING_STORE}" ]]; then
    echo "Creating backing store: ${BACKING_STORE}"
    mkdir -p "${BACKING_STORE}"
fi

# Check if already mounted
if mount | grep -q "${MOUNT_POINT}"; then
    echo "Warning: ${MOUNT_POINT} appears to be already mounted"
    echo "Run ./unmount.sh first to unmount"
    exit 1
fi

echo "Mount point: ${MOUNT_POINT}"
echo "Backing store: ${BACKING_STORE}"
echo ""
echo "Starting MagicFolder..."
echo ""

# Run in foreground with debug output
# Add -d flag for debug mode, -f for foreground
if [[ "${2}" == "-d" ]] || [[ "${2}" == "--debug" ]]; then
    echo "Running in debug mode (foreground)..."
    "${BINARY}" "${MOUNT_POINT}" -f -d
else
    echo "Running in foreground mode..."
    echo "Press Ctrl+C to stop"
    echo ""
    "${BINARY}" "${MOUNT_POINT}" -f
fi
