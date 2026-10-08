#!/usr/bin/env python3
import os
import re
import sys

TARGET_DIRECTORIES = [
    "/media/myfiles/Hollywood Movies",
    "/media/myfiles/Bollywood Movies",
]

MEDIA_EXTENSIONS = {".mkv", ".mp4", ".avi", ".webm", ".ts", ".m4v", ".srt"}

def clean_dots(name):
    base, ext = os.path.splitext(name)
    cleaned_base = base.replace(".", " ")
    cleaned_base = re.sub(r"\s+", " ", cleaned_base).strip()
    return f"{cleaned_base}{ext}"

def rename_media_in_dir(directory):
    if not os.path.exists(directory):
        print(f"[Skip] Directory not found: {directory}")
        return

    print(f"\nScanning: {directory} ...")
    count = 0
    for root, dirs, files in os.walk(directory, topdown=False):
        # 1. Rename files
        for filename in files:
            if filename.endswith(".crdownload") or filename.endswith(".part") or filename.endswith(".tmp"):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext in MEDIA_EXTENSIONS:
                base = os.path.splitext(filename)[0]
                if "." in base:
                    new_filename = clean_dots(filename)
                    old_path = os.path.join(root, filename)
                    new_path = os.path.join(root, new_filename)
                    if old_path != new_path:
                        try:
                            os.rename(old_path, new_path)
                            print(f"[Renamed File] '{filename}' -> '{new_filename}'")
                            count += 1
                        except Exception as e:
                            print(f"[Error] Failed to rename '{filename}': {e}")

        # 2. Rename directories if they have dots in them
        for dirname in dirs:
            if "." in dirname:
                cleaned_dirname = re.sub(r"\s+", " ", dirname.replace(".", " ")).strip()
                old_dir = os.path.join(root, dirname)
                new_dir = os.path.join(root, cleaned_dirname)
                if old_dir != new_dir:
                    try:
                        os.rename(old_dir, new_dir)
                        print(f"[Renamed Folder] '{dirname}' -> '{cleaned_dirname}'")
                        count += 1
                    except Exception as e:
                        print(f"[Error] Failed to rename folder '{dirname}': {e}")

    print(f"Finished {directory}: {count} item(s) renamed.")

def main():
    dirs = sys.argv[1:] if len(sys.argv) > 1 else TARGET_DIRECTORIES
    for d in dirs:
        rename_media_in_dir(d)
    print("\nAll done! In Jellyfin, go to Dashboard -> Libraries -> Scan All Libraries.")

if __name__ == "__main__":
    main()
