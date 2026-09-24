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

# VRs whose values are raw binary - never scan or rewrite these as text
BINARY_VRS = {'OB', 'OW', 'OF', 'OD', 'OL', 'OV', 'UN', 'SQ'}


def clean_lpch_value(value):
    """Strip LPCH from any string-ish DICOM value.

    pydicom does not hand back a plain str for every text VR: PN comes back as
    PersonName and multi-valued elements as MultiValue, neither of which is a str.
    Testing isinstance(value, str) alone therefore silently skips every person-name
    field, which is exactly where names tend to live.
    """
    if isinstance(value, pydicom.valuerep.PersonName):
        return remove_lpch(str(value))
    if isinstance(value, pydicom.multival.MultiValue):
        return [clean_lpch_value(v) for v in value]
    if isinstance(value, str):
        return remove_lpch(value)
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

SEQ_INDEX_RE = re.compile(r"_Seq\d+_")


def normalize_tag_name(name):
    """Make a tag name index-insensitive so one CSV row covers every item of a sequence.

    The CSV's flattened names (e.g. PerformedProtocolCodeSequence_Seq0_CodeValue) come
    from get_metadata.py, and the indices in them are just whatever the source dataset
    happened to contain - they are not a per-item instruction. Collapsing the index means
    a rule written for _Seq0_ also applies to item 7 of a file we have never seen.
    The CSV itself is never modified; this only affects lookup keys.
    """
    return SEQ_INDEX_RE.sub("_Seq_", name)


def normalize_keys(rules):
    """Index-normalize a list of tag names or a {tag name: action} dict."""
    if isinstance(rules, dict):
        return {normalize_tag_name(k): v for k, v in rules.items()}
    return {normalize_tag_name(k) for k in rules}


def process_dataset(ds, prefix, type_ones, type_ones_to_modify, type_twos, type_threes,
                    custom_type_ones, patient_id):
    """Apply the CSV rules to one dataset level, recursing into sequences.

    prefix builds up the same flattened name the CSV uses, so nested tags such as
    ContributingEquipmentSequence_Seq0_InstitutionName can actually be matched.
    Removals are collected per level and deleted from the dataset that owns the
    element - deleting a nested element's tag from the top-level dataset would either
    do nothing or delete an unrelated element that shares the tag number.
    """
    elements_to_remove = []

    for element in ds:
        keyword = element.keyword or f"Tag_{element.tag}"
        full_name = f"{prefix}{keyword}"
        key = normalize_tag_name(full_name)

        # A sequence itself may be marked for removal; otherwise descend into its items.
        if element.VR == 'SQ':
            if key in type_threes:
                elements_to_remove.append(element.tag)
                print(f"Marked sequence for removal: {full_name} ({element.tag})")
            else:
                for i, item in enumerate(element.value):
                    process_dataset(item, f"{full_name}_Seq{i}_", type_ones,
                                    type_ones_to_modify, type_twos, type_threes,
                                    custom_type_ones, patient_id)
            continue

        if hasattr(element, 'value') and element.value is not None:

            # Handle custom actions first (highest priority)
            if key in custom_type_ones:
                apply_custom_action(element, full_name, custom_type_ones[key], patient_id)

            # Handle Type 1 tags that need modification
            elif key in type_ones_to_modify:
                apply_custom_action(element, full_name, type_ones_to_modify[key], patient_id)

            # Handle Type 1 tags (keep as-is)
            elif key in type_ones:
                print(f"Kept {full_name}: '{element.value}'")

            # Handle Type 2 tags (empty them)
            elif key in type_twos:
                try:
                    if element.VR in ['FL', 'FD', 'SL', 'SS', 'UL', 'US']:
                        element.value = None
                    else:
                        element.value = ""
                    print(f"Emptied {full_name} (VR: {element.VR})")
                except Exception as e:
                    print(f"Error emptying {full_name}: {e}")

            # Handle Type 3 tags (remove them) - ONLY if explicitly in type_threes list
            elif key in type_threes:
                elements_to_remove.append(element.tag)
                print(f"Marked for removal: {full_name} ({element.tag})")

            # For all other tags (not in CSV), do nothing - leave as-is.
            # This includes PixelData and any other tag the CSV does not mention.
            else:
                pass

        else:
            # Empty elements - only remove if explicitly in type_threes list
            if key in type_threes:
                elements_to_remove.append(element.tag)

    # Remove only the explicitly marked elements, from this dataset level
    for tag in elements_to_remove:
        if tag in ds:
            try:
                del ds[tag]
                print(f"Removed tag: {tag}")
            except Exception as e:
                print(f"Error removing tag {tag}: {e}")


def anonymize_dicom(input_path, output_path, type_ones, type_ones_to_modify, type_twos, type_threes, custom_type_ones):
    """Anonymize a single DICOM file based on configuration.

    Returns True on success, False if the file could not be anonymized or written.
    """
    tmp_path = output_path + ".partial"
    try:
        ds = pydicom.dcmread(input_path)

        # Index-normalize every rule set so nested CSV names can match (see item 2)
        type_ones = normalize_keys(type_ones)
        type_ones_to_modify = normalize_keys(type_ones_to_modify)
        type_twos = normalize_keys(type_twos)
        type_threes = normalize_keys(type_threes)
        custom_type_ones = normalize_keys(custom_type_ones)

        # Get PatientID for consistent jittering
        patient_id = None
        if hasattr(ds, 'PatientID') and ds.PatientID:
            patient_id = ds.PatientID

        # FIRST PASS: Remove LPCH from ALL elements, at every nesting level and in
        # every string-ish VR (str, PersonName, MultiValue)
        for element in ds.iterall():
            if not hasattr(element, 'value') or element.value is None:
                continue
            if element.VR in BINARY_VRS or isinstance(element.value, (bytes, bytearray)):
                continue
            original_value = str(element.value)
            if "LPCH" not in original_value:
                continue
            element.value = clean_lpch_value(element.value)
            print(f"LPCH cleaned from {element.keyword or element.tag}: '{original_value}' -> '{element.value}'")

        # SECOND PASS: Handle anonymization by type - ONLY for tags explicitly listed in CSV
        process_dataset(ds, "", type_ones, type_ones_to_modify, type_twos, type_threes,
                        custom_type_ones, patient_id)

        # Save anonymized DICOM. Written to a temp path first and moved into place only
        # on success: pydicom validates values during write, so a bad value would
        # otherwise leave a truncated file behind that looks like valid output.
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        ds.save_as(tmp_path, enforce_file_format=True)
        os.replace(tmp_path, output_path)
        print(f"Successfully anonymized: {os.path.basename(input_path)}")
        return True

    except Exception as e:
        print(f"Error processing {input_path}: {e}")
        # Never leave a partial file that could be mistaken for anonymized output
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False


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
    
    succeeded = 0
    failed = []
    
    # Process each file
    for i, dicom_file in enumerate(dicom_files):
        # Preserve relative directory structure
        rel_path = os.path.relpath(dicom_file, input_path)
        output_file = output_path / rel_path
        
        # Ensure output subdirectory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"\nProcessing {i+1}/{len(dicom_files)}: {rel_path}")
        if anonymize_dicom(dicom_file, str(output_file), type_ones, type_ones_to_modify, type_twos, type_threes, custom_type_ones):
            succeeded += 1
        else:
            failed.append(rel_path)
    
    print(f"\nAnonymization complete! {succeeded}/{len(dicom_files)} files anonymized")
    print(f"Anonymized files saved to: {output_folder}")
    if failed:
        print(f"\nFAILED ({len(failed)}) - no output written for these files:")
        for rel_path in failed:
            print(f"  {rel_path}")
    return succeeded, failed

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

# Config CSV lives next to this script, so it resolves no matter where you run from
CSV_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dicom-data-dict.csv")

if __name__ == "__main__":
    # get info on what to do with each tag
    type_ones, type_ones_to_modify, type_twos, type_threes = get_tags_of_types(CSV_CONFIG_PATH)
    
    custom_type_ones = {
        "ContentDate" : "random jitter",
        "PatientID" : "hash",
        "ContributingEquipmentSequence_Seq0_Manufacturer" : "hash",
        "StudyInstanceUID" : "hash",
        "SeriesInstanceUID" : "hash",
        "FilterMaterial" : "RHODIUM",
        # These four are VR IS (integer string) - use ints, not strings
        "CollimatorLeftVerticalEdge" : 0,
        "CollimatorRightVerticalEdge" : 0,
        "CollimatorUpperHorizontalEdge" : 0,
        "CollimatorLowerHorizontalEdge" : 0,
        "ShutterShape" : "RECTANGULAR",
        # VR FL (float) - a string here fails inside save_as(), mid-write
        "DistanceSourceToIsocenter" : 1.0,
        "Trim" : "1",
        "RadiationSetting" : "SC"
    }

    input_folder = "sample/sample_dicoms/"
    output_folder = "sample/anonymized_output/"
    
    print("Starting DICOM anonymization with CSV configuration...")
    print(f"Input folder: {input_folder}")
    print(f"Output folder: {output_folder}")
    print(f"Configuration: {CSV_CONFIG_PATH}")
    print(f"Custom overrides: {len(custom_type_ones)} tags")
    
    anonymize_folder(input_folder, output_folder, type_ones, type_ones_to_modify, type_twos, type_threes, custom_type_ones)
