#!/bin/bash
# Unmount script for MagicFolder

MOUNT_POINT="${1:-/tmp/magicFolder}"

echo "=== MagicFolder Unmount Script ==="
echo ""

# Check if mounted
if ! mount | grep -q "${MOUNT_POINT}"; then
    echo "Warning: ${MOUNT_POINT} does not appear to be mounted"
    exit 0
fi

echo "Unmounting: ${MOUNT_POINT}"

# Try fusermount first (Linux), then umount (macOS)
if command -v fusermount3 &> /dev/null; then
    fusermount3 -u "${MOUNT_POINT}"
elif command -v fusermount &> /dev/null; then
    fusermount -u "${MOUNT_POINT}"
else
    # macOS uses diskutil or umount
    if [[ "$OSTYPE" == "darwin"* ]]; then
        diskutil unmount "${MOUNT_POINT}" 2>/dev/null || umount "${MOUNT_POINT}"
    else
        umount "${MOUNT_POINT}"
    fi
fi

echo "Unmounted successfully!"
