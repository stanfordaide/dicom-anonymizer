# Sample data

**Every value in these files is completely synthetic.** There is no real patient
data here. The patient names, MRNs, accession numbers, physician names, dates and
institution names are all invented, and the pixel data is a generated gradient
and not a real image. The files also carry fake private vendor tags holding a name and
MRN, so the anonymizer's handling of private tags is exercised by the sample run.

- `sample_dicoms/` — 5 synthetic DICOMs, used as input
- `anonymized_output/` — the result of running the anonymizer over them
- `anonymized_renamed_output/` — the same files with filenames anonymized to `HIPSTER-XXXXXXXX.dcm`
- `filename_mappings.csv` — maps each `HIPSTER-` name back to its original filename
- `anonymized_metadata.csv` — every tag of the anonymized output, one row per file

All of these are regenerated output. To rebuild them from scratch, run from the
repo root:

```bash
python sample/make_sample_dicoms.py     # writes sample_dicoms/
python anonymize.py sample/sample_dicoms sample/anonymized_output
python rename_official_files.py sample/anonymized_output sample/anonymized_renamed_output
python dicom_anon_checker.py sample/sample_dicoms sample/anonymized_renamed_output \
    --mappings sample/filename_mappings.csv
python compile_metadata.py sample/anonymized_renamed_output \
    --output sample/anonymized_metadata.csv
```

Delete `sample_dicoms/`, `anonymized_output/`, `anonymized_renamed_output/` and
`filename_mappings.csv` first, since the rename step refuses to overwrite them.

The same thing in one command, writing to a separate folder so it does not collide
with the committed output above:

```bash
python pipeline.py sample/sample_dicoms sample/pipeline_output
```

On a real dataset, `filename_mappings.csv` is the re-identification key and must be
kept separate from the anonymized files. Here it maps synthetic names to synthetic
names, so it is safe to commit.

See the main [README](../README.md) for more information.
