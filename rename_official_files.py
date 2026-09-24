import pandas as pd
import os
import shutil
from pathlib import Path

def copy_with_new_names():
    # Read the mapping CSV
    mappings = pd.read_csv("dataset-copy/new-to-old-mappings-copy.csv")
    
    # Create the destination directory
    output_dir = "official_anon_images"
    os.makedirs(output_dir, exist_ok=True)
    print(f"Created directory: {output_dir}")
    
    copied_count = 0
    missing_count = 0
    
    for _, row in mappings.iterrows():
        old_filename = row['old_filename']
        new_filename = row['new_filename']
        
        # Source path (original file in pydicom-images-1)
        source_path = f"pydicom-images-1/{old_filename}"
        
        # Destination path (new filename in official_anon_images)
        dest_path = os.path.join(output_dir, new_filename)
        
        # Copy file if source exists
        if os.path.exists(source_path):
            try:
                shutil.copy2(source_path, dest_path)
                copied_count += 1
                if copied_count % 100 == 0:  # Progress update every 100 files
                    print(f"Copied {copied_count} files...")
            except Exception as e:
                print(f"Error copying {old_filename} -> {new_filename}: {e}")
        else:
            print(f"Source file not found: {source_path}")
            missing_count += 1
    
    print(f"\nCopy operation complete!")
    print(f"Successfully copied: {copied_count} files")
    print(f"Missing files: {missing_count} files")
    print(f"Files are now in: {output_dir}")

if __name__ == "__main__":
    copy_with_new_names()