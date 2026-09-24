# Sample data

**Every value in these files is completely synthetic.** There is no real patient
data here. The patient names, MRNs, accession numbers, physician names, dates and
institution names are all invented, and the pixel data is a generated gradient
and not a real image.

- `sample_dicoms/` — 5 synthetic DICOMs, used as input
- `anonymized_output/` — the result of running the anonymizer over them
- `anonymized_renamed_output/` — the same files with filenames anonymized to `ANON-XXXXXXXX.dcm`
- `filename_mappings.csv` — maps each `ANON-` name back to its original filename

All of these are regenerated output. To rebuild them from scratch, run from the
repo root:

```bash
python sample/make_sample_dicoms.py   # writes sample_dicoms/
python anonymize.py                   # writes anonymized_output/
# writes anonymized_renamed_output/ and filename_mappings.csv
python rename_official_files.py sample/anonymized_output sample/anonymized_renamed_output
```

Note that the last step refuses to overwrite an existing `anonymized_renamed_output/` or
`filename_mappings.csv`, so delete those first when regenerating.

On a real dataset, `filename_mappings.csv` is the re-identification key and must be
kept separate from the anonymized files. Here it maps synthetic names to synthetic
names, so it is safe to commit.

See the main [README](../README.md) for more information.
