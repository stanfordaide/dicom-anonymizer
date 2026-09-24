# Sample data

**Every value in these files is completely synthetic.** There is no real patient
data here. The patient names, MRNs, accession numbers, physician names, dates and
institution names are all invented, and the pixel data is a generated gradient
and not a real image.

- `sample_dicoms/` — 5 synthetic DICOMs, used as input
- `anonymized_output/` — the result of running the anonymizer over them

Both folders are regenerated output. To rebuild them from scratch, run from the
repo root:

```bash
python sample/make_sample_dicoms.py   # writes sample_dicoms/
python anonymize.py                   # writes anonymized_output/
```

See the main [README](../README.md) for more information.
