# Duplicate File Finder (Windows Desktop Application)

A modern, fast, and safe Windows desktop application to find and remove duplicate files using **Python**, **Flask**, **PyWebView**, and **SHA-256** cryptographic hashing.

Built with clean architecture, simple Python code, and zero unnecessary dependencies—ideal for learning and daily practical use.

---

## 1. Project Overview & Architecture

### High-Level Architecture

The application combines web technologies with native desktop capabilities using a 3-layer architecture:

```
┌────────────────────────────────────────────────────────┐
│            Native Windows Application Window           │
│                       (PyWebView)                      │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Frontend User Interface (HTML / CSS)     │  │
│  │   - Modern Dashboard Cards                       │  │
│  │   - Folder Picker & Scan Controls                │  │
│  │   - Duplicate Groups Table & Checkboxes          │  │
│  │   - Confirmation Modal Dialog                    │  │
│  └────────────────────────▲─────────────────────────┘  │
└───────────────────────────┼────────────────────────────┘
                            │ Standard HTTP JSON API
                            │ (Localhost 127.0.0.1)
┌───────────────────────────▼────────────────────────────┐
│                    Flask Web Server                    │
│   - Serves HTML / CSS / Assets                         │
│   - /api/browse-folder (Native Windows Picker)         │
│   - /api/scan          (Initiates Directory Scan)      │
│   - /api/delete        (Enforces Safe Deletion Rules)  │
└───────────────────────────▲────────────────────────────┘
                            │ Direct Python Calls
┌───────────────────────────▼────────────────────────────┐
│                  Core Engine (scanner.py)              │
│   - Recursive Directory Traversal                      │
│   - Step 1: File Size Pre-Grouping (Optimization)      │
│   - Step 2: Chunked SHA-256 Cryptographic Hashing      │
│   - Step 3: Duplicate Group Assembly                   │
│   - Step 4: Strict Deletion Safety & Original Guard    │
└────────────────────────────────────────────────────────┘
```

---

## 2. File Responsibilities

| File / Folder | Responsibility |
|---|---|
| `main.py` | **Desktop Entry Point**: Starts the background Flask server, waits for the health check, creates and opens the native desktop window via `pywebview`, and handles clean shutdown when the window is closed. |
| `app.py` | **Flask Web Application & API**: Serves the UI templates, exposes REST endpoints (`/api/scan`, `/api/browse-folder`, `/api/delete`, `/api/health`), handles PyInstaller path extraction (`sys._MEIPASS`), and tracks session state. |
| `scanner.py` | **Core Scanning & Hashing Engine**: Contains the logic for traversing folders recursively, grouping files by size, calculating SHA-256 hashes in memory-efficient chunks, and safely deleting redundant copies while preserving originals. |
| `templates/index.html` | **Frontend Template**: Clean, semantic HTML structure containing top navigation, dashboard summary metrics, folder picker, organized duplicate group tables, and the confirmation modal dialog. |
| `static/style.css` | **Light-Theme Stylesheet**: Modern desktop styling with subtle shadows, card layouts, status badges, custom buttons, and responsive grid—all with zero external CDN dependencies (works 100% offline). |
| `assets/icon.ico` | **Application Icon**: High-resolution multi-size Windows icon used in the window title bar and compiled `.exe`. |
| `requirements.txt` | **Dependencies List**: Specifies required Python packages (`Flask`, `pywebview`, `pyinstaller`). |
| `README.md` | **Documentation & Educational Guide**: Comprehensive project guide, architecture explanations, and setup instructions. |

---

## 3. How the Application Works

### Step-by-Step Execution Flow

1. **Launch**: Running `python main.py` triggers `main.py`.
2. **Port Allocation**: The app finds a free local port on `127.0.0.1` to avoid port collisions.
3. **Flask Startup**: Flask starts in a background daemon thread (`ServerThread`).
4. **Health Check Synchronization**: `main.py` polls `http://127.0.0.1:<port>/api/health` until HTTP 200 is returned.
5. **Window Initialization**: PyWebView opens a native desktop window loading the Flask URL.
6. **Folder Selection**:
   - The user clicks **Browse Folder**.
   - Frontend sends `POST /api/browse-folder`.
   - Flask invokes Windows's native folder dialog and returns the path.
7. **Scanning & SHA-256 Identification**:
   - The user clicks **Scan For Duplicates**.
   - Frontend sends `POST /api/scan` with the directory path.
   - `scanner.py` walks the folder recursively.
   - Files are grouped by byte size first. Unique file sizes are skipped immediately.
   - For files with matching sizes, SHA-256 hashes are calculated in 64 KB chunks.
   - Files with identical hashes are grouped together.
8. **Results Display**:
   - Flask returns the groups and summary statistics as JSON.
   - Frontend renders duplicate groups with file details, sizes, dates, and checkboxes.
   - The oldest file in each group is automatically designated and protected as **ORIGINAL (KEEP)**.
9. **Safe Deletion**:
   - The user selects files or clicks **Select All Duplicates**.
   - The user clicks **Delete Selected**.
   - A modal dialog appears showing the exact number of files and space to be reclaimed.
   - Upon confirmation, frontend sends `POST /api/delete`.
   - Backend validates every file:
     - Must be inside the scanned folder (path traversal prevention).
     - Must exist.
     - **Safety Rule Enforced**: At least one original copy per group is preserved, even if the user selected all files in a group.
   - Files are deleted with `os.remove()`, and the UI refreshes with the updated statistics.

---

## 4. Why SHA-256 for Duplicate Detection?

### 1. Cryptographic Guarantee
SHA-256 (Secure Hash Algorithm 256-bit) produces a 64-character hexadecimal digest representing the file's contents. If two files have the exact same SHA-256 hash, their contents are mathematically identical. File names, creation dates, or extensions do not affect the hash—only the raw bytes matter.

### 2. Two-Stage Optimization (Size Pre-Grouping)
Calculating hashes for thousands of files on disk can take time. To optimize this:
- **Stage 1 (Fast)**: Group all files by exact byte size using `os.stat().st_size`. If only one file has a size of 1,048,576 bytes, it **cannot** have a duplicate. We never read or hash that file!
- **Stage 2 (Precise)**: Only files that share the exact same byte size (2 or more files) are read and hashed with SHA-256.

### 3. Chunked Streaming
Files are read in 64 KB (`65536` bytes) chunks. This ensures that hashing large multi-gigabyte files (such as videos or ISO images) consumes only a few kilobytes of RAM.

---

## 5. File Safety Features

File deletion is permanent, so multiple layers of safety are implemented:

- **Never Automatic**: Files are never deleted without explicit manual confirmation in a modal dialog.
- **Original Preservation**: Even if a user checks every single file in a duplicate group, the backend detects this and protects the original copy.
- **Path Traversal Protection**: Every file path requested for deletion is verified using `pathlib.Path.resolve().relative_to(base_folder)`. Files outside the scanned folder cannot be touched.
- **Symlink Protection**: Directory walking uses `os.walk(..., followlinks=False)` to prevent following shortcuts or symlinks outside the selected folder.
- **Graceful Error Handling**: If a file is locked by Windows (e.g., opened in another program) or restricted by permissions, the app logs the error and continues safely without crashing.

---

## 6. Installation & Development

### Prerequisites
- Windows 10 or Windows 11
- Python 3.10 or newer

### Installation Steps

1. Clone or extract the project directory:
   ```cmd
   cd duplicate-file-finder
   ```

2. Install dependencies:
   ```cmd
   pip install -r requirements.txt
   ```

### Running in Development

**Desktop Mode (PyWebView native desktop window):**
```cmd
python main.py
```

**Web Mode (Run Flask in your default web browser for quick styling/debugging):**
```cmd
python app.py
```
Then visit `http://127.0.0.1:5000` in your browser.

---

## 7. Packaging as a Windows Executable

PyInstaller bundles Python, Flask, PyWebView, HTML templates, CSS, and the application icon into a standalone `.exe` that runs without requiring Python to be installed.

### PyInstaller Build Command

Run the following command from the project root directory:

```cmd
python -m PyInstaller --onefile --noconsole --name "DuplicateFileFinder" --icon "assets/icon.ico" --add-data "templates;templates" --add-data "static;static" --add-data "assets;assets" main.py
```

### Explanation of Flags:
- `--onefile`: Packages everything into a single, portable `.exe` file.
- `--noconsole`: Hides the background black command prompt window so it looks like a clean desktop application.
- `--name "DuplicateFileFinder"`: Sets the executable output name.
- `--icon "assets/icon.ico"`: Applies the custom application icon to the Windows executable.
- `--add-data "templates;templates"`: Bundles the HTML templates folder.
- `--add-data "static;static"`: Bundles CSS and static files.
- `--add-data "assets;assets"`: Bundles application icons.

The finished executable will be created at:
```
dist/DuplicateFileFinder.exe
```

---

## 8. Learning & ChatGPT Review Notes

If you are reviewing this code with a mentor or uploading to ChatGPT:
- Examine `scanner.py` to see how `hashlib.sha256()` reads streams in binary mode (`"rb"`).
- Examine `app.py` to see how Flask serves both standard web pages (`render_template`) and JSON APIs (`jsonify`).
- Examine `main.py` to understand the threading model: why Flask runs in a daemon thread while PyWebView controls the main thread UI event loop.

