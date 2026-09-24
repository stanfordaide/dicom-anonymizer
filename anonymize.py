import argparse
import sys

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

def remove_lpch(value, verbose=True):
    """Remove LPCH and LPCH - substrings from value.

    verbose=False silences the log line, so callers that only want to know what the
    cleaned value would be (dicom_anon_checker.py) do not pollute their own output.
    """
    if isinstance(value, str):
        original_value = value
        # Remove LPCH with various spacing patterns
        cleaned = value.replace("LPCH -", "").replace("LPCH", "").replace("- LPCH", "")
        # Clean up extra spaces and dashes
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = re.sub(r'^[\s\-]+|[\s\-]+$', '', cleaned)
        
        if original_value != cleaned and verbose:
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


# Tags never deleted for want of a CSV row. These are bulk data,
# not identifiers: deleting PixelData would throw away the image itself, and the CSV has
# no row for it. This only guards the "not in the CSV" path - an explicit `remove` in the
# CSV is still obeyed.
NEVER_REMOVE_UNLISTED = {
    "PixelData", "FloatPixelData", "DoubleFloatPixelData", "PixelDataProviderURL",
    "OverlayData", "WaveformData", "EncapsulatedDocument", "CurveData",
    "SpectroscopyData",
}


def process_dataset(ds, prefix, type_ones, type_ones_to_modify, type_twos, type_threes,
                    custom_type_ones, patient_id, known_keys, removed_unlisted=None):
    """Apply the CSV rules to one dataset level, recursing into sequences.

    prefix builds up the same flattened name the CSV uses, so nested tags such as
    ContributingEquipmentSequence_Seq0_InstitutionName can actually be matched.
    Removals are collected per level and deleted from the dataset that owns the
    element - deleting a nested element's tag from the top-level dataset would either
    do nothing or delete an unrelated element that shares the tag number.

    known_keys is the set of every tag the CSV has a rule for. Any tag outside it is
    removed: the CSV was built from the official tag list, so anything absent from it is
    either a private vendor tag or something no valid file needs. Names of removed
    unlisted tags are appended to removed_unlisted for reporting.
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
                # Always descend rather than deleting the container. No sequence
                # container appears in the CSV, only their children do, so deleting
                # unlisted containers outright would destroy tags marked `keep`.
                for i, item in enumerate(element.value):
                    process_dataset(item, f"{full_name}_Seq{i}_", type_ones,
                                    type_ones_to_modify, type_twos, type_threes,
                                    custom_type_ones, patient_id, known_keys,
                                    removed_unlisted)
                # A container that is unlisted and now completely empty held nothing
                # the CSV sanctioned - this is what clears private vendor sequences.
                if (key not in known_keys
                        and all(len(item) == 0 for item in element.value)):
                    elements_to_remove.append(element.tag)
                    print(f"Marked empty unlisted sequence for removal: {full_name}")
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

            # No rule in the CSV, so remove it - see known_keys in the docstring.
            else:
                if keyword not in NEVER_REMOVE_UNLISTED:
                    elements_to_remove.append(element.tag)
                    if removed_unlisted is not None:
                        removed_unlisted.append(full_name)
                    private = " (private)" if element.tag.group % 2 == 1 else ""
                    print(f"Removed unlisted tag{private}: {full_name} ({element.tag})")

        else:
            # Empty elements: removed if the CSV says so, or if there is no rule at all
            if key in type_threes:
                elements_to_remove.append(element.tag)
            elif keyword not in NEVER_REMOVE_UNLISTED and key not in known_keys:
                elements_to_remove.append(element.tag)
                if removed_unlisted is not None:
                    removed_unlisted.append(full_name)

    # Remove only the explicitly marked elements, from this dataset level
    for tag in elements_to_remove:
        if tag in ds:
            try:
                del ds[tag]
                print(f"Removed tag: {tag}")
            except Exception as e:
                print(f"Error removing tag {tag}: {e}")


def anonymize_dicom(input_path, output_path, type_ones, type_ones_to_modify, type_twos,
                    type_threes, custom_type_ones):
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

        # SECOND PASS: apply the CSV rules. known_keys is every tag the CSV covers, so
        # that anything outside it can be removed.
        removed_unlisted = []
        known_keys = (set(type_ones) | set(type_twos) | set(type_threes)
                      | set(type_ones_to_modify) | set(custom_type_ones))
        process_dataset(ds, "", type_ones, type_ones_to_modify, type_twos, type_threes,
                        custom_type_ones, patient_id, known_keys, removed_unlisted)
        if removed_unlisted:
            print(f"Removed {len(removed_unlisted)} tag(s) with no rule in the data dict")

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


def anonymize_folder(input_folder, output_folder, type_ones, type_ones_to_modify,
                     type_twos, type_threes, custom_type_ones):
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
        if anonymize_dicom(dicom_file, str(output_file), type_ones, type_ones_to_modify,
                           type_twos, type_threes, custom_type_ones):
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

# The CSV records intent in prose ("keep but populate with 0"); this dict is the
# machine-readable implementation of those 14 rows. It lives at module level so that
# dicom_anon_checker.py can import it and verify against the same definitions rather
# than keeping its own copy, which would silently drift.
CUSTOM_TYPE_ONES = {
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

# The prefix get_consistent_uid() generates replacement UIDs under
UID_PREFIX = "1.2.840.113619."

def folders_overlap(input_folder, output_folder):
    """True if one folder contains the other, or they are the same folder.

    Writing output inside the input folder is a quiet trap: the first run looks fine,
    but a second run walks its own output and re-anonymizes already-anonymized files -
    hashing hashes, jittering jittered dates - and the file count grows every time.
    Every entry point refuses this rather than letting it happen.
    """
    a = os.path.abspath(input_folder)
    b = os.path.abspath(output_folder)
    return a == b or os.path.commonpath([a, b]) in (a, b)


def anonymize(input_folder, output_folder, config_path=CSV_CONFIG_PATH):
    """Anonymize every DICOM in input_folder into output_folder.

    Returns (succeeded, failed) from anonymize_folder, so callers such as the pipeline
    orchestrator can report honestly and stop on failure.
    """
    type_ones, type_ones_to_modify, type_twos, type_threes = get_tags_of_types(config_path)

    print("Starting DICOM anonymization with CSV configuration...")
    print(f"Input folder: {input_folder}")
    print(f"Output folder: {output_folder}")
    print(f"Configuration: {config_path}")
    print(f"Custom overrides: {len(CUSTOM_TYPE_ONES)} tags")
    print("Tags with no data dict rule: removed")

    return anonymize_folder(input_folder, output_folder, type_ones, type_ones_to_modify,
                            type_twos, type_threes, CUSTOM_TYPE_ONES)


def main():
    parser = argparse.ArgumentParser(
        description="Anonymize DICOM metadata according to dicom-data-dict.csv. "
                    "Filenames are preserved; use rename_official_files.py to anonymize those.")
    parser.add_argument("input_folder", help="folder of DICOM files to anonymize")
    parser.add_argument("output_folder",
                        help="folder to write anonymized files into, preserving structure")
    parser.add_argument("--config", default=CSV_CONFIG_PATH,
                        help="data dict CSV (default: dicom-data-dict.csv beside this script)")
    args = parser.parse_args()

    if not os.path.isdir(args.input_folder):
        print(f"ERROR: input folder does not exist: {args.input_folder}")
        return 1
    if not os.path.isfile(args.config):
        print(f"ERROR: config CSV does not exist: {args.config}")
        return 1
    if folders_overlap(args.input_folder, args.output_folder):
        print(f"ERROR: the output folder is inside the input folder (or vice versa):")
        print(f"       input:  {args.input_folder}")
        print(f"       output: {args.output_folder}")
        print("       Re-running would re-anonymize the output. Use a separate folder.")
        return 1

    _, failed = anonymize(args.input_folder, args.output_folder, args.config)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
