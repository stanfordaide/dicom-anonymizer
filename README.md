# DICOM Anonymizer

Anonymizer for DICOM studies. Point it at a folder of DICOMs and get back a folder of
anonymized DICOMs, with both the metadata and the filenames de-identified, plus a CSV
mapping the new filenames back to the originals.

This tool reads [dicom-data-dict.csv](dicom-data-dict.csv)—a hand-compiled sheet of DICOM tags, their types, their meanings, and how to deal with PHI associated with them—to perform the correct action (keep, remove, hash, empty, etc.) on the metadata of DICOM files in order to correctly anonymize. We provide a full pipeline for anonymization of metadata, anonymization of filenames, and verification of anonymization.

## Setup

The project ships a conda environment.

```bash
conda env create -f environment.yml
conda activate dicom-anonymizer
```

## Usage

One command for the whole thing — anonymize metadata, anonymize filenames, verify, and
compile a metadata audit CSV:

```bash
python pipeline.py <input_folder> <output_folder>
```

That produces four things inside the output folder:

```
<output_folder>/
  anonymized/                metadata anonymized, original filenames (intermediate)
  anonymized_renamed/        the deliverable: HIPSTER-XXXXXXXX.dcm, flattened
  filename_mappings.csv      the re-identification key
  anonymized_metadata.csv    every tag of the output, one row per file, for auditing
```

**Only `anonymized_renamed/` is shareable.** `filename_mappings.csv` maps every
`HIPSTER-` name back to the original filename, so it re-identifies the dataset and must
be kept private. It is written beside the deliverable rather than inside it for
exactly that reason.

Options: `--config CSV` for a different data dict, `--mappings PATH` to put the key
elsewhere, and `--verbose` for every per-tag decision instead of a summary.

**Every run needs a clean destination.** Before doing any work the pipeline refuses to
start if `anonymized/` or `anonymized_renamed/` already has anything in it, or if the
mapping CSV already exists. Mixing two runs in one folder would leave a mapping CSV that
no longer describes what is on disk, and overwriting a mapping CSV would destroy the only
route from an `HIPSTER-` name back to its original filename. There is no override: to re-run,
delete the previous output folder (and its mapping CSV) yourself, or point the run at a
different output folder. Nothing is ever deleted for you.

The pipeline exits non-zero if any stage fails, and stops rather than continuing with
incomplete output, so it can gate a larger process.

The output folder must not be inside the input folder (or vice versa), and all three
CLIs refuse that outright. Sibling folders under a shared parent are fine.

### Running the stages individually

Each stage is also a standalone CLI, which is what the pipeline calls into:

```bash
python anonymize.py <input_folder> <output_folder> [--config CSV]
python rename_official_files.py <input_folder> <output_folder> [--mappings PATH]
python dicom_anon_checker.py <original_folder> <anonymized_folder> [--mappings PATH] [--verbose]
python compile_metadata.py <folder> [--output CSV]
```

### Trying it on the sample data

```bash
python sample/make_sample_dicoms.py     # 5 synthetic DICOMs -> sample/sample_dicoms/
python pipeline.py sample/sample_dicoms sample/pipeline_output
```

`sample/pipeline_output` must not already exist from an earlier run — `rm -rf` it first,
or pass a different folder.

Or stage by stage, which is how the committed `sample/` folders were produced:

```bash
python anonymize.py sample/sample_dicoms sample/anonymized_output
python rename_official_files.py sample/anonymized_output sample/anonymized_renamed_output
python dicom_anon_checker.py sample/sample_dicoms sample/anonymized_renamed_output \
    --mappings sample/filename_mappings.csv
```

All commands are run from the repo root.

## How it works

`dicom-data-dict.csv` is the config. One row per DICOM tag, with columns
`Tag, Type, Definition, Example, Action_to_Take`. 274 rows total.
`anonymize.py` reads the `Action_to_Take` column and sorts every tag into:

| `Action_to_Take` | Behavior                                                    |
| ---------------- | ----------------------------------------------------------- |
| `keep`           | left untouched (98 rows)                                    |
| `empty`          | value replaced with `""` / `None` depending on VR (26 rows) |
| `remove`         | tag deleted entirely (136 rows)                             |
| anything else    | treated as a custom action (14 rows)                        |

Custom actions are then resolved by the `CUSTOM_TYPE_ONES` dict in `anonymize.py`,
which supports `hash`, `random jitter`, or a literal replacement value. It lives at
module level so `dicom_anon_checker.py` can import it and verify against the same
definitions instead of keeping its own copy.

Any tag **not** in the CSV is removed. The CSV was built from the official DICOM tag
list, so a tag absent from it is either a private vendor tag or something no valid file
needs. **If this causes issues in the future (i.e. accidentally removing a tag that was necessary for a certain modality to compile), note that there is a set of explicitly allowed tags (NEVER_REMOVE_UNLISTED) in anonymize.py that will not be removed from the DICOMs, allowing for the customization of extra allowed tags.**

Hashing is consistent within a run: the same `PatientID` always maps to the same
hash, and the same `StudyInstanceUID`/`SeriesInstanceUID` always map to the same
new UID, so studies and series stay grouped. Date jitter is ±30 days, chosen once
per patient, so intervals within a patient are preserved.

There is also a separate pass that strips the substring `LPCH` from _every_ text
value in the file. Binary values such as pixel data are skipped.

### Note on the `Action_to_Take` values

The 14 custom rows use prose values like `keep but populate with 0` and
`keep but hash`. `get_tags_of_types()` doesn't parse these — it only recognizes
the exact strings `keep`, `empty` and `remove`, and passes anything else through
as a literal replacement value. The `CUSTOM_TYPE_ONES` dict is what actually defines
those 14 behaviors. **This is intentional** — the CSV is the human-readable record of intent, and
`CUSTOM_TYPE_ONES` is the machine-readable implementation. The consequence to be
aware of: the two lists must be kept in sync by hand. If you add a new custom
action to the CSV without adding a matching entry to `CUSTOM_TYPE_ONES`, that
tag's value will be silently overwritten with the literal prose string from the
CSV (e.g. a tag would end up containing the text `keep but populate with 0`).
`dicom_anon_checker.py` reports a `WARN` when it sees this, so it gets caught.

## Files

| File                           | Purpose                                                                                                                                                                                              |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pipeline.py`                  | One command for all four stages. The normal entry point.                                                                                                                                             |
| `anonymize.py`                 | Metadata anonymization.                                                                                                                                                                              |
| `dicom-data-dict.csv`          | Tag-by-tag anonymization config.                                                                                                                                                                     |
| `environment.yml`              | Conda environment definition. The primary dependency spec.                                                                                                                                           |
| `sample/`                      | Test data and generated output, kept out of the project root.                                                                                                                                        |
| `sample/make_sample_dicoms.py` | Generates synthetic test DICOMs (no real patient data) into `sample/sample_dicoms/`.                                                                                                                 |
| `compile_metadata.py`          | Dumps every tag of every DICOM in a folder to a wide CSV. Generated the tag names used in `dicom-data-dict.csv`, hence the `_Seq0_` flattening convention. Runs as pipeline stage 4, and standalone. |
| `dicom_anon_checker.py`        | Verifies anonymization: checks every data dict rule was honored, reports to the terminal, exits non-zero on failure. Has its own CLI.                                                                |
| `rename_official_files.py`     | Filename anonymization: copies a folder to `HIPSTER-XXXXXXXX.dcm` names and writes the mapping CSV. Has its own CLI.                                                                                    |

## Test data

`sample/make_sample_dicoms.py` writes 5 synthetic DICOMs into
`sample/sample_dicoms/`. All values are invented; there is no real patient data.
They're built to exercise the interesting paths:

- all 10 distinct `Action_to_Take` values (52 `remove`, 30 `keep`, 16 `empty` rows hit per file)
- all 14 `CUSTOM_TYPE_ONES` overrides
- 28 nested sequence rows, including a multi-item `PerformedProtocolCodeSequence`
  so that `_Seq0_`, `_Seq1_` and `_Seq2_` all appear
- `LPCH` substrings in 16 different elements, including inside sequences
- two files sharing a `PatientID`/`StudyInstanceUID`/`SeriesInstanceUID`, to check
  hashing stays consistent across files
- private vendor tags (odd group `0009`) carrying a name and MRN, plus a private
  _sequence_ with PHI nested inside it, so the strict allowlist is actually exercised
- one file (`edge_case_blank_fields.dcm`) with blank values throughout
- filenames that themselves contain PHI
