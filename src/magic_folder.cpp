/**
 * MagicFolder - A self-organizing FUSE filesystem
 * Phase 1: Passthrough driver with "vanish" trick
 * 
 * Files written to the mount point are stored in a backing directory
 * but "vanish" from the root listing until classified.
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
#include <map>
#include <zmq.h>
#include <thread>
#include <queue>
#include <condition_variable>
#include <atomic>

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
    
    // Virtual Directory Structure
    // Category -> List of filenames
    std::map<std::string, std::vector<std::string>> categories;
    // Filename -> Category (for quick lookup)
    std::map<std::string, std::string> file_category_map;
    
    std::mutex state_mutex;
    
    // Async Processing
    std::queue<std::string> processing_queue;
    std::unordered_set<std::string> queued_files; // To prevent duplicates
    std::mutex queue_mutex;
    std::condition_variable queue_cv;
    std::thread worker_thread;
    std::atomic<bool> running;

    // ZeroMQ
    void* context;
    void* socket;
    
    static MagicFolderState& instance() {
        static MagicFolderState instance;
        return instance;
    }
    
    void init_zmq() {
        context = zmq_ctx_new();
        socket = zmq_socket(context, ZMQ_REQ);
        
        // Set timeout to avoid hanging if Python brain is down
        // Increased to 60 seconds because LLM/OCR processing can be slow
        int timeout = 60000; 
        zmq_setsockopt(socket, ZMQ_RCVTIMEO, &timeout, sizeof(timeout));
        zmq_setsockopt(socket, ZMQ_SNDTIMEO, &timeout, sizeof(timeout));
        
        int rc = zmq_connect(socket, "ipc:///tmp/magic_brain.ipc");
        if (rc == 0) {
            std::cout << "[MagicFolder] Connected to Brain IPC" << std::endl;
        } else {
            std::cerr << "[MagicFolder] Failed to connect to Brain IPC: " << zmq_strerror(errno) << std::endl;
        }

        // Start worker thread
        running = true;
        worker_thread = std::thread(&MagicFolderState::worker_loop, this);
    }

    void worker_loop() {
        while (running) {
            std::vector<std::string> batch;
            {
                std::unique_lock<std::mutex> lock(queue_mutex);
                queue_cv.wait(lock, [this] { return !processing_queue.empty() || !running; });
                
                if (!running && processing_queue.empty()) break;
                
                // DEBOUNCE: Wait a bit to let more files arrive for batch processing
                // This also helps ensure files are fully flushed to disk before reading
                lock.unlock();
                std::this_thread::sleep_for(std::chrono::milliseconds(500));
                lock.lock();
                
                if (!running && processing_queue.empty()) break;
                
                // Dequeue ALL items to process in batch
                while (!processing_queue.empty()) {
                    batch.push_back(processing_queue.front());
                    processing_queue.pop();
                }
                // We keep files in queued_files until processing is done to prevent duplicates
            }
            
            if (!batch.empty()) {
                classify_files_batch(batch);
                
                // Now remove processed files from the tracking set
                std::lock_guard<std::mutex> lock(queue_mutex);
                for (const auto& file : batch) {
                    queued_files.erase(file);
                }
            }
        }
    }

    void enqueue_for_classification(const std::string& filename) {
        // Ignore macOS metadata files
        if (filename == ".DS_Store" || (filename.size() >= 2 && filename.substr(0, 2) == "._")) {
            return;
        }

        // Check if already classified
        {
            std::lock_guard<std::mutex> lock(state_mutex);
            if (file_category_map.count(filename)) {
                return; // Already classified
            }
        }

        {
            std::lock_guard<std::mutex> lock(queue_mutex);
            // Check if already in queue
            if (queued_files.count(filename)) {
                return; // Already queued
            }
            
            processing_queue.push(filename);
            queued_files.insert(filename);
        }
        queue_cv.notify_one();
        std::cout << "[MagicFolder] Enqueued for async classification: " << filename << std::endl;
    }

    void shutdown() {
        running = false;
        queue_cv.notify_all();
        if (worker_thread.joinable()) {
            worker_thread.join();
        }
        if (socket) zmq_close(socket);
        if (context) zmq_ctx_destroy(context);
    }
    
    void add_to_queue(const std::string& filename, const std::string& full_path) {
        // Ignore macOS metadata files
        if (filename == ".DS_Store" || (filename.size() >= 2 && filename.substr(0, 2) == "._")) {
            return;
        }

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
    
    // Request classification from Python Brain (Batch)
    void classify_files_batch(const std::vector<std::string>& filenames) {
        if (filenames.empty()) return;

        std::string request = "{\"files\": [";
        for (size_t i = 0; i < filenames.size(); ++i) {
            std::string full_path = backing_store + "/" + filenames[i];
            request += "\"" + full_path + "\"";
            if (i < filenames.size() - 1) {
                request += ", ";
            }
        }
        request += "]}";
        
        std::cout << "[MagicFolder] Sending batch request (" << filenames.size() << " files): " << request << std::endl;
        
        zmq_send(socket, request.c_str(), request.length(), 0);
        
        char buffer[8192]; // Larger buffer for batch response
        int bytes = zmq_recv(socket, buffer, 8192, 0);
        
        if (bytes > 0) {
            buffer[bytes] = '\0';
            std::string response(buffer);
            std::cout << "[MagicFolder] Received batch response" << std::endl;
            
            // Parse response for each file in the batch
            for (const auto& filename : filenames) {
                std::string full_path = backing_store + "/" + filename;
                
                // Find the object containing this path
                // We look for the path string, then find the surrounding {}
                size_t p_pos = response.find(full_path);
                if (p_pos != std::string::npos) {
                    size_t obj_start = response.rfind("{", p_pos);
                    size_t obj_end = response.find("}", p_pos);
                    
                    if (obj_start != std::string::npos && obj_end != std::string::npos) {
                        std::string obj_str = response.substr(obj_start, obj_end - obj_start);
                        
                        size_t c_pos = obj_str.find("\"category\": \"");
                        if (c_pos != std::string::npos) {
                            size_t c_start = c_pos + 13;
                            size_t c_end = obj_str.find("\"", c_start);
                            if (c_end != std::string::npos) {
                                std::string category = obj_str.substr(c_start, c_end - c_start);
                                update_category(filename, category);
                            }
                        }
                    }
                }
            }
        } else {
            std::cerr << "[MagicFolder] Failed to receive response from Brain" << std::endl;
        }
    }
    
    void update_category(const std::string& filename, const std::string& category) {
        std::lock_guard<std::mutex> lock(state_mutex);
        
        // Remove from hidden/unclassified
        hidden_files.erase(filename);
        // Note: We don't remove from unclassified_queue vector efficiently, 
        // but for MVP we just ignore it or clear it periodically.
        
        // Add to category
        categories[category].push_back(filename);
        file_category_map[filename] = category;
        
        std::cout << "[MagicFolder] File '" << filename << "' moved to '" << category << "'" << std::endl;
    }
    
private:
    MagicFolderState() : context(nullptr), socket(nullptr) {}
};

// Helper: Get the real path in the backing store
static std::string get_real_path(const char* path) {
    std::string p(path);
    
    // Check if it's a file inside a virtual category
    // Format: /Category/filename
    size_t second_slash = p.find('/', 1);
    if (second_slash != std::string::npos) {
        std::string category = p.substr(1, second_slash - 1);
        std::string filename = p.substr(second_slash + 1);
        
        // Check if this is a known category mapping
        // For MVP, we assume if it looks like a category path, it maps to the raw file
        return MagicFolderState::instance().backing_store + "/" + filename;
    }
    
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

// Helper: Check if file should be ignored (macOS metadata, etc)
static bool is_ignored_file(const std::string& filename) {
    return (filename == ".DS_Store" || (filename.size() >= 2 && filename.substr(0, 2) == "._"));
}

// FUSE Operations

#ifdef __APPLE__
static int magic_getattr(const char* path, struct fuse_darwin_attr* stbuf, struct fuse_file_info* fi) {
    (void) fi;
    memset(stbuf, 0, sizeof(struct fuse_darwin_attr));
    
    std::string p(path);
    bool is_virtual_dir = false;
    
    // Check if it's a virtual category directory
    if (p != "/") {
        // Remove leading slash
        std::string name = p.substr(1);
        // Check if it contains slash (meaning it's a file inside category)
        if (name.find('/') == std::string::npos) {
            // It's a top level entry. Check if it's a category.
            std::lock_guard<std::mutex> lock(MagicFolderState::instance().state_mutex);
            if (MagicFolderState::instance().categories.count(name)) {
                is_virtual_dir = true;
            }
        }
    }
    
    if (is_virtual_dir) {
        // Fake directory attributes
        stbuf->mode = S_IFDIR | 0755;
        stbuf->nlink = 2;
        stbuf->uid = getuid();
        stbuf->gid = getgid();
        stbuf->size = 4096;
        stbuf->blocks = 8;
        stbuf->ino = std::hash<std::string>{}(p); // Fake inode based on path hash
        stbuf->atimespec.tv_sec = time(nullptr);
        stbuf->mtimespec.tv_sec = time(nullptr);
        stbuf->ctimespec.tv_sec = time(nullptr);
        return 0;
    }
    
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
    
    std::string p(path);
    bool is_virtual_dir = false;
    
    // Check if it's a virtual category directory
    if (p != "/") {
        std::string name = p.substr(1);
        if (name.find('/') == std::string::npos) {
            std::lock_guard<std::mutex> lock(MagicFolderState::instance().state_mutex);
            if (MagicFolderState::instance().categories.count(name)) {
                is_virtual_dir = true;
            }
        }
    }
    
    if (is_virtual_dir) {
        stbuf->st_mode = S_IFDIR | 0755;
        stbuf->st_nlink = 2;
        stbuf->st_uid = getuid();
        stbuf->st_gid = getgid();
        stbuf->st_size = 4096;
        stbuf->st_atime = time(nullptr);
        stbuf->st_mtime = time(nullptr);
        stbuf->st_ctime = time(nullptr);
        return 0;
    }
    
    std::string real_path = get_real_path(path);
    
    int res = lstat(real_path.c_str(), stbuf);
    if (res == -1) {
        return -errno;
    }
    
    return 0;
}
#endif

static int magic_access(const char* path, int mask) {
    std::string p(path);
    
    // Check if it's a virtual category directory
    if (p != "/") {
        std::string name = p.substr(1);
        if (name.find('/') == std::string::npos) {
            std::lock_guard<std::mutex> lock(MagicFolderState::instance().state_mutex);
            if (MagicFolderState::instance().categories.count(name)) {
                return 0; // Virtual directories are always accessible
            }
        }
    }

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
    
    // Add . and .. entries
    filler(buf, ".", nullptr, 0, FUSE_FILL_DIR_PLUS);
    filler(buf, "..", nullptr, 0, FUSE_FILL_DIR_PLUS);
    
    bool is_root = (strcmp(path, "/") == 0);
    
    // If root, show categories and unhidden files
    if (is_root) {
        // 1. Show Categories (Virtual Directories)
        {
            std::lock_guard<std::mutex> lock(MagicFolderState::instance().state_mutex);
            for (const auto& pair : MagicFolderState::instance().categories) {
                struct stat st;
                memset(&st, 0, sizeof(st));
                st.st_mode = S_IFDIR | 0755;
                
                #ifdef __APPLE__
                filler(buf, pair.first.c_str(), nullptr, 0, FUSE_FILL_DIR_PLUS);
                #else
                filler(buf, pair.first.c_str(), &st, 0, FUSE_FILL_DIR_PLUS);
                #endif
            }
        }
        
        // 2. Show real files (excluding hidden ones)
        std::string real_path = get_real_path(path);
        DIR* dp = opendir(real_path.c_str());
        if (dp != nullptr) {
            struct dirent* de;
            while ((de = readdir(dp)) != nullptr) {
                if (strcmp(de->d_name, ".") == 0 || strcmp(de->d_name, "..") == 0) continue;
                
                // THE VANISH TRICK
                if (MagicFolderState::instance().is_hidden(de->d_name)) {
                    continue;
                }
                
                // Also hide files that have been categorized (they are now in virtual dirs)
                {
                    std::lock_guard<std::mutex> lock(MagicFolderState::instance().state_mutex);
                    if (MagicFolderState::instance().file_category_map.count(de->d_name)) {
                        continue;
                    }
                }
                
                struct stat st;
                memset(&st, 0, sizeof(st));
                st.st_ino = de->d_ino;
                st.st_mode = de->d_type << 12;
                
                #ifdef __APPLE__
                if (filler(buf, de->d_name, nullptr, 0, FUSE_FILL_DIR_PLUS)) break;
                #else
                if (filler(buf, de->d_name, &st, 0, FUSE_FILL_DIR_PLUS)) break;
                #endif
            }
            closedir(dp);
        }
    } else {
        // Check if it's a category directory
        std::string p(path);
        std::string category = p.substr(1); // Remove leading slash
        
        std::vector<std::string> files;
        bool is_category = false;
        
        {
            std::lock_guard<std::mutex> lock(MagicFolderState::instance().state_mutex);
            auto it = MagicFolderState::instance().categories.find(category);
            if (it != MagicFolderState::instance().categories.end()) {
                is_category = true;
                files = it->second;
            }
        }
        
        if (is_category) {
            // List files in this category
            for (const auto& filename : files) {
                // We need to get stats for the real file
                std::string real_file_path = MagicFolderState::instance().backing_store + "/" + filename;
                struct stat st;
                if (lstat(real_file_path.c_str(), &st) == 0) {
                    #ifdef __APPLE__
                    filler(buf, filename.c_str(), nullptr, 0, FUSE_FILL_DIR_PLUS);
                    #else
                    filler(buf, filename.c_str(), &st, 0, FUSE_FILL_DIR_PLUS);
                    #endif
                }
            }
        } else {
            // It might be a real directory in the backing store (not supported in this MVP logic fully, but fallback)
            std::string real_path = get_real_path(path);
            DIR* dp = opendir(real_path.c_str());
            if (dp != nullptr) {
                struct dirent* de;
                while ((de = readdir(dp)) != nullptr) {
                    if (strcmp(de->d_name, ".") == 0 || strcmp(de->d_name, "..") == 0) continue;
                    #ifdef __APPLE__
                    if (filler(buf, de->d_name, nullptr, 0, FUSE_FILL_DIR_PLUS)) break;
                    #else
                    struct stat st;
                    memset(&st, 0, sizeof(st));
                    st.st_ino = de->d_ino;
                    st.st_mode = de->d_type << 12;
                    if (filler(buf, de->d_name, &st, 0, FUSE_FILL_DIR_PLUS)) break;
                    #endif
                }
                closedir(dp);
            }
        }
    }
    
    return 0;
}

static int magic_opendir(const char* path, struct fuse_file_info* fi) {
    (void) fi;
    std::string p(path);
    
    // Check if virtual directory
    if (p != "/") {
        std::string name = p.substr(1);
        if (name.find('/') == std::string::npos) {
            std::lock_guard<std::mutex> lock(MagicFolderState::instance().state_mutex);
            if (MagicFolderState::instance().categories.count(name)) {
                return 0; // Success for virtual dir
            }
        }
    }
    
    // For real directories, check if they exist
    std::string real_path = get_real_path(path);
    DIR* dp = opendir(real_path.c_str());
    if (dp == nullptr) {
        return -errno;
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
        if (!is_ignored_file(filename)) {
            MagicFolderState::instance().add_to_queue(filename, real_path);
        }
    }
    
    return 0;
}

static int magic_release(const char* path, struct fuse_file_info* fi) {
    // THE VANISH TRICK: When file is closed, ensure it's in the queue
    if (is_root_file(path)) {
        std::string filename = get_filename(path);
        
        if (!is_ignored_file(filename)) {
            std::string real_path = get_real_path(path);
            
            // Check if already in queue (was added during create)
            if (!MagicFolderState::instance().is_hidden(filename)) {
                MagicFolderState::instance().add_to_queue(filename, real_path);
            }
            
            std::cout << "[MagicFolder] File closed, triggering classification: " << filename << std::endl;
            
            // TRIGGER CLASSIFICATION
            // Async (non-blocking) for bulk support
            MagicFolderState::instance().enqueue_for_classification(filename);
        }
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
    
    // Initialize ZeroMQ
    MagicFolderState::instance().init_zmq();
    
    std::cout << "[MagicFolder] Filesystem initialized!" << std::endl;
    std::cout << "[MagicFolder] Backing store: " << MagicFolderState::instance().backing_store << std::endl;
    
    return nullptr;
}

static void magic_destroy(void* private_data) {
    (void) private_data;
    std::cout << "[MagicFolder] Filesystem unmounted." << std::endl;
    MagicFolderState::instance().shutdown();
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
    .opendir    = magic_opendir,
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
