# Filename anonymization: the second half of the pipeline.
#
# Metadata anonymization (anonymize.py) cleans the tags inside each file, but the
# filenames themselves frequently carry PHI - names, MRNs, accession numbers. This
# copies an anonymized folder to a new folder, renaming every file to
# ANON-XXXXXXXX.dcm, and writes a CSV mapping the new names back to the old ones.
#
# The numbering is a sequential counter over the files sorted by relative path, so
# collisions are impossible by construction rather than merely unlikely, and the
# number is not derived from the PHI-bearing original name.
#
# Output is flattened into a single folder: directory names can carry PHI too, and
# unique names make it safe to drop the tree. Grouping is still recoverable from the
# mapping CSV and from StudyInstanceUID / SeriesInstanceUID inside the files.
#
# The mapping CSV is the re-identification key. By default it is written to the
# PARENT of the output folder, so it does not travel with the de-identified dataset.
#
# Usage:
#   python rename_official_files.py <input_folder> <output_folder> [--mappings PATH] [--force]

import argparse
import csv
import os
import shutil
import sys

MAPPINGS_FILENAME = "filename_mappings.csv"
ANON_PREFIX = "ANON-"
ANON_DIGITS = 8


def find_dicom_files(folder):
    """Return every .dcm file under folder, sorted by relative path.

    Sorting matters: the ANON numbers come from this order, so the mapping must not
    depend on whatever order the filesystem happens to hand back. The .dcm filter
    matches anonymize.py's anonymize_folder - if one is widened to accept
    extensionless DICOMs, both must be, or files would be anonymized and then
    skipped here.
    """
    found = []
    for root, _, files in os.walk(folder):
        for file in files:
            if file.endswith('.dcm'):
                full = os.path.join(root, file)
                found.append((os.path.relpath(full, folder), full))
    return sorted(found, key=lambda pair: pair[0])


def make_anon_name(index, digits=ANON_DIGITS):
    """ANON-00000001.dcm for index 1. Unique because index is a counter."""
    return f"{ANON_PREFIX}{index:0{digits}d}.dcm"


def default_mappings_path(output_folder):
    """The mapping CSV belongs beside the output folder, not inside it."""
    parent = os.path.dirname(os.path.abspath(output_folder))
    return os.path.join(parent, MAPPINGS_FILENAME)


def write_mappings_csv(rows, path):
    """Write the old -> new mapping. rows is a list of (old_filename, new_filename).

    Refuses to write an empty mapping: this file is the only way to get back from an
    ANON name to the original, so replacing a good one with a header-only file would
    lose the key for an entire dataset.
    """
    if not rows:
        print(f"\nNOT writing an empty mapping CSV to {path}")
        print("  No files were renamed, so there is nothing to map. Any existing")
        print("  mapping at that path has been left untouched.")
        return False
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['old_filename', 'new_filename'])
        writer.writerows(rows)
    return True


def rename_folder(input_folder, output_folder, mappings_path=None, force=False):
    """Copy input_folder to output_folder under anonymized filenames.

    Returns (mapping_rows, failures). mapping_rows is a list of
    (old_relative_path, new_filename); failures is a list of
    (old_relative_path, error_message).
    """
    if mappings_path is None:
        mappings_path = default_mappings_path(output_folder)

    # Refuse to mix two runs' files in one folder: the mapping would no longer
    # describe what is actually on disk. Never delete anything - say so and stop.
    if os.path.isdir(output_folder) and os.listdir(output_folder):
        if not force:
            print(f"ERROR: output folder is not empty: {output_folder}")
            print("       Remove it, pick another folder, or pass --force to add to it.")
            return None, None
        print(f"WARNING: adding to a non-empty output folder: {output_folder}")

    # Checked before any copying, so a refusal leaves the filesystem untouched. The
    # mapping is the only route from an ANON name back to the original, so it is not
    # something to overwrite by accident.
    if os.path.exists(mappings_path) and not force:
        print(f"ERROR: a mapping CSV already exists: {mappings_path}")
        print("       It is the only way to reverse an earlier run's renaming.")
        print("       Move or delete it, pass --mappings to write elsewhere,")
        print("       or pass --force to overwrite it.")
        return None, None

    # The mapping CSV re-identifies the dataset. Inside the output folder it would
    # ship with the de-identified data, which defeats the point.
    out_abs = os.path.abspath(output_folder)
    map_abs = os.path.abspath(mappings_path)
    if os.path.commonpath([out_abs, map_abs]) == out_abs:
        print("=" * 70)
        print("WARNING: the mapping CSV is being written INSIDE the output folder:")
        print(f"         {map_abs}")
        print("         This file re-identifies the dataset. Keep it separate from")
        print("         the anonymized data before sharing that data.")
        print("=" * 70)

    dicom_files = find_dicom_files(input_folder)
    print(f"Found {len(dicom_files)} DICOM files to rename")

    os.makedirs(output_folder, exist_ok=True)

    mapping_rows = []
    failures = []

    for index, (rel_path, source_path) in enumerate(dicom_files, start=1):
        new_name = make_anon_name(index)
        dest_path = os.path.join(output_folder, new_name)

        # Should be impossible with a counter, but a stale --force run could collide
        if os.path.exists(dest_path):
            failures.append((rel_path, f"destination already exists: {new_name}"))
            print(f"  SKIPPED {rel_path} -> {new_name} (destination exists)")
            continue

        try:
            shutil.copy2(source_path, dest_path)
            # Forward slashes so the CSV reads the same on any platform
            mapping_rows.append((rel_path.replace(os.sep, '/'), new_name))
            print(f"  {rel_path} -> {new_name}")
        except Exception as e:
            failures.append((rel_path, str(e)))
            print(f"  FAILED {rel_path}: {e}")

    wrote_mappings = write_mappings_csv(mapping_rows, mappings_path)

    print(f"\nRenaming complete! {len(mapping_rows)}/{len(dicom_files)} files renamed")
    print(f"Renamed files saved to: {output_folder}")
    if wrote_mappings:
        print(f"Filename mappings saved to: {mappings_path}")
    if failures:
        print(f"\nFAILED ({len(failures)}):")
        for rel_path, error in failures:
            print(f"  {rel_path}: {error}")

    return mapping_rows, failures


def main():
    parser = argparse.ArgumentParser(
        description="Copy a folder of DICOMs to anonymized filenames (ANON-XXXXXXXX.dcm) "
                    "and write a CSV mapping the new names to the old ones.")
    parser.add_argument("input_folder",
                        help="folder of (already metadata-anonymized) DICOM files")
    parser.add_argument("output_folder",
                        help="folder to write the renamed copies into, flattened")
    parser.add_argument("--mappings", default=None,
                        help=f"path for the mapping CSV "
                             f"(default: {MAPPINGS_FILENAME} beside the output folder)")
    parser.add_argument("--force", action="store_true",
                        help="allow writing into a non-empty output folder")
    args = parser.parse_args()

    if not os.path.isdir(args.input_folder):
        print(f"ERROR: input folder does not exist: {args.input_folder}")
        return 1

    print(f"Input folder: {args.input_folder}")
    print(f"Output folder: {args.output_folder}")

    mapping_rows, failures = rename_folder(
        args.input_folder, args.output_folder, args.mappings, args.force)

    if mapping_rows is None:
        return 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
