/**
 * MagicFolder - A self-organizing FUSE filesystem
 */

#define FUSE_USE_VERSION 31

#include <fuse3/fuse.h>
#include <cstring>
#include <cerrno>
#include <string>
#include <vector>
#include <unordered_set>
#include <unordered_map>
#include <mutex>
#include <dirent.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/mount.h>
#include <ctime>
#include <iostream>
#include <fstream>
#include <filesystem>

namespace fs = std::filesystem;

// File metadata for unclassified files
struct FileMetadata {
    std::string filename;
    std::string full_path;
    time_t created_at;
    size_t size;
    bool is_processing;
    
    FileMetadata(const std::string& name, const std::string& path)
        : filename(name), full_path(path), created_at(time(nullptr)), 
          size(0), is_processing(true) {}
};

// Global state for the filesystem
class MagicFolderState {
public:
    std::string backing_store;  // ~/.magicFolder/raw
    std::vector<FileMetadata> unclassified_queue;
    std::unordered_set<std::string> hidden_files;  // Files to hide from root listing
    std::mutex state_mutex;
    
    static MagicFolderState& instance() {
        static MagicFolderState instance;
        return instance;
    }
    
    void add_to_queue(const std::string& filename, const std::string& full_path) {
        std::lock_guard<std::mutex> lock(state_mutex);
        unclassified_queue.emplace_back(filename, full_path);
        hidden_files.insert(filename);
        std::cout << "[MagicFolder] File queued for classification: " << filename << std::endl;
    }
    
    bool is_hidden(const std::string& filename) {
        std::lock_guard<std::mutex> lock(state_mutex);
        return hidden_files.count(filename) > 0;
    }
    
    size_t queue_size() {
        std::lock_guard<std::mutex> lock(state_mutex);
        return unclassified_queue.size();
    }
    
private:
    MagicFolderState() = default;
};

// Helper: Get the real path in the backing store
static std::string get_real_path(const char* path) {
    return MagicFolderState::instance().backing_store + path;
}

// Helper: Check if path is in root directory
static bool is_root_file(const char* path) {
    std::string p(path);
    if (p == "/") return false;
    // Check if there's only one slash at the beginning
    return p.find('/', 1) == std::string::npos;
}

// Helper: Get filename from path
static std::string get_filename(const char* path) {
    std::string p(path);
    size_t pos = p.rfind('/');
    if (pos != std::string::npos) {
        return p.substr(pos + 1);
    }
    return p;
}

// FUSE Operations

#ifdef __APPLE__
static int magic_getattr(const char* path, struct fuse_darwin_attr* stbuf, struct fuse_file_info* fi) {
    (void) fi;
    memset(stbuf, 0, sizeof(struct fuse_darwin_attr));
    
    std::string real_path = get_real_path(path);
    
    struct stat st;
    int res = lstat(real_path.c_str(), &st);
    if (res == -1) {
        return -errno;
    }
    
    // Copy stat to fuse_darwin_attr
    stbuf->ino = st.st_ino;
    stbuf->mode = st.st_mode;
    stbuf->nlink = st.st_nlink;
    stbuf->uid = st.st_uid;
    stbuf->gid = st.st_gid;
    stbuf->rdev = st.st_rdev;
    stbuf->size = st.st_size;
    stbuf->blocks = st.st_blocks;
    stbuf->blksize = st.st_blksize;
    stbuf->flags = 0;
    stbuf->atimespec = st.st_atimespec;
    stbuf->mtimespec = st.st_mtimespec;
    stbuf->ctimespec = st.st_ctimespec;
    stbuf->btimespec = st.st_birthtimespec;
    
    return 0;
}
#else
static int magic_getattr(const char* path, struct stat* stbuf, struct fuse_file_info* fi) {
    (void) fi;
    memset(stbuf, 0, sizeof(struct stat));
    
    std::string real_path = get_real_path(path);
    
    int res = lstat(real_path.c_str(), stbuf);
    if (res == -1) {
        return -errno;
    }
    
    return 0;
}
#endif

static int magic_access(const char* path, int mask) {
    std::string real_path = get_real_path(path);
    
    int res = access(real_path.c_str(), mask);
    if (res == -1) {
        return -errno;
    }
    
    return 0;
}

#ifdef __APPLE__
static int magic_readdir(const char* path, void* buf, fuse_darwin_fill_dir_t filler,
                         off_t offset, struct fuse_file_info* fi,
                         enum fuse_readdir_flags flags) {
#else
static int magic_readdir(const char* path, void* buf, fuse_fill_dir_t filler,
                         off_t offset, struct fuse_file_info* fi,
                         enum fuse_readdir_flags flags) {
#endif
    (void) offset;
    (void) fi;
    (void) flags;
    
    std::string real_path = get_real_path(path);
    DIR* dp = opendir(real_path.c_str());
    if (dp == nullptr) {
        return -errno;
    }
    
    // Add . and .. entries
    filler(buf, ".", nullptr, 0, FUSE_FILL_DIR_PLUS);
    filler(buf, "..", nullptr, 0, FUSE_FILL_DIR_PLUS);
    
    bool is_root = (strcmp(path, "/") == 0);
    
    struct dirent* de;
    while ((de = readdir(dp)) != nullptr) {
        // Skip . and .. (already added)
        if (strcmp(de->d_name, ".") == 0 || strcmp(de->d_name, "..") == 0) {
            continue;
        }
        
        // THE VANISH TRICK: Hide files in the unclassified queue from root listing
        if (is_root && MagicFolderState::instance().is_hidden(de->d_name)) {
            // File is hidden - don't show in listing
            continue;
        }
        
        struct stat st;
        memset(&st, 0, sizeof(st));
        st.st_ino = de->d_ino;
        st.st_mode = de->d_type << 12;
        
        #ifdef __APPLE__
        if (filler(buf, de->d_name, nullptr, 0, FUSE_FILL_DIR_PLUS)) {
        #else
        if (filler(buf, de->d_name, &st, 0, FUSE_FILL_DIR_PLUS)) {
        #endif
            break;
        }
    }
    
    closedir(dp);
    return 0;
}

static int magic_open(const char* path, struct fuse_file_info* fi) {
    std::string real_path = get_real_path(path);
    
    int fd = open(real_path.c_str(), fi->flags);
    if (fd == -1) {
        return -errno;
    }
    
    fi->fh = fd;
    return 0;
}

static int magic_read(const char* path, char* buf, size_t size, off_t offset,
                      struct fuse_file_info* fi) {
    int fd;
    int res;
    
    if (fi == nullptr) {
        std::string real_path = get_real_path(path);
        fd = open(real_path.c_str(), O_RDONLY);
    } else {
        fd = fi->fh;
    }
    
    if (fd == -1) {
        return -errno;
    }
    
    res = pread(fd, buf, size, offset);
    if (res == -1) {
        res = -errno;
    }
    
    if (fi == nullptr) {
        close(fd);
    }
    
    return res;
}

static int magic_write(const char* path, const char* buf, size_t size,
                       off_t offset, struct fuse_file_info* fi) {
    int fd;
    int res;
    
    if (fi == nullptr) {
        std::string real_path = get_real_path(path);
        fd = open(real_path.c_str(), O_WRONLY);
    } else {
        fd = fi->fh;
    }
    
    if (fd == -1) {
        return -errno;
    }
    
    res = pwrite(fd, buf, size, offset);
    if (res == -1) {
        res = -errno;
    }
    
    if (fi == nullptr) {
        close(fd);
    }
    
    return res;
}

static int magic_create(const char* path, mode_t mode, struct fuse_file_info* fi) {
    std::string real_path = get_real_path(path);
    
    int fd = open(real_path.c_str(), fi->flags, mode);
    if (fd == -1) {
        return -errno;
    }
    
    fi->fh = fd;
    
    // If creating a file in root, mark it for the vanish trick
    if (is_root_file(path)) {
        std::string filename = get_filename(path);
        MagicFolderState::instance().add_to_queue(filename, real_path);
    }
    
    return 0;
}

static int magic_release(const char* path, struct fuse_file_info* fi) {
    // THE VANISH TRICK: When file is closed, ensure it's in the queue
    if (is_root_file(path)) {
        std::string filename = get_filename(path);
        std::string real_path = get_real_path(path);
        
        // Check if already in queue (was added during create)
        if (!MagicFolderState::instance().is_hidden(filename)) {
            MagicFolderState::instance().add_to_queue(filename, real_path);
        }
        
        std::cout << "[MagicFolder] File closed, ready for classification: " << filename << std::endl;
        std::cout << "[MagicFolder] Queue size: " << MagicFolderState::instance().queue_size() << std::endl;
    }
    
    close(fi->fh);
    return 0;
}

static int magic_unlink(const char* path) {
    std::string real_path = get_real_path(path);
    
    int res = unlink(real_path.c_str());
    if (res == -1) {
        return -errno;
    }
    
    return 0;
}

static int magic_mkdir(const char* path, mode_t mode) {
    std::string real_path = get_real_path(path);
    
    int res = mkdir(real_path.c_str(), mode);
    if (res == -1) {
        return -errno;
    }
    
    return 0;
}

static int magic_rmdir(const char* path) {
    std::string real_path = get_real_path(path);
    
    int res = rmdir(real_path.c_str());
    if (res == -1) {
        return -errno;
    }
    
    return 0;
}

static int magic_rename(const char* from, const char* to, unsigned int flags) {
    std::string real_from = get_real_path(from);
    std::string real_to = get_real_path(to);
    
    if (flags) {
        return -EINVAL;
    }
    
    int res = rename(real_from.c_str(), real_to.c_str());
    if (res == -1) {
        return -errno;
    }
    
    return 0;
}

static int magic_truncate(const char* path, off_t size, struct fuse_file_info* fi) {
    std::string real_path = get_real_path(path);
    int res;
    
    if (fi != nullptr) {
        res = ftruncate(fi->fh, size);
    } else {
        res = truncate(real_path.c_str(), size);
    }
    
    if (res == -1) {
        return -errno;
    }
    
    return 0;
}

static int magic_utimens(const char* path, const struct timespec ts[2],
                         struct fuse_file_info* fi) {
    (void) fi;
    std::string real_path = get_real_path(path);
    
    int res = utimensat(AT_FDCWD, real_path.c_str(), ts, AT_SYMLINK_NOFOLLOW);
    if (res == -1) {
        return -errno;
    }
    
    return 0;
}

static int magic_chmod(const char* path, mode_t mode, struct fuse_file_info* fi) {
    (void) fi;
    std::string real_path = get_real_path(path);
    
    int res = chmod(real_path.c_str(), mode);
    if (res == -1) {
        return -errno;
    }
    
    return 0;
}

static int magic_chown(const char* path, uid_t uid, gid_t gid, struct fuse_file_info* fi) {
    (void) fi;
    std::string real_path = get_real_path(path);
    
    int res = lchown(real_path.c_str(), uid, gid);
    if (res == -1) {
        return -errno;
    }
    
    return 0;
}

static int magic_statfs(const char* path, struct statfs* stbuf) {
    std::string real_path = get_real_path(path);
    
    int res = statfs(real_path.c_str(), stbuf);
    if (res == -1) {
        return -errno;
    }
    
    return 0;
}

static void* magic_init(struct fuse_conn_info* conn, struct fuse_config* cfg) {
    (void) conn;
    cfg->kernel_cache = 0;  // Disable kernel caching for real-time updates
    cfg->use_ino = 1;
    
    std::cout << "[MagicFolder] Filesystem initialized!" << std::endl;
    std::cout << "[MagicFolder] Backing store: " << MagicFolderState::instance().backing_store << std::endl;
    
    return nullptr;
}

static void magic_destroy(void* private_data) {
    (void) private_data;
    std::cout << "[MagicFolder] Filesystem unmounted." << std::endl;
    std::cout << "[MagicFolder] Files in queue: " << MagicFolderState::instance().queue_size() << std::endl;
}

// FUSE operations structure
static const struct fuse_operations magic_oper = {
    .getattr    = magic_getattr,
    .mkdir      = magic_mkdir,
    .unlink     = magic_unlink,
    .rmdir      = magic_rmdir,
    .rename     = magic_rename,
    .chmod      = magic_chmod,
    .chown      = magic_chown,
    .truncate   = magic_truncate,
    .open       = magic_open,
    .read       = magic_read,
    .write      = magic_write,
    .release    = magic_release,
    .readdir    = magic_readdir,
    .init       = magic_init,
    .destroy    = magic_destroy,
    .access     = magic_access,
    .create     = magic_create,
    .utimens    = magic_utimens,
    .statfs     = magic_statfs,
};

void print_usage(const char* progname) {
    std::cout << "Usage: " << progname << " <mountpoint> [FUSE options]" << std::endl;
    std::cout << std::endl;
    std::cout << "MagicFolder - A self-organizing FUSE filesystem" << std::endl;
    std::cout << "Files written to the mount point will 'vanish' from the listing" << std::endl;
    std::cout << "and be queued for automatic classification." << std::endl;
    std::cout << std::endl;
    std::cout << "Backing store: ~/.magicFolder/raw" << std::endl;
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        print_usage(argv[0]);
        return 1;
    }
    
    // Setup backing store path
    const char* home = getenv("HOME");
    if (home == nullptr) {
        std::cerr << "Error: HOME environment variable not set" << std::endl;
        return 1;
    }
    
    std::string backing_store = std::string(home) + "/.magicFolder/raw";
    MagicFolderState::instance().backing_store = backing_store;
    
    // Create backing store if it doesn't exist
    try {
        fs::create_directories(backing_store);
        std::cout << "[MagicFolder] Backing store created/verified: " << backing_store << std::endl;
    } catch (const fs::filesystem_error& e) {
        std::cerr << "Error creating backing store: " << e.what() << std::endl;
        return 1;
    }
    
    std::cout << "[MagicFolder] Starting FUSE filesystem..." << std::endl;
    std::cout << "[MagicFolder] Mount point: " << argv[1] << std::endl;
    
    return fuse_main(argc, argv, &magic_oper, nullptr);
}
