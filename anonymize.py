# import pandas as pd
# import pydicom
# import os
# import re
# import hashlib
# from pathlib import Path
# from pydicom.uid import generate_uid

# # DICOM tags that cannot be removed or emptied (Type 1 - Required)
# type_ones = [
#     "SpecificCharacterSet",
#     "ProcedureCodeSequence_Seq0_CodeValue",
#     "ProcedureCodeSequence_Seq0_CodingSchemeDesignator",
#     "ProcedureCodeSequence_Seq0_CodeMeaning",
#     "RequestedProcedureCodeSequence_Seq0_CodeValue",
#     "RequestedProcedureCodeSequence_Seq0_CodingSchemeDesignator",
#     "RequestedProcedureCodeSequence_Seq0_CodeMeaning",
#     "PerformedProtocolCodeSequence_Seq0_CodeValue",
#     "PerformedProtocolCodeSequence_Seq0_CodingSchemeDesignator",
#     "PerformedProtocolCodeSequence_Seq0_CodeMeaning",
#     "BodyPartExamined",
#     "SOPClassUID",                    # (0008,0016)
#     "SOPInstanceUID",                 # (0008,0018)
#     "StudyDate",                      # (0008,0020)
#     "SeriesDate",                     # (0008,0021)
#     "AcquisitionDate",                # (0008,0022)
#     "ContentDate",                    # (0008,0023)
#     "StudyTime",                      # (0008,0030)
#     "SeriesTime",                     # (0008,0031)
#     "AcquisitionTime",                # (0008,0032)
#     "ContentTime",                    # (0008,0033)
#     "AccessionNumber",                # (0008,0050)
#     "Modality",                       # (0008,0060)
#     "Manufacturer",                   # (0008,0070)
#     "StudyInstanceUID",               # (0020,000D)
#     "SeriesInstanceUID",              # (0020,000E)
#     "StudyID",                        # (0020,0010)
#     "SeriesNumber",                   # (0020,0011)
#     "InstanceNumber",                 # (0020,0013)
#     "PatientOrientation",             # (0020,0020)
#     "ImagePositionPatient",           # (0020,0032)
#     "ImageOrientationPatient",        # (0020,0037)
#     "FrameOfReferenceUID",            # (0020,0052)
#     "SamplesPerPixel",                # (0028,0002)
#     "PhotometricInterpretation",      # (0028,0004)
#     "Rows",                           # (0028,0010)
#     "Columns",                        # (0028,0011)
#     "BitsAllocated",                  # (0028,0100)
#     "BitsStored",                     # (0028,0101)
#     "HighBit",                        # (0028,0102)
#     "PixelRepresentation",            # (0028,0103)
#     "PixelData",                      # (7FE0,0010)
#     "PixelSpacing",
#     "WindowCenter",                   # (0028,1050)
#     "WindowWidth",                    # (0028,1051)
#     "RescaleIntercept",               # (0028,1052)
#     "RescaleSlope",                   # (0028,1053)
#     "RescaleType"                     # (0028,1054)
# ]

# # DICOM tags that cannot be removed but can be emptied (Type 2 - Required but can be empty)
# type_twos = [
#     "ImageType",                      # (0008,0008)
#     "StudyDescription",               # (0008,1030) - MOVED HERE FROM type_ones
#     "SeriesDescription",              # (0008,103E)
#     "PatientName",                    # (0010,0010)
#     "PatientID",                      # (0010,0020)
#     "PatientBirthDate",               # (0010,0030)
#     "PatientSex",                     # (0010,0040)
#     "PatientAge",                     # (0010,1010)
#     "PatientWeight",                  # (0010,1030)
#     "PatientSize",                    # (0010,1020)
#     "PatientPosition",                # (0018,5100)
#     "SliceThickness",                 # (0018,0050)
#     "SpacingBetweenSlices",           # (0018,0088)
#     "SliceLocation",                  # (0020,1041)
#     "ImageComments",                  # (0020,4000)
#     "ProtocolName",                   # (0018,1030)
#     "InstitutionName",                # (0008,0080)
#     "InstitutionAddress",             # (0008,0081)
#     "ReferringPhysicianName",         # (0008,0090)
#     "PerformingPhysicianName",        # (0008,1050)
#     "OperatorsName",                  # (0008,1070)
#     "ManufacturerModelName",          # (0008,1090)
#     "DeviceSerialNumber",             # (0018,1000)
#     "SoftwareVersions",               # (0018,1020)
#     "StationName",                    # (0008,1010)
#     "RequestingPhysician",            # (0032,1032)
#     "RequestedProcedureDescription",  # (0032,1060)
# ]

# # Tags that should NOT be hashed (keep original values) - FIXED SYNTAX ERRORS
# no_hash_tags = [
#     "SpecificCharacterSet",
#     "StudyDescription",               # Keep for LPCH removal only
#     "ProcedureCodeSequence_Seq0_CodeValue",
#     "ProcedureCodeSequence_Seq0_CodingSchemeDesignator",
#     "ProcedureCodeSequence_Seq0_CodeMeaning",
#     "RequestedProcedureCodeSequence_Seq0_CodeValue",
#     "RequestedProcedureCodeSequence_Seq0_CodingSchemeDesignator",
#     "RequestedProcedureCodeSequence_Seq0_CodeMeaning",
#     "PerformedProtocolCodeSequence_Seq0_CodeValue",
#     "PerformedProtocolCodeSequence_Seq0_CodingSchemeDesignator",
#     "PerformedProtocolCodeSequence_Seq0_CodeMeaning",
#     "BodyPartExamined",
#     "SOPInstanceUID",                 # (0008,0018)
#     "Modality",                       # (0008,0060)
#     "SamplesPerPixel",                # (0028,0002)
#     "PhotometricInterpretation",      # (0028,0004)
#     "Rows",                           # (0028,0010)
#     "Columns",                        # (0028,0011)
#     "BitsAllocated",                  # (0028,0100)
#     "BitsStored",                     # (0028,0101)
#     "HighBit",                        # (0028,0102)
#     "PixelRepresentation",            # (0028,0103)
#     "PixelData",                      # (7FE0,0010)
#     "PatientOrientation",
#     "ImagePositionPatient",
#     "ImageOrientationPatient",
#     "SliceThickness",
#     "SpacingBetweenSlices",
#     "PixelSpacing",                   # FIXED: Added comma
#     "WindowCenter",                   # (0028,1050)
#     "WindowWidth",                    # (0028,1051)
#     "RescaleIntercept",               # (0028,1052)
#     "RescaleSlope",                   # (0028,1053)
#     "RescaleType"                     # (0028,1054)
# ]

# # Store mappings to ensure consistency
# patient_id_mapping = {}
# study_uid_mapping = {}
# series_uid_mapping = {}

# def get_consistent_hash(value, mapping_dict):
#     """Get consistent hash for repeated values"""
#     if value in mapping_dict:
#         return mapping_dict[value]
    
#     # Create new hash
#     hash_object = hashlib.sha256(str(value).encode())
#     hashed = hash_object.hexdigest()[:16]
#     mapping_dict[value] = hashed
#     return hashed

# def get_consistent_numeric_hash(value, mapping_dict, max_digits=12):
#     """Get consistent numeric hash for repeated values"""
#     if value in mapping_dict:
#         return mapping_dict[value]
    
#     # Generate numeric hash that fits IS VR constraints
#     hash_int = abs(hash(str(value))) % (10 ** max_digits - 1)
#     str_hash = str(hash_int)
#     mapping_dict[value] = str_hash
#     return str_hash

# def remove_lpch(value):
#     """Remove LPCH and LPCH - substrings from value"""
#     if isinstance(value, str):
#         original_value = value
#         # Remove LPCH with various spacing patterns
#         cleaned = value.replace("LPCH -", "").replace("LPCH", "").replace("- LPCH", "")
#         # Clean up extra spaces and dashes
#         cleaned = re.sub(r'\s+', ' ', cleaned)  # Replace multiple spaces with single space
#         cleaned = re.sub(r'^[\s\-]+|[\s\-]+$', '', cleaned)  # Remove leading/trailing spaces and dashes
        
#         if original_value != cleaned:
#             print(f"LPCH REMOVED: '{original_value}' -> '{cleaned}'")
        
#         return cleaned
#     return value

# def get_consistent_uid(original_uid, mapping_dict, prefix="1.2.840.113619."):
#     """Get consistent UID for repeated UIDs"""
#     if original_uid in mapping_dict:
#         return mapping_dict[original_uid]
    
#     # Generate new UID
#     new_uid = generate_uid(prefix=prefix)
#     mapping_dict[original_uid] = new_uid
#     return new_uid

# def get_anonymized_value(element, keyword):
#     """Get appropriately anonymized value based on element type and VR"""
#     original_value = element.value
    
#     # Handle UID fields specially
#     if keyword in ["StudyInstanceUID", "SeriesInstanceUID", "FrameOfReferenceUID"]:
#         if keyword == "StudyInstanceUID":
#             return get_consistent_uid(original_value, study_uid_mapping)
#         elif keyword == "SeriesInstanceUID":
#             return get_consistent_uid(original_value, series_uid_mapping)
#         else:
#             return generate_uid()
    
#     # Handle numeric fields that need to stay numeric
#     elif element.VR == 'IS':  # Integer String - max 12 chars, must be numeric
#         if keyword in ["StudyID", "SeriesNumber", "InstanceNumber"]:
#             # Generate a numeric hash that fits the constraints
#             return get_consistent_numeric_hash(original_value, {}, 12)
#         else:
#             return str(original_value)
    
#     elif element.VR == 'DS':  # Decimal String - must be numeric
#         # Keep original numeric values for technical parameters
#         return original_value
    
#     elif element.VR in ['FL', 'FD', 'SL', 'SS', 'UL', 'US']:  # Other numeric types
#         return original_value
    
#     # Handle date/time fields
#     elif element.VR == 'DA':  # Date
#         if keyword in ["StudyDate", "SeriesDate", "AcquisitionDate", "ContentDate"]:
#             return "20200101"  # Fixed anonymized date
#         else:
#             return original_value
    
#     elif element.VR == 'TM':  # Time
#         if keyword in ["StudyTime", "SeriesTime", "AcquisitionTime", "ContentTime"]:
#             return "120000.000000"
#         else:
#             return original_value
    
#     # Handle text fields - these can take hash strings
#     else:
#         if keyword == "PatientID":
#             return get_consistent_hash(original_value, patient_id_mapping)
#         elif keyword == "AccessionNumber":
#             return get_consistent_hash(original_value, {})
#         else:
#             return get_consistent_hash(original_value, {})

# def anonymize_dicom(input_path, output_path):
#     """Anonymize a single DICOM file"""
#     try:
#         ds = pydicom.dcmread(input_path)
#         elements_to_remove = []
        
#         # FIRST PASS: Remove LPCH from ALL elements
#         for element in ds.iterall():
#             if hasattr(element, 'value') and isinstance(element.value, str) and "LPCH" in element.value:
#                 original_value = element.value
#                 cleaned_value = remove_lpch(element.value)
#                 element.value = cleaned_value
#                 print(f"LPCH cleaned from {element.keyword or element.tag}: '{original_value}' -> '{cleaned_value}'")
        
#         # SECOND PASS: Handle anonymization by type
#         for element in ds.iterall():
#             keyword = element.keyword
                
#             if hasattr(element, 'value') and element.value is not None:
                
#                 # Handle Type 1 tags
#                 if keyword in type_ones:
#                     if keyword not in no_hash_tags:
#                         try:
#                             new_value = get_anonymized_value(element, keyword)
#                             element.value = new_value
#                             print(f"Anonymized {keyword} (VR: {element.VR})")
#                         except Exception as e:
#                             print(f"Error anonymizing {keyword}: {e}")
#                     # else: keep original value (in no_hash_tags)
                
#                 # Handle Type 2 tags (empty them, EXCEPT StudyDescription which keeps LPCH-cleaned value)
#                 elif keyword in type_twos:
#                     if keyword == "StudyDescription":
#                         # Keep the LPCH-cleaned value, don't empty it
#                         print(f"Kept StudyDescription with LPCH removed: '{element.value}'")
#                     else:
#                         try:
#                             # Set appropriate empty value based on VR
#                             if element.VR == 'IS':
#                                 element.value = ""
#                             elif element.VR == 'DS':
#                                 element.value = ""
#                             elif element.VR in ['FL', 'FD', 'SL', 'SS', 'UL', 'US']:
#                                 element.value = None
#                             else:
#                                 element.value = ""
#                             print(f"Emptied {keyword} (VR: {element.VR})")
#                         except Exception as e:
#                             print(f"Error emptying {keyword}: {e}")
                
#                 # Handle Type 3 tags (remove them)
#                 else:
#                     elements_to_remove.append(element.tag)
            
#             else:
#                 if keyword not in type_ones and keyword not in type_twos:
#                     elements_to_remove.append(element.tag)
        
#         # Remove Type 3 elements
#         for tag in elements_to_remove:
#             if tag in ds:
#                 try:
#                     del ds[tag]
#                 except Exception as e:
#                     print(f"Error removing tag {tag}: {e}")
        
#         # Save anonymized DICOM
#         os.makedirs(os.path.dirname(output_path), exist_ok=True)
#         ds.save_as(output_path)
#         print(f"Successfully anonymized: {os.path.basename(input_path)}")
        
#     except Exception as e:
#         print(f"Error processing {input_path}: {e}")

# def anonymize_folder(input_folder, output_folder):
#     """Anonymize all DICOM files in a folder"""
    
#     input_path = Path(input_folder)
#     output_path = Path(output_folder)
    
#     # Create output directory
#     output_path.mkdir(parents=True, exist_ok=True)
    
#     # Find all DICOM files
#     dicom_files = []
#     for root, dirs, files in os.walk(input_path):
#         for file in files:
#             if file.endswith('.dcm'):
#                 dicom_files.append(os.path.join(root, file))
    
#     print(f"Found {len(dicom_files)} DICOM files to process")
    
#     # Process each file
#     for i, dicom_file in enumerate(dicom_files):
#         # Preserve relative directory structure
#         rel_path = os.path.relpath(dicom_file, input_path)
#         output_file = output_path / rel_path
        
#         # Ensure output subdirectory exists
#         output_file.parent.mkdir(parents=True, exist_ok=True)
        
#         print(f"\nProcessing {i+1}/{len(dicom_files)}: {rel_path}")
#         anonymize_dicom(dicom_file, str(output_file))
    
#     print(f"\nAnonymization complete! Processed {len(dicom_files)} files")
#     print(f"Anonymized files saved to: {output_folder}")





# def get_tags_of_types(filepath_to_dicom_dict):
#     # keep as-is
#     type_ones = []
#     # keep but modify as a dict: { tag : action }
#     type_ones_to_modify = {}
#     # empty
#     type_twos = []
#     # remove completely
#     type_threes = []

#     # load the dicom data dict csv
#     dicom_data_dict = pd.read_csv(filepath_to_dicom_dict)
#     # read from the "Action_to_Take" column
#     for _, row in dicom_data_dict.iterrows():
#         action = row["Action_to_Take"]
#         if (action == "keep"):
#             type_ones.append(row["Tag"])
#         elif (action == "empty"):
#             type_twos.append(row["Tag"])
#         elif (action == "remove"):
#             type_threes.append(row["Tag"])
#         else:
#             type_ones_to_modify[row["Tag"]] = action
    
#     return type_ones, type_ones_to_modify, type_twos, type_threes

# if __name__ == "__main__":
#     # get info on what to do with each tag
#     type_ones, _, type_twos, type_threes = get_tags_of_types("dicom-data-dict.csv")
#     custom_type_ones = {
#         "ContentDate" : "random jitter",
#         "PatientID" : "hash",
#         "ContributingEquipmentSequence_Seq0_Manufacturer" : "hash",
#         "StudyInstanceUID" : "hash",
#         "SeriesInstanceUID" : "hash",
#         "FilterMaterial" : "RHODIUM",
#         "CollimatorLeftVerticalEdge" : "0",
#         "CollimatorRightVerticalEdge" : "0",
#         "CollimatorUpperHorizontalEdge" : "0",
#         "CollimatorLowerHorizontalEdge" : "0",
#         "ShutterShape" : "RECTANGULAR",
#         "DistanceSourceToIsocenter" : "1",
#         "Trim" : "1",
#         "RadiationSetting" : "SC"
#     }

#     input_folder = "images/"
#     output_folder = "pydicom-images/"

import pandas as pd
import pydicom
import os
import re
import hashlib
import random
from pathlib import Path
from pydicom.uid import generate_uid
from datetime import datetime, timedelta

# Store mappings to ensure consistency
patient_id_mapping = {}
study_uid_mapping = {}
series_uid_mapping = {}
date_jitter_mapping = {}

def get_consistent_hash(value, mapping_dict):
    """Get consistent hash for repeated values"""
    if value in mapping_dict:
        return mapping_dict[value]
    
    # Create new hash
    hash_object = hashlib.sha256(str(value).encode())
    hashed = hash_object.hexdigest()[:16]
    mapping_dict[value] = hashed
    return hashed

def get_consistent_numeric_hash(value, mapping_dict, max_digits=12):
    """Get consistent numeric hash for repeated values"""
    if value in mapping_dict:
        return mapping_dict[value]
    
    # Generate numeric hash that fits IS VR constraints
    hash_int = abs(hash(str(value))) % (10 ** max_digits - 1)
    str_hash = str(hash_int)
    mapping_dict[value] = str_hash
    return str_hash

def get_jittered_date(original_date, patient_id):
    """Apply consistent date jitter per patient"""
    if patient_id in date_jitter_mapping:
        jitter_days = date_jitter_mapping[patient_id]
    else:
        # Generate random jitter between -30 and +30 days per patient
        jitter_days = random.randint(-30, 30)
        date_jitter_mapping[patient_id] = jitter_days
    
    try:
        # Parse original date (format: YYYYMMDD)
        original = datetime.strptime(str(original_date), '%Y%m%d')
        jittered = original + timedelta(days=jitter_days)
        return jittered.strftime('%Y%m%d')
    except:
        return str(original_date)  # Return original if parsing fails

def remove_lpch(value):
    """Remove LPCH and LPCH - substrings from value"""
    if isinstance(value, str):
        original_value = value
        # Remove LPCH with various spacing patterns
        cleaned = value.replace("LPCH -", "").replace("LPCH", "").replace("- LPCH", "")
        # Clean up extra spaces and dashes
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = re.sub(r'^[\s\-]+|[\s\-]+$', '', cleaned)
        
        if original_value != cleaned:
            print(f"LPCH REMOVED: '{original_value}' -> '{cleaned}'")
        
        return cleaned
    return value

def get_consistent_uid(original_uid, mapping_dict, prefix="1.2.840.113619."):
    """Get consistent UID for repeated UIDs"""
    if original_uid in mapping_dict:
        return mapping_dict[original_uid]
    
    # Generate new UID
    new_uid = generate_uid(prefix=prefix)
    mapping_dict[original_uid] = new_uid
    return new_uid

def apply_custom_action(element, keyword, action, patient_id=None):
    """Apply custom action to element based on action type"""
    original_value = element.value
    
    if action == "hash":
        # Hash the value
        if keyword == "PatientID":
            new_value = get_consistent_hash(original_value, patient_id_mapping)
        elif keyword in ["StudyInstanceUID", "SeriesInstanceUID"]:
            if keyword == "StudyInstanceUID":
                new_value = get_consistent_uid(original_value, study_uid_mapping)
            else:
                new_value = get_consistent_uid(original_value, series_uid_mapping)
        else:
            new_value = get_consistent_hash(original_value, {})
        
        element.value = new_value
        print(f"Hashed {keyword}: '{original_value}' -> '{new_value}'")
    
    elif action == "random jitter":
        # Apply date jitter
        if patient_id:
            new_value = get_jittered_date(original_value, patient_id)
            element.value = new_value
            print(f"Jittered {keyword}: '{original_value}' -> '{new_value}'")
        else:
            print(f"Cannot jitter {keyword}: no patient ID available")
    
    else:
        # Replace with literal value
        element.value = action
        print(f"Replaced {keyword}: '{original_value}' -> '{action}'")

def anonymize_dicom(input_path, output_path, type_ones, type_ones_to_modify, type_twos, type_threes, custom_type_ones):
    """Anonymize a single DICOM file based on configuration"""
    try:
        ds = pydicom.dcmread(input_path)
        elements_to_remove = []
        
        # Get PatientID for consistent jittering
        patient_id = None
        if hasattr(ds, 'PatientID') and ds.PatientID:
            patient_id = ds.PatientID
        
        # FIRST PASS: Remove LPCH from ALL elements
        for element in ds.iterall():
            if hasattr(element, 'value') and isinstance(element.value, str) and "LPCH" in element.value:
                original_value = element.value
                cleaned_value = remove_lpch(element.value)
                element.value = cleaned_value
                print(f"LPCH cleaned from {element.keyword or element.tag}: '{original_value}' -> '{cleaned_value}'")
        
        # SECOND PASS: Handle anonymization by type - ONLY for tags explicitly listed in CSV
        for element in ds.iterall():
            keyword = element.keyword
            
            if hasattr(element, 'value') and element.value is not None:
                
                # Handle custom actions first (highest priority)
                if keyword in custom_type_ones:
                    action = custom_type_ones[keyword]
                    apply_custom_action(element, keyword, action, patient_id)
                
                # Handle Type 1 tags that need modification
                elif keyword in type_ones_to_modify:
                    action = type_ones_to_modify[keyword]
                    apply_custom_action(element, keyword, action, patient_id)
                
                # Handle Type 1 tags (keep as-is)
                elif keyword in type_ones:
                    # Keep original value
                    print(f"Kept {keyword}: '{element.value}'")
                
                # Handle Type 2 tags (empty them)
                elif keyword in type_twos:
                    try:
                        # Set appropriate empty value based on VR
                        if element.VR == 'IS':
                            element.value = ""
                        elif element.VR == 'DS':
                            element.value = ""
                        elif element.VR in ['FL', 'FD', 'SL', 'SS', 'UL', 'US']:
                            element.value = None
                        else:
                            element.value = ""
                        print(f"Emptied {keyword} (VR: {element.VR})")
                    except Exception as e:
                        print(f"Error emptying {keyword}: {e}")
                
                # Handle Type 3 tags (remove them) - ONLY if explicitly in type_threes list
                elif keyword in type_threes:
                    elements_to_remove.append(element.tag)
                    print(f"Marked for removal: {keyword} ({element.tag})")
                
                # CHANGED: For all other tags (not in CSV), do nothing - leave as-is
                # This includes PixelData and any other tags not mentioned in the CSV
                else:
                    # Do nothing - leave the tag untouched
                    pass
            
            else:
                # Empty elements - only remove if explicitly in type_threes list
                if keyword in type_threes:
                    elements_to_remove.append(element.tag)
        
        # Remove only the explicitly marked elements
        for tag in elements_to_remove:
            if tag in ds:
                try:
                    del ds[tag]
                    print(f"Removed tag: {tag}")
                except Exception as e:
                    print(f"Error removing tag {tag}: {e}")
        
        # Save anonymized DICOM
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        ds.save_as(output_path)
        print(f"Successfully anonymized: {os.path.basename(input_path)}")
        
    except Exception as e:
        print(f"Error processing {input_path}: {e}")


def anonymize_folder(input_folder, output_folder, type_ones, type_ones_to_modify, type_twos, type_threes, custom_type_ones):
    """Anonymize all DICOM files in a folder"""
    
    input_path = Path(input_folder)
    output_path = Path(output_folder)
    
    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Find all DICOM files
    dicom_files = []
    for root, dirs, files in os.walk(input_path):
        for file in files:
            if file.endswith('.dcm'):
                dicom_files.append(os.path.join(root, file))
    
    print(f"Found {len(dicom_files)} DICOM files to process")
    
    # Process each file
    for i, dicom_file in enumerate(dicom_files):
        # Preserve relative directory structure
        rel_path = os.path.relpath(dicom_file, input_path)
        output_file = output_path / rel_path
        
        # Ensure output subdirectory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"\nProcessing {i+1}/{len(dicom_files)}: {rel_path}")
        anonymize_dicom(dicom_file, str(output_file), type_ones, type_ones_to_modify, type_twos, type_threes, custom_type_ones)
    
    print(f"\nAnonymization complete! Processed {len(dicom_files)} files")
    print(f"Anonymized files saved to: {output_folder}")

def get_tags_of_types(filepath_to_dicom_dict):
    # keep as-is
    type_ones = []
    # keep but modify as a dict: { tag : action }
    type_ones_to_modify = {}
    # empty
    type_twos = []
    # remove completely
    type_threes = []

    # load the dicom data dict csv
    dicom_data_dict = pd.read_csv(filepath_to_dicom_dict)
    # read from the "Action_to_Take" column
    for _, row in dicom_data_dict.iterrows():
        action = row["Action_to_Take"]
        if (action == "keep"):
            type_ones.append(row["Tag"])
        elif (action == "empty"):
            type_twos.append(row["Tag"])
        elif (action == "remove"):
            type_threes.append(row["Tag"])
        else:
            type_ones_to_modify[row["Tag"]] = action
    
    return type_ones, type_ones_to_modify, type_twos, type_threes

if __name__ == "__main__":
    # get info on what to do with each tag
    type_ones, type_ones_to_modify, type_twos, type_threes = get_tags_of_types("data_analysis/dataset_creation/anonymizer/dicom-data-dict.csv")
    
    custom_type_ones = {
        "ContentDate" : "random jitter",
        "PatientID" : "hash",
        "ContributingEquipmentSequence_Seq0_Manufacturer" : "hash",
        "StudyInstanceUID" : "hash",
        "SeriesInstanceUID" : "hash",
        "FilterMaterial" : "RHODIUM",
        "CollimatorLeftVerticalEdge" : "0",
        "CollimatorRightVerticalEdge" : "0",
        "CollimatorUpperHorizontalEdge" : "0",
        "CollimatorLowerHorizontalEdge" : "0",
        "ShutterShape" : "RECTANGULAR",
        "DistanceSourceToIsocenter" : "1",
        "Trim" : "1",
        "RadiationSetting" : "SC"
    }

    input_folder = "images/"
    output_folder = "pydicom-images-1/"
    
    print("Starting DICOM anonymization with CSV configuration...")
    print(f"Input folder: {input_folder}")
    print(f"Output folder: {output_folder}")
    print(f"Configuration: dicom-data-dict.csv")
    print(f"Custom overrides: {len(custom_type_ones)} tags")
    
    anonymize_folder(input_folder, output_folder, type_ones, type_ones_to_modify, type_twos, type_threes, custom_type_ones)