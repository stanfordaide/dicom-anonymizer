# One command for the whole anonymization pipeline.
#
#   1. anonymize metadata   (anonymize.py)
#   2. anonymize filenames  (rename_official_files.py)
#   3. verify the result    (dicom_anon_checker.py)
#   4. compile a metadata CSV of the output for auditing (compile_metadata.py)
#
# Usage:
#   python pipeline.py <input_folder> <output_folder> [options]
#
# Given an input folder of DICOMs, produces:
#
#   <output_folder>/anonymized/           metadata anonymized, original filenames
#   <output_folder>/anonymized_renamed/   final deliverable: HIPSTER- names, flattened
#   <output_folder>/filename_mappings.csv the re-identification key
#   <output_folder>/anonymized_metadata.csv every tag of the output, for auditing
#
# Only anonymized_renamed/ is the shareable artifact. The mapping CSV sits beside it
# rather than inside it precisely so it does not get shared along with the data.
#
# Each stage stops the pipeline if it fails, and the exit code is non-zero if anything
# went wrong, so this can gate a larger process.

import argparse
import contextlib
import io
import os
import sys

from anonymize import CSV_CONFIG_PATH, anonymize, folders_overlap
from compile_metadata import extract_all_dicom_metadata
from dicom_anon_checker import check_folder
from rename_official_files import MAPPINGS_FILENAME, rename_folder

ANON_SUBDIR = "anonymized"
RENAMED_SUBDIR = "anonymized_renamed"
METADATA_FILENAME = "anonymized_metadata.csv"


def banner(step, total, title):
    print()
    print("=" * 74)
    print(f"STEP {step}/{total}: {title}")
    print("=" * 74)


@contextlib.contextmanager
def maybe_quiet(quiet):
    """Swallow a stage's per-tag chatter unless --verbose was passed.

    anonymize.py logs every single tag decision, which is useful when debugging one
    file and unreadable across thousands. The summary lines are printed by this module
    either way, so nothing needed is lost.
    """
    if not quiet:
        yield
        return
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        yield


def run_pipeline(input_folder, output_folder, config_path=CSV_CONFIG_PATH,
                 mappings_path=None, verbose=False):
    """Run all three stages. Returns an exit code: 0 on success, 1 on any failure."""
    anon_dir = os.path.join(output_folder, ANON_SUBDIR)
    renamed_dir = os.path.join(output_folder, RENAMED_SUBDIR)
    if mappings_path is None:
        mappings_path = os.path.join(output_folder, MAPPINGS_FILENAME)
    metadata_path = os.path.join(output_folder, METADATA_FILENAME)

    TOTAL_STEPS = 4

    print("=" * 74)
    print("DICOM ANONYMIZATION PIPELINE")
    print("=" * 74)
    print(f"Input:            {input_folder}")
    print(f"Output:           {output_folder}")
    print(f"  metadata only:  {anon_dir}")
    print(f"  final output:   {renamed_dir}")
    print(f"  mapping key:    {mappings_path}")
    print(f"  metadata audit: {metadata_path}")
    print(f"Config:           {config_path}")

    # Output inside the input folder is the trap folders_overlap() describes: the first
    # run looks clean, and the second walks its own output. Refuse before doing any work.
    if folders_overlap(input_folder, output_folder):
        print("\nERROR: the output folder is inside the input folder (or vice versa):")
        print(f"       input:  {input_folder}")
        print(f"       output: {output_folder}")
        print("       A later run would re-anonymize this run's output, hashing hashes")
        print("       and jittering already-jittered dates. Use a separate folder.")
        return 1

    # Checked up front so the run does not die halfway through. rename_folder does its
    # own checks too, but failing before stage 1 saves doing all that work for nothing.
    for path, label in ((anon_dir, "intermediate folder"),
                        (renamed_dir, "output folder")):
        if os.path.isdir(path) and os.listdir(path):
            print(f"\nERROR: {label} is not empty: {path}")
            print("       Remove it or pick another output folder.")
            return 1
    if os.path.exists(mappings_path):
        print(f"\nERROR: a mapping CSV already exists: {mappings_path}")
        print("       It is the only way to reverse an earlier run's renaming.")
        print("       Move it, or pass --mappings to write elsewhere.")
        return 1

    # --- Stage 1: metadata ---------------------------------------------------
    banner(1, TOTAL_STEPS, "Anonymizing metadata")
    with maybe_quiet(not verbose):
        succeeded, failed = anonymize(input_folder, anon_dir, config_path)
    print(f"{succeeded} file(s) anonymized"
          + (f", {len(failed)} failed" if failed else ""))
    if failed:
        print("\nFailed files (no output written for these):")
        for rel_path in failed:
            print(f"  {rel_path}")
        print("\nPipeline stopped: fix the metadata stage before renaming.")
        return 1
    if succeeded == 0:
        print(f"\nNothing to do: no .dcm files found under {input_folder}")
        return 1

    # --- Stage 2: filenames --------------------------------------------------
    banner(2, TOTAL_STEPS, "Anonymizing filenames")
    with maybe_quiet(not verbose):
        mapping_rows, rename_failures = rename_folder(anon_dir, renamed_dir,
                                                      mappings_path)
    if mapping_rows is None:
        print("Pipeline stopped: the rename stage refused to run.")
        return 1
    print(f"{len(mapping_rows)} file(s) renamed")
    print(f"Mapping written to: {mappings_path}")
    if rename_failures:
        print(f"\n{len(rename_failures)} file(s) failed to rename:")
        for rel_path, error in rename_failures:
            print(f"  {rel_path}: {error}")
        print("\nPipeline stopped: the output folder is incomplete.")
        return 1

    # --- Stage 3: verification -----------------------------------------------
    # Always runs. There is no way to produce output from this tool without verifying it.
    banner(3, TOTAL_STEPS, "Verifying anonymization")
    # Compares the ORIGINAL input against the final renamed output, so the check
    # covers both stages at once rather than trusting the intermediate.
    problems = check_folder(input_folder, renamed_dir, mappings_path,
                            config_path, verbose)

    # --- Stage 4: metadata audit ---------------------------------------------
    # Compiled from the FINAL output, never the input: the same CSV built from
    # non-anonymized files would be a spreadsheet full of PHI.
    banner(4, TOTAL_STEPS, "Compiling a metadata audit CSV")
    with maybe_quiet(not verbose):
        metadata_df = extract_all_dicom_metadata(renamed_dir, metadata_path)
    print(f"{metadata_df.shape[0]} file(s), {metadata_df.shape[1] - 1} tag(s) "
          f"-> {metadata_path}")

    print()
    print("=" * 74)
    print("PIPELINE SUMMARY")
    print("=" * 74)
    print(f"Files processed:  {succeeded}")
    print(f"Final output:     {renamed_dir}")
    print(f"Mapping key:      {mappings_path}")
    print(f"Metadata audit:   {metadata_path}")
    print(f"Intermediate:     {anon_dir}")
    if problems:
        print(f"Verification:     FAILED ({problems} problem(s))")
    else:
        print("Verification:     PASSED")

    if problems:
        print("\nRESULT: FAILED - do not share this output until the failures above "
              "are resolved.")
        return 1

    print(f"\nRESULT: SUCCESS")
    print(f"  Share only {renamed_dir}")
    print(f"  Keep {mappings_path} private - it re-identifies the dataset.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Run the full DICOM anonymization pipeline: metadata, then "
                    "filenames, then verification.")
    parser.add_argument("input_folder", help="folder of DICOM files to anonymize")
    parser.add_argument("output_folder",
                        help="folder to write all pipeline output into")
    parser.add_argument("--config", default=CSV_CONFIG_PATH,
                        help="data dict CSV (default: dicom-data-dict.csv beside anonymize.py)")
    parser.add_argument("--mappings", default=None,
                        help=f"path for the mapping CSV "
                             f"(default: {MAPPINGS_FILENAME} in the output folder)")
    parser.add_argument("--verbose", action="store_true",
                        help="show every per-tag decision instead of just the summary")
    args = parser.parse_args()

    if not os.path.isdir(args.input_folder):
        print(f"ERROR: input folder does not exist: {args.input_folder}")
        return 1
    if not os.path.isfile(args.config):
        print(f"ERROR: config CSV does not exist: {args.config}")
        return 1

    return run_pipeline(args.input_folder, args.output_folder, args.config,
                        args.mappings, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
