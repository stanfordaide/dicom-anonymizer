import pydicom
import os
import pandas as pd

def extract_all_dicom_metadata(folder_path, output_csv="all_dicom_metadata_3.csv"):
    """Extract all DICOM headers and values from all images in folder, only keeping tags with at least one non-empty-string value."""
    
    all_metadata = []
    tag_value_tracker = dict()  # Track if a tag ever has a non-empty-string value
    
    # Add these fields to skip (large binary fields)
    SKIP_TAGS = {
        'PixelData',           # The actual image data
        'OverlayData',         # Overlay pixel data
        'WaveformData',        # Waveform data
        'EncapsulatedDocument', # Embedded documents
        'CurveData',           # Curve data
        'SpectroscopyData',    # Spectroscopy data
        'FloatPixelData',      # Float pixel data
        'DoubleFloatPixelData', # Double float pixel data
        'PrivateCreator',      # Often contains large private data
    }
    
    print(f"Processing DICOM files in: {folder_path}")
    
    # First pass: collect all files
    dicom_files = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.dcm'):
                filepath = os.path.join(root, file)
                dicom_files.append(filepath)
    
    print(f"Found {len(dicom_files)} DICOM files")
    
    # Process each DICOM file
    for i, filepath in enumerate(dicom_files):
        try:
            ds = pydicom.dcmread(filepath)
            
            # Create metadata dictionary for this file
            metadata = {
                'filename': os.path.basename(filepath)
            }
            
            # Recursively extract all tags
            def extract_tags(dataset, prefix=""):
                for element in dataset:
                    keyword = element.keyword if element.keyword else f"Tag_{element.tag}"
                    full_keyword = f"{prefix}{keyword}"
                    
                    # Skip known large binary fields
                    if keyword in SKIP_TAGS:
                        continue
                    
                    # Handle different data types
                    if element.VR == 'SQ':  # Sequence
                        for j, seq_item in enumerate(element.value):
                            extract_tags(seq_item, f"{full_keyword}_Seq{j}_")
                    else:
                        try:
                            if hasattr(element, 'value'):
                                if isinstance(element.value, bytes):
                                    # Skip if bytes are too large
                                    if len(element.value) > 1000:  # Skip if > 1KB
                                        value = f"<BINARY_DATA_{len(element.value)}_BYTES>"
                                    else:
                                        value = str(element.value.decode('utf-8', errors='ignore'))
                                elif isinstance(element.value, pydicom.multival.MultiValue):
                                    value = str(list(element.value))
                                else:
                                    value = str(element.value)
                                    # Truncate very long strings
                                    if len(value) > 1000:  # Limit to 1000 characters
                                        value = value[:1000] + "...<TRUNCATED>"
                            else:
                                value = str(element)
                                # Truncate very long strings
                                if len(value) > 1000:
                                    value = value[:1000] + "...<TRUNCATED>"
                        except:
                            value = "ERROR_READING_VALUE"
                        
                        # Only add to metadata if not an empty string
                        if value != "":
                            metadata[full_keyword] = value
                            # Track if this tag ever has a non-empty-string value
                            tag_value_tracker[full_keyword] = True
                        else:
                            # If not already marked as True, mark as False
                            if full_keyword not in tag_value_tracker:
                                tag_value_tracker[full_keyword] = False
            
            extract_tags(ds)
            all_metadata.append(metadata)
            
            if (i + 1) % 100 == 0:
                print(f"Processed {i + 1}/{len(dicom_files)} files")
                
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
            metadata = {
                'filename': os.path.basename(filepath),
                'ERROR': str(e)
            }
            all_metadata.append(metadata)
    
    # Only keep columns (tags) that had at least one non-empty-string value
    valid_tags = {tag for tag, has_value in tag_value_tracker.items() if has_value}
    print(f"Keeping {len(valid_tags)} tags with at least one non-empty-string value.")
    
    # Convert to DataFrame
    df = pd.DataFrame(all_metadata)
    keep_cols = ['filename'] + [col for col in df.columns if col in valid_tags]
    df = df[keep_cols]
    
    # Save to CSV
    df.to_csv(output_csv, index=False)
    print(f"Saved metadata to: {output_csv}")
    print(f"Total files processed: {len(all_metadata)}")
    print(f"Total unique DICOM tags kept: {len(valid_tags)}")
    
    return df

if __name__ == "__main__":
    anon_folder = "dataset/images"
    print("Extracting ALL DICOM metadata...")
    metadata_df = extract_all_dicom_metadata(anon_folder, "dataset/new_dicom_metadata.csv")
    print(f"\nComplete! CSV shape: {metadata_df.shape} (rows x columns)")