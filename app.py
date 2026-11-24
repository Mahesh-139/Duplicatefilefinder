"""
app.py - Flask Web Application and Backend API

This file creates the Flask application and defines the HTTP routes:
1. Serving the desktop UI (index.html, style.css).
2. Providing API endpoints for folder selection, scanning, and safe deletion.
3. Managing PyInstaller path extraction so static assets and templates work
   both in development and when packaged into an executable.
"""

import os
import sys
from flask import Flask, render_template, request, jsonify

# Import the core scanner functionality
import scanner

# ---------------------------------------------------------------------------
# Path Resolution for PyInstaller Bundling
# ---------------------------------------------------------------------------
# When packaged with PyInstaller, temporary files are unpacked into sys._MEIPASS.
# In normal development, files are located relative to this script.
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR
)

# ---------------------------------------------------------------------------
# In-Memory Application State
# ---------------------------------------------------------------------------
# Keeps track of the last scan results on the backend so deletion requests
# can be strictly validated against real duplicate groups.
scan_state = {
    "base_directory": "",
    "groups": [],
    "summary": {}
}


@app.route("/")
def index():
    """Render and serve the main desktop dashboard interface."""
    return render_template("index.html")


@app.route("/api/health")
def health_check():
    """
    Health check endpoint.
    PyWebView polls this endpoint to know when the Flask server is ready.
    """
    return jsonify({"status": "ready"})


@app.route("/api/browse-folder", methods=["POST"])
def browse_folder():
    """
    Open the native Windows folder selection dialog.
    Returns the selected folder path to the frontend.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        # Create a hidden Tkinter root window
        root = tk.Tk()
        root.withdraw()
        # Bring the folder dialog to the top of all windows
        root.attributes("-topmost", True)
        
        selected_folder = filedialog.askdirectory(title="Select Folder to Scan for Duplicates")
        root.destroy()

        if selected_folder:
            # Normalize path for Windows
            normalized_path = os.path.normpath(selected_folder)
            return jsonify({"success": True, "folder": normalized_path})
        else:
            return jsonify({"success": False, "cancelled": True})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to open folder picker: {str(e)}"})


@app.route("/api/scan", methods=["POST"])
def scan_folder():
    """
    Scan a selected directory for duplicate files.
    Expects JSON: { "folder": "C:\\path\\to\\directory" }
    """
    data = request.get_json() or {}
    folder_path = data.get("folder", "").strip()

    if not folder_path:
        return jsonify({"success": False, "error": "Please provide a folder path to scan."}), 400

    # Execute the scanning process from scanner.py
    result = scanner.scan_for_duplicates(folder_path)

    if result.get("success"):
        # Save scan results in memory for subsequent safe deletion validation
        scan_state["base_directory"] = result.get("base_directory", "")
        scan_state["groups"] = result.get("groups", [])
        scan_state["summary"] = result.get("summary", {})

    return jsonify(result)


@app.route("/api/delete", methods=["POST"])
def delete_duplicates():
    """
    Safely delete selected duplicate files.
    Expects JSON: { "folder": "C:\\path", "files": ["C:\\path\\file1.jpg", ...] }
    """
    data = request.get_json() or {}
    folder_path = data.get("folder", "").strip()
    files_to_delete = data.get("files", [])

    if not folder_path or not files_to_delete:
        return jsonify({"success": False, "error": "Missing folder or files selection."}), 400

    # Ensure the folder matches the current scan state
    if os.path.normpath(folder_path) != os.path.normpath(scan_state.get("base_directory", "")):
        return jsonify({
            "success": False,
            "error": "The folder does not match the active scan session. Please rescan."
        }), 400

    # Perform deletion using our secure scanner function
    deletion_result = scanner.delete_selected_files(
        folder_path=folder_path,
        files_to_delete=files_to_delete,
        current_groups=scan_state.get("groups", [])
    )

    # After deletion, refresh the scan results so the frontend gets the latest state
    if deletion_result.get("success") and deletion_result.get("deleted_count", 0) > 0:
        refreshed_scan = scanner.scan_for_duplicates(folder_path)
        if refreshed_scan.get("success"):
            scan_state["groups"] = refreshed_scan.get("groups", [])
            scan_state["summary"] = refreshed_scan.get("summary", {})
            deletion_result["updated_data"] = refreshed_scan

    return jsonify(deletion_result)


if __name__ == "__main__":
    # Allows running app.py directly for development / browser testing
    app.run(host="127.0.0.1", port=5000, debug=True)

