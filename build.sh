#!/bin/bash
# Build script for MagicFolder

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"

echo "=== MagicFolder Build Script ==="
echo ""

# Check for required dependencies
check_dependencies() {
    echo "Checking dependencies..."
    
    # Check for cmake
    if ! command -v cmake &> /dev/null; then
        echo "Error: cmake is not installed"
        echo "Install with: brew install cmake"
        exit 1
    fi
    
    # Check for pkg-config
    if ! command -v pkg-config &> /dev/null; then
        echo "Error: pkg-config is not installed"
        echo "Install with: brew install pkg-config"
        exit 1
    fi
    
    # Check for libfuse (macFUSE on macOS)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if ! pkg-config --exists fuse3 2>/dev/null; then
            echo "Error: macFUSE is not installed or fuse3 pkg-config is not found"
            echo ""
            echo "To install macFUSE:"
            echo "  1. Download from: https://osxfuse.github.io/"
            echo "  2. Or install via: brew install --cask macfuse"
            echo ""
            echo "After installing macFUSE, you may need to:"
            echo "  - Restart your computer"
            echo "  - Allow the kernel extension in System Preferences > Security & Privacy"
            echo ""
            echo "For pkg-config to find fuse3, you may need:"
            echo "  export PKG_CONFIG_PATH=\"/usr/local/lib/pkgconfig:\$PKG_CONFIG_PATH\""
            exit 1
        fi
    else
        if ! pkg-config --exists fuse3 2>/dev/null; then
            echo "Error: libfuse3 is not installed"
            echo "Install with: sudo apt-get install libfuse3-dev fuse3"
            exit 1
        fi
    fi
    
    echo "All dependencies found!"
    echo ""
}

# Build the project
build() {
    echo "Building MagicFolder..."
    
    mkdir -p "${BUILD_DIR}"
    cd "${BUILD_DIR}"
    
    cmake ..
    make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu)
    
    echo ""
    echo "Build successful!"
    echo "Binary location: ${BUILD_DIR}/magic_folder"
}

# Clean build
clean() {
    echo "Cleaning build directory..."
    rm -rf "${BUILD_DIR}"
    echo "Clean complete!"
}

# Main
case "${1:-build}" in
    build)
        check_dependencies
        build
        ;;
    clean)
        clean
        ;;
    rebuild)
        clean
        check_dependencies
        build
        ;;
    *)
        echo "Usage: $0 {build|clean|rebuild}"
        exit 1
        ;;
esac
