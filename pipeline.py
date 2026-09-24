# One command for the whole anonymization pipeline.
#
#   1. anonymize metadata   (anonymize.py)
#   2. anonymize filenames  (rename_official_files.py)
#   3. verify the result    (dicom_anon_checker.py)
#
# Usage:
#   python pipeline.py <input_folder> <output_folder> [options]
#
# Given an input folder of DICOMs, produces:
#
#   <output_folder>/anonymized/           metadata anonymized, original filenames
#   <output_folder>/anonymized_renamed/   final deliverable: ANON- names, flattened
#   <output_folder>/filename_mappings.csv the re-identification key
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
import shutil
import sys

from anonymize import CSV_CONFIG_PATH, anonymize, folders_overlap
from dicom_anon_checker import check_folder
from rename_official_files import MAPPINGS_FILENAME, rename_folder

ANON_SUBDIR = "anonymized"
RENAMED_SUBDIR = "anonymized_renamed"


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
                 mappings_path=None, force=False, skip_check=False,
                 keep_intermediate=True, verbose=False):
    """Run all three stages. Returns an exit code: 0 on success, 1 on any failure."""
    anon_dir = os.path.join(output_folder, ANON_SUBDIR)
    renamed_dir = os.path.join(output_folder, RENAMED_SUBDIR)
    if mappings_path is None:
        mappings_path = os.path.join(output_folder, MAPPINGS_FILENAME)

    total_steps = 2 if skip_check else 3

    print("=" * 74)
    print("DICOM ANONYMIZATION PIPELINE")
    print("=" * 74)
    print(f"Input:            {input_folder}")
    print(f"Output:           {output_folder}")
    print(f"  metadata only:  {anon_dir}")
    print(f"  final output:   {renamed_dir}")
    print(f"  mapping key:    {mappings_path}")
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
    if not force:
        for path, label in ((anon_dir, "intermediate folder"),
                            (renamed_dir, "output folder")):
            if os.path.isdir(path) and os.listdir(path):
                print(f"\nERROR: {label} is not empty: {path}")
                print("       Remove it, pick another output folder, or pass --force.")
                return 1
        if os.path.exists(mappings_path):
            print(f"\nERROR: a mapping CSV already exists: {mappings_path}")
            print("       It is the only way to reverse an earlier run's renaming.")
            print("       Move it, pass --mappings, or pass --force to overwrite.")
            return 1

    # --- Stage 1: metadata ---------------------------------------------------
    banner(1, total_steps, "Anonymizing metadata")
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
    banner(2, total_steps, "Anonymizing filenames")
    with maybe_quiet(not verbose):
        mapping_rows, rename_failures = rename_folder(anon_dir, renamed_dir,
                                                      mappings_path, force)
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
    if skip_check:
        print("\nSkipping verification (--skip-check).")
        problems = 0
    else:
        banner(3, total_steps, "Verifying anonymization")
        # Compares the ORIGINAL input against the final renamed output, so the check
        # covers both stages at once rather than trusting the intermediate.
        problems = check_folder(input_folder, renamed_dir, mappings_path,
                                config_path, verbose)

    # --- Cleanup -------------------------------------------------------------
    if not keep_intermediate:
        shutil.rmtree(anon_dir, ignore_errors=True)
        print(f"\nRemoved intermediate folder: {anon_dir}")

    print()
    print("=" * 74)
    print("PIPELINE SUMMARY")
    print("=" * 74)
    print(f"Files processed:  {succeeded}")
    print(f"Final output:     {renamed_dir}")
    print(f"Mapping key:      {mappings_path}")
    if keep_intermediate:
        print(f"Intermediate:     {anon_dir}")
    if skip_check:
        print("Verification:     SKIPPED")
    elif problems:
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
    parser.add_argument("--force", action="store_true",
                        help="overwrite a non-empty output folder or existing mapping CSV")
    parser.add_argument("--skip-check", action="store_true",
                        help="do not run the verification stage")
    parser.add_argument("--no-intermediate", action="store_true",
                        help="delete the metadata-only folder once the run succeeds")
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
                        args.mappings, args.force, args.skip_check,
                        not args.no_intermediate, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
