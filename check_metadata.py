import pydicom

def check_tag(dicom_filepath, tag):
    """
    Check the content of a specific DICOM tag
    
    Args:
        dicom_filepath (str): Path to the DICOM file
        tag: DICOM tag - can be:
             - Tuple like (0x0008, 0x0090) 
             - String like "00080090"
             - Keyword like "ReferringPhysicianName"
    
    Returns:
        dict: Contains tag info and value, or error message
    """
    try:
        ds = pydicom.dcmread(dicom_filepath)
        
        # Handle different tag input formats
        if isinstance(tag, str):
            if len(tag) == 8 and tag.isalnum():  # Format like "00080090"
                tag_tuple = (int(tag[:4], 16), int(tag[4:], 16))
            else:  # Assume it's a keyword
                if hasattr(ds, tag):
                    element = getattr(ds, tag)
                    return {
                        'file': dicom_filepath,
                        'tag_keyword': tag,
                        'tag_hex': str(element.tag),
                        'tag_name': element.name,
                        'vr': element.VR,
                        'value': str(element.value) if hasattr(element, 'value') else 'No value',
                        'exists': True
                    }
                else:
                    return {
                        'file': dicom_filepath,
                        'tag_keyword': tag,
                        'exists': False,
                        'error': f"Tag '{tag}' not found in DICOM file"
                    }
        else:  # Assume it's a tuple like (0x0008, 0x0090)
            tag_tuple = tag
        
        # Check if tag exists
        if tag_tuple in ds:
            element = ds[tag_tuple]
            return {
                'file': dicom_filepath,
                'tag_hex': str(element.tag),
                'tag_name': element.name,
                'tag_keyword': element.keyword,
                'vr': element.VR,
                'value': str(element.value) if hasattr(element, 'value') else 'No value',
                'raw_value': element.value if hasattr(element, 'value') else None,
                'exists': True
            }
        else:
            return {
                'file': dicom_filepath,
                'tag_hex': f"({tag_tuple[0]:04X},{tag_tuple[1]:04X})",
                'exists': False,
                'error': f"Tag {tag_tuple} not found in DICOM file"
            }
            
    except Exception as e:
        return {
            'file': dicom_filepath,
            'exists': False,
            'error': f"Error reading DICOM file: {str(e)}"
        }

def check_tag_multiple_files(dicom_folder, tag):
    """Check a specific tag across multiple DICOM files"""
    import os
    
    results = []
    for root, _, files in os.walk(dicom_folder):
        for file in files:
            if file.endswith('.dcm'):
                filepath = os.path.join(root, file)
                result = check_tag(filepath, tag)
                results.append(result)
    
    return results

def print_tag_summary(results):
    """Print a summary of tag checking results"""
    print(f"\nTag Check Summary ({len(results)} files):")
    print("-" * 60)
    
    existing_count = 0
    unique_values = set()
    
    for result in results:
        if result['exists']:
            existing_count += 1
            if 'value' in result:
                unique_values.add(result['value'])
            print(f"✓ {result['file']}: {result.get('value', 'No value')}")
        else:
            print(f"✗ {result['file']}: {result.get('error', 'Not found')}")
    
    print(f"\nSummary:")
    print(f"- Files with tag: {existing_count}/{len(results)}")
    print(f"- Unique values: {len(unique_values)}")
    if unique_values:
        print(f"- Values found: {list(unique_values)}")

# Example usage functions
if __name__ == "__main__":
    # Example 1: Check single file, single tag
    result = check_tag("data_analysis/dataset_creation/anonymizer/CTP/output/__default/ST-9611974235664919637/FO-16944319892516169818.dcm", "ReferringPhysicianName")
    print(result)
    
    # Example 2: Check single file with hex tag
    result = check_tag("data_analysis/dataset_creation/anonymizer/CTP/output/__default/ST-9611974235664919637/FO-16944319892516169818.dcm", "00080090")
    print(result)
    
    # Example 3: Check single file with tuple tag
    result = check_tag("data_analysis/dataset_creation/anonymizer/CTP/output/__default/ST-9611974235664919637/FO-16944319892516169818.dcm", (0x0008, 0x0090))
    print(result)
    
    # Example 4: Check multiple files
    results = check_tag_multiple_files("data_analysis/dataset_creation/anonymizer/CTP/output/__default/ST-9611974235664919637/FO-16944319892516169818.dcm", "ReferringPhysicianName")
    print_tag_summary(results)