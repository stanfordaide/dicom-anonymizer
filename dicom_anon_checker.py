# Verify that anonymization actually did what dicom-data-dict.csv said to do.
#
# For every rule in the data dict, this looks at the original file and the anonymized
# file and checks the rule was honored:
#
#   keep    -> tag still present, value unchanged
#   empty   -> tag still present, value blank
#   remove  -> tag gone
#   custom  -> hashed / jittered / replaced with the expected literal
#
# It reports per-file and in aggregate, and exits non-zero if anything failed, so it
# can gate a pipeline. Rules are looked up with the same index-insensitive
# normalization anonymize.py uses, and the custom action definitions are imported from
# anonymize.py rather than copied, so the two cannot drift apart.
#
# Usage:
#   python dicom_anon_checker.py <original_folder> <anonymized_folder> \
#       [--mappings PATH] [--config CSV] [--verbose]
#
# Pass --mappings when the anonymized files have been renamed to ANON- names; the
# mapping CSV is what pairs them back to their originals.

import argparse
import csv
import hashlib
import os
import re
import sys
from datetime import datetime

import pandas as pd
import pydicom

from anonymize import (BINARY_VRS, CSV_CONFIG_PATH, CUSTOM_TYPE_ONES,
                       NEVER_REMOVE_UNLISTED, UID_PREFIX, normalize_tag_name,
                       remove_lpch)

# These tags get a freshly generated UID rather than a hash of the original, so their
# value cannot be predicted - only its shape can be checked
UID_HASH_TAGS = {"StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID"}

AS_VR_RE = re.compile(r'^\d{3}[YMWD]$')

PASS, FAIL, SKIP, WARN = "PASS", "FAIL", "SKIP", "WARN"


def load_rules(config_path):
    """Return {normalized tag name: action} from the data dict CSV."""
    dicom_data_dict = pd.read_csv(config_path)
    rules = {}
    for _, row in dicom_data_dict.iterrows():
        rules[normalize_tag_name(row["Tag"])] = row["Action_to_Take"]
    return rules


def flatten_dataset(ds, prefix=""):
    """Flatten a dataset to {ContributingEquipmentSequence_Seq0_InstitutionName: element}.

    Same naming scheme the CSV uses, so rules can be matched against nested tags.
    """
    flat = {}
    for element in ds:
        keyword = element.keyword or f"Tag_{element.tag}"
        full_name = f"{prefix}{keyword}"
        if element.VR == 'SQ':
            for i, item in enumerate(element.value):
                flat.update(flatten_dataset(item, f"{full_name}_Seq{i}_"))
        else:
            flat[full_name] = element
    return flat


def is_empty_value(value):
    """True for the various things pydicom hands back for an emptied element."""
    if value is None:
        return True
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return True
    return str(value).strip() == ""


def scrubbed(value):
    """The value as the LPCH pass would have left it.

    anonymize.py strips LPCH from every text value *before* applying any CSV action, so
    a hashed or kept value is derived from the scrubbed text, not the raw original.
    """
    return str(remove_lpch(str(value), verbose=False))


def expected_hash(original_value):
    """Reproduce anonymize.py's get_consistent_hash(), including the earlier LPCH pass."""
    return hashlib.sha256(scrubbed(original_value).encode()).hexdigest()[:16]



CUSTOM_BY_KEY = {normalize_tag_name(k): v for k, v in CUSTOM_TYPE_ONES.items()}


def resolve_action(tag_name, csv_action):
    """Work out what anonymize.py would actually have done to this tag.

    The CSV records intent in prose ("keep but hash"), and anonymize.py resolves the 14
    such rows through CUSTOM_TYPE_ONES, which is checked first. Mirroring that
    precedence here is what keeps the checker honest: it verifies what the code does,
    not what the CSV's wording suggests.

    Returns (effective_action, is_unbacked_prose). The flag is True when a CSV row asks
    for something custom but has no CUSTOM_TYPE_ONES entry, in which case anonymize.py
    writes the prose string itself into the tag.
    """
    key = normalize_tag_name(tag_name)
    if key in CUSTOM_BY_KEY:
        return CUSTOM_BY_KEY[key], False
    if csv_action in ("keep", "empty", "remove"):
        return csv_action, False
    return csv_action, True


def check_rule(tag_name, action, original_element, anon_element, unbacked=False):
    """Check one resolved action against one tag. Returns (status, detail)."""
    present = anon_element is not None
    original_value = original_element.value
    anon_value = anon_element.value if present else None
    leaf = tag_name.split('_')[-1]

    if unbacked:
        return WARN, (f"action {action!r} has no CUSTOM_TYPE_ONES entry, so the prose "
                      f"string itself was written into the tag (value is now "
                      f"{str(anon_value)[:40]!r})")

    # Custom actions are checked first, matching anonymize.py's precedence
    if action == "hash":
        if not present:
            return FAIL, "expected a hashed value, but the tag was removed"
        if leaf in UID_HASH_TAGS:
            if str(anon_value) == str(original_value):
                return FAIL, "UID unchanged"
            if not str(anon_value).startswith(UID_PREFIX):
                return FAIL, f"replacement UID lacks the {UID_PREFIX} prefix: {anon_value!r}"
            return PASS, "replaced with a new UID"
        want = expected_hash(original_value)
        if str(anon_value) != want:
            return FAIL, f"expected sha256[:16] {want!r}, got {str(anon_value)!r}"
        return PASS, "hashed"

    if action == "compute age":
        # Tag may be absent if birth date or exam date was unavailable — that is
        # intentional, so absence is not a failure.
        if not present:
            return PASS, "removed (age could not be computed)"
        val_str = str(anon_value).strip()
        if not AS_VR_RE.match(val_str):
            return FAIL, f"expected AS-VR format (e.g. 025Y), got {val_str!r}"
        return PASS, f"computed age: {val_str}"

    if action == "keep":
        if not present:
            return FAIL, "should have been kept, but the tag is gone"
        if str(anon_value) == str(original_value):
            return PASS, "kept"
        # The LPCH scrub runs over every text value regardless of what the CSV says, so
        # it legitimately overrides "keep". Accept a difference that is exactly the LPCH
        # removal, and only then.
        if str(anon_value) == scrubbed(original_value):
            return PASS, "kept, with LPCH stripped by the institution scrub"
        return FAIL, f"should be unchanged, but {str(original_value)[:40]!r} -> {str(anon_value)[:40]!r}"

    if action == "empty":
        if not present:
            return FAIL, "should have been emptied, but the tag is gone"
        if not is_empty_value(anon_value):
            return FAIL, f"should be empty, but holds {str(anon_value)[:40]!r}"
        return PASS, "emptied"

    if action == "remove":
        if present:
            return FAIL, f"should have been removed, but still holds {str(anon_value)[:40]!r}"
        return PASS, "removed"

    # Anything else is a literal replacement value from CUSTOM_TYPE_ONES.
    if not present:
        return FAIL, f"expected the literal {action!r}, but the tag was removed"
    if str(anon_value) != str(action):
        return FAIL, f"expected {action!r}, got {str(anon_value)!r}"
    return PASS, f"replaced with {action!r}"


def check_file(original_path, anon_path, rules):
    """Check one pair of files. Returns (results, lpch_hits, unlisted).

    results is a list of (tag_name, action, status, detail).
    """
    original_ds = pydicom.dcmread(original_path)
    anon_ds = pydicom.dcmread(anon_path)

    original_flat = flatten_dataset(original_ds)
    anon_flat = flatten_dataset(anon_ds)

    results = []
    for tag_name, original_element in original_flat.items():
        csv_action = rules.get(normalize_tag_name(tag_name))
        if csv_action is None:
            # No rule for this tag. anonymize.py leaves those alone by design; the
            # unlisted report below covers whether that is safe.
            continue
        action, unbacked = resolve_action(tag_name, csv_action)
        status, detail = check_rule(tag_name, action, original_element,
                                    anon_flat.get(tag_name), unbacked)
        # Report against the CSV's own wording, which is what a reader will look up
        results.append((tag_name, csv_action, status, detail))

    # The LPCH scrub runs outside the CSV, so verify it separately. str() is used
    # deliberately: PersonName and MultiValue are not str, and checking isinstance
    # here would reproduce the exact bug this is meant to catch.
    lpch_hits = []
    for element in anon_ds.iterall():
        if element.VR in BINARY_VRS or element.value is None:
            continue
        if isinstance(element.value, (bytes, bytearray)):
            continue
        if "LPCH" in str(element.value):
            lpch_hits.append((element.keyword or str(element.tag), str(element.value)))

    # Tags surviving into the output with no rule covering them. anonymize.py's strict
    # mode removes these, so anything left here is either a leak or was deliberately
    # protected as bulk data. Sequence containers are excluded: no container appears in
    # the CSV, only their children do, so they are legitimately unlisted.
    unlisted = sorted(
        name for name in anon_flat
        if rules.get(normalize_tag_name(name)) is None
        and name.split('_')[-1] not in NEVER_REMOVE_UNLISTED)

    return results, lpch_hits, unlisted


def pair_files(original_folder, anon_folder, mappings_path=None):
    """Return [(label, original_path, anon_path)] for each file to check."""
    pairs = []
    if mappings_path:
        with open(mappings_path, newline='') as f:
            for row in csv.DictReader(f):
                old, new = row['old_filename'], row['new_filename']
                pairs.append((f"{old} -> {new}",
                              os.path.join(original_folder, old),
                              os.path.join(anon_folder, new)))
        return pairs

    for root, _, files in os.walk(original_folder):
        for file in sorted(files):
            if not file.endswith('.dcm'):
                continue
            full = os.path.join(root, file)
            rel = os.path.relpath(full, original_folder)
            pairs.append((rel, full, os.path.join(anon_folder, rel)))
    return sorted(pairs, key=lambda p: p[0])


def check_folder(original_folder, anon_folder, mappings_path=None,
                 config_path=CSV_CONFIG_PATH, verbose=False):
    """Check every paired file and print a report. Returns the number of failures."""
    rules = load_rules(config_path)
    pairs = pair_files(original_folder, anon_folder, mappings_path)

    print("=" * 74)
    print("DICOM ANONYMIZATION CHECK")
    print("=" * 74)
    print(f"Original folder:   {original_folder}")
    print(f"Anonymized folder: {anon_folder}")
    print(f"Config:            {config_path} ({len(rules)} rules)")
    if mappings_path:
        print(f"Mappings:          {mappings_path}")
    print(f"Files to check:    {len(pairs)}")

    total_pass = total_fail = total_warn = 0
    missing_files = []
    all_unlisted = {}

    for label, original_path, anon_path in pairs:
        print(f"\n{label}")

        if not os.path.exists(original_path):
            print(f"  ERROR: original not found: {original_path}")
            missing_files.append(original_path)
            continue
        if not os.path.exists(anon_path):
            print(f"  ERROR: anonymized file not found: {anon_path}")
            missing_files.append(anon_path)
            continue

        try:
            results, lpch_hits, unlisted = check_file(original_path, anon_path, rules)
        except Exception as e:
            print(f"  ERROR reading files: {e}")
            missing_files.append(anon_path)
            continue

        passes = [r for r in results if r[2] == PASS]
        failures = [r for r in results if r[2] == FAIL]
        warnings = [r for r in results if r[2] == WARN]
        total_pass += len(passes)
        total_fail += len(failures)
        total_warn += len(warnings)

        by_action = {}
        for _, action, status, _ in results:
            key = action if action in ("keep", "empty", "remove") else "custom"
            entry = by_action.setdefault(key, [0, 0])
            entry[0 if status == PASS else 1] += 1
        breakdown = ", ".join(f"{k} {v[0]}/{v[0] + v[1]}"
                             for k, v in sorted(by_action.items()))
        print(f"  {len(passes)}/{len(results)} rules honored   ({breakdown})")

        for tag_name, action, _, detail in failures:
            print(f"  FAIL  [{action}] {tag_name}: {detail}")
        for tag_name, action, _, detail in warnings:
            print(f"  WARN  {tag_name}: {detail}")
        if lpch_hits:
            total_fail += len(lpch_hits)
            for keyword, value in lpch_hits:
                print(f"  FAIL  [LPCH] {keyword} still contains LPCH: {value[:50]!r}")
        if verbose:
            for tag_name, action, _, detail in passes:
                print(f"  pass  [{action}] {tag_name}: {detail}")

        # A surviving unlisted tag is a failure, not a note: anonymize.py removes every
        # tag the data dict has no rule for, so one being here means it leaked.
        total_fail += len(unlisted)
        for name in unlisted:
            print(f"  FAIL  [unlisted] {name} has no rule in the data dict and "
                  f"should have been removed")
        for name in unlisted:
            all_unlisted[name] = all_unlisted.get(name, 0) + 1

    print("\n" + "=" * 74)
    print("SUMMARY")
    print("=" * 74)
    print(f"Files checked:  {len(pairs) - len(missing_files)}/{len(pairs)}")
    print(f"Rules honored:  {total_pass}")
    print(f"Rules violated: {total_fail}")
    if total_warn:
        print(f"Warnings:       {total_warn}")
    if missing_files:
        print(f"Files missing:  {len(missing_files)}")

    if all_unlisted:
        print(f"\nTags that should have been removed but survived "
              f"({len(all_unlisted)}):")
        print("  Every one of these is a potential PHI leak. This check is how the")
        print("  missing InstitutionName rows and the private-tag leak were both found.")
        for name in sorted(all_unlisted):
            print(f"    {name}")

    if total_fail:
        print(f"\nRESULT: FAILED - {total_fail} rule(s) not honored")
    elif missing_files:
        print("\nRESULT: INCOMPLETE - some files could not be checked")
    else:
        print("\nRESULT: PASSED - every rule in the data dict was honored")

    return total_fail + len(missing_files)


def main():
    parser = argparse.ArgumentParser(
        description="Check that anonymized DICOMs honor every rule in the data dict.")
    parser.add_argument("original_folder", help="folder of original, non-anonymized files")
    parser.add_argument("anonymized_folder", help="folder of anonymized files")
    parser.add_argument("--mappings", default=None,
                        help="filename_mappings.csv, required if the anonymized files "
                             "have been renamed to ANON- names")
    parser.add_argument("--config", default=CSV_CONFIG_PATH,
                        help="data dict CSV (default: dicom-data-dict.csv beside anonymize.py)")
    parser.add_argument("--verbose", action="store_true",
                        help="also print every rule that passed")
    args = parser.parse_args()

    for folder in (args.original_folder, args.anonymized_folder):
        if not os.path.isdir(folder):
            print(f"ERROR: folder does not exist: {folder}")
            return 1
    if args.mappings and not os.path.isfile(args.mappings):
        print(f"ERROR: mappings CSV does not exist: {args.mappings}")
        return 1

    problems = check_folder(args.original_folder, args.anonymized_folder,
                            args.mappings, args.config, args.verbose)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
