# Generate a small set of synthetic DICOM files for testing the anonymizer.
#
# These contain NO real patient data - every value is invented. They are built to
# exercise the interesting paths in anonymize.py:
#   - tags the CSV says to "keep", "empty" and "remove"
#   - all 14 custom_type_ones overrides (hash / jitter / literal replacement)
#   - PHI nested inside sequences, including multi-item sequences (_Seq0_, _Seq1_)
#   - "LPCH" substrings that remove_lpch() should strip
#   - a PatientID shared across two files, to check hashing stays consistent
#   - filenames that themselves contain PHI, for the renaming step
#
# Usage: python sample/make_sample_dicoms.py [output_folder]
#
# With no argument, writes to sample_dicoms/ next to this script, so it behaves the
# same whether you run it from the repo root or from inside sample/.

import argparse
import os

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

# Digital X-Ray Image Storage - For Presentation (matches the CSV's examples)
SOP_CLASS_UID = "1.2.840.10008.5.1.4.1.1.1.1"


def make_code_item(value, designator, meaning, version=None):
    """One item of a code sequence."""
    item = Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = designator
    item.CodeMeaning = meaning
    if version is not None:
        item.CodingSchemeVersion = version
    return item


def build_dataset(
    patient_name,
    patient_id,
    birth_date,
    sex,
    age,
    accession,
    study_uid,
    series_uid,
    study_date,
    institution,
    station,
    physician,
    laterality,
    instance_number,
):
    ds = Dataset()

    # --- identifiers / structure (CSV: keep) ---
    ds.SpecificCharacterSet = "ISO_IR 100"
    ds.ImageType = ["ORIGINAL", "PRIMARY", ""]
    ds.SOPClassUID = SOP_CLASS_UID
    ds.SOPInstanceUID = generate_uid()
    ds.StudyInstanceUID = study_uid          # custom: hash
    ds.SeriesInstanceUID = series_uid        # custom: hash
    ds.StudyID = "ST-0001"
    ds.Modality = "DX"
    ds.BodyPartExamined = "CHEST"

    # --- direct PHI (CSV: empty) ---
    ds.PatientName = patient_name
    ds.PatientBirthDate = birth_date
    ds.PatientSex = sex
    ds.AccessionNumber = accession
    ds.StudyDate = study_date
    ds.ReferringPhysicianName = physician
    ds.Manufacturer = "SIEMENS"
    ds.SeriesNumber = instance_number
    ds.ImageLaterality = laterality
    ds.PositionerType = "NONE"
    ds.PositionerPrimaryAngle = 0.0
    ds.PositionerSecondaryAngle = 0.0
    ds.TableMotion = "STATIC"

    # --- PHI-bearing tags (CSV: remove) ---
    ds.PatientID = patient_id                # custom: hash (so it must survive, hashed)
    ds.PatientAge = age
    ds.SeriesDate = study_date
    ds.AcquisitionDate = study_date
    ds.SeriesDescription = f"{institution} - CHEST PA"
    ds.ManufacturerModelName = "Ysio Max"
    ds.SoftwareVersions = "VA10B"
    ds.InstanceNumber = instance_number
    ds.InstanceCreationDate = study_date
    ds.InstanceCreationTime = "101500"
    ds.PerformedProcedureStepStartDate = study_date
    ds.PerformedProcedureStepEndDate = study_date
    ds.IrradiationEventUID = generate_uid()
    ds.DetectorManufacturerName = "SIEMENS"
    ds.DetectorManufacturerModelName = "MAX-DET"
    ds.DetectorDescription = f"Detector at {station}"
    ds.AcquisitionNumber = instance_number
    ds.ExposureInmAs = 12
    ds.ExposureTimeInuS = 25000
    ds.XRayTubeCurrentInuA = 320000
    ds.EntranceDoseInmGy = 2
    ds.OrganDose = 1.5
    ds.TotalNumberOfExposures = 1
    ds.ExposuresOnPlate = 1
    ds.SpatialResolution = 3.5
    ds.ExposureStatus = "NORMAL"
    ds.CalibrationImage = "NO"
    ds.PatientIdentityRemoved = "NO"
    ds.VOILUTFunction = "LINEAR"

    # --- the 14 custom_type_ones overrides ---
    ds.ContentDate = study_date              # random jitter
    ds.FilterMaterial = "ALUMINUM"           # -> RHODIUM
    ds.ShutterShape = "CIRCULAR"             # -> RECTANGULAR
    ds.RadiationSetting = "GR"               # -> SC
    ds.CollimatorLeftVerticalEdge = 120      # -> 0
    ds.CollimatorRightVerticalEdge = 2880    # -> 0
    ds.CollimatorUpperHorizontalEdge = 140   # -> 0
    ds.CollimatorLowerHorizontalEdge = 2760  # -> 0
    ds.DistanceSourceToIsocenter = 1200      # -> 1
    ds.Trim = "5"                            # -> 1

    # --- LPCH substrings, which remove_lpch() should strip ---
    ds.StudyDescription = "LPCH - CHEST 2 VIEW"
    ds.InstitutionName = f"LPCH {institution}"
    ds.InstitutionAddress = "725 Welch Rd, Palo Alto CA"
    ds.StationName = f"{station} LPCH"[:16]  # SH is capped at 16 chars
    ds.ProtocolName = "LPCH CHEST ROUTINE"
    ds.OperatorsName = "TECH^LPCH"
    ds.PerformingPhysicianName = physician
    ds.RequestingPhysician = physician
    ds.RequestedProcedureDescription = "LPCH - XR CHEST"
    ds.DeviceSerialNumber = "SN-88213"

    # --- nested PHI: single-item sequences (_Seq0_ in the CSV) ---
    ds.ProcedureCodeSequence = Sequence([
        make_code_item("XRCHEST2V", "LPCHCODES", "LPCH - XR Chest 2 View", version="1.4")
    ])
    ds.RequestedProcedureCodeSequence = Sequence([
        make_code_item("RP-CHEST", "LPCHCODES", "Requested LPCH Chest")
    ])
    ds.AnatomicRegionSequence = Sequence([
        make_code_item("T-D3000", "SRT", "Chest")
    ])

    contributing = Dataset()
    contributing.Manufacturer = "LPCH IMAGING WORKSTATION"   # custom: hash
    contributing.InstitutionName = f"LPCH {institution}"     # remove
    contributing.StationName = station                       # remove
    # DT must be a valid datetime, so leave it out when there is no date at all
    if study_date:
        contributing.ContributionDateTime = f"{study_date}101500"  # remove
    contributing.PurposeOfReferenceCodeSequence = Sequence([
        make_code_item("109103", "DCM", "Modifying Equipment")
    ])
    ds.ContributingEquipmentSequence = Sequence([contributing])

    # --- nested PHI: multi-item sequence, so _Seq0_ AND _Seq1_ both appear ---
    ds.PerformedProtocolCodeSequence = Sequence([
        make_code_item("PROTO-1", "LPCHCODES", f"LPCH protocol for {patient_name}", version="2.0"),
        make_code_item("PROTO-2", "LPCHCODES", f"Read by {physician}", version="2.0"),
        make_code_item("PROTO-3", "LPCHCODES", f"Acquired at {station}"),
    ])

    # --- private vendor tags, the way a real scanner writes them ---
    # Odd group number = private. Real files are full of these and they routinely carry
    # PHI, so the strict allowlist has to clear them. One is a private *sequence* with
    # PHI nested inside, which is the harder case.
    block = ds.private_block(0x0009, "ACME_IMAGING", create=True)
    block.add_new(0x01, 'LO', patient_name or "EMPTY")
    block.add_new(0x02, 'LO', patient_id)
    block.add_new(0x03, 'LO', f"Read by {physician} at LPCH")
    private_item = Dataset()
    private_item.PatientName = patient_name
    private_item.AccessionNumber = accession
    block.add_new(0x10, 'SQ', Sequence([private_item]))

    # --- minimal but valid image data (values are meaningless) ---
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = 8
    ds.Columns = 8
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelSpacing = [0.139, 0.139]
    ds.WindowCenter = 2048
    ds.WindowWidth = 4096
    ds.RescaleIntercept = 0
    ds.RescaleSlope = 1
    ds.RescaleType = "US"
    ds.PixelData = (np.arange(64, dtype=np.uint16) * 64).tobytes()

    # --- file meta ---
    fm = FileMetaDataset()
    fm.MediaStorageSOPClassUID = SOP_CLASS_UID
    fm.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    fm.TransferSyntaxUID = ExplicitVRLittleEndian
    fm.ImplementationClassUID = generate_uid()
    ds.file_meta = fm
    ds.preamble = b"\x00" * 128

    return ds


# Two files share a PatientID/Study/Series so we can confirm hashing is consistent.
STUDY_A = generate_uid()
SERIES_A = generate_uid()

SAMPLES = [
    # filename intentionally contains PHI, for the future renaming step
    ("DOE_JANE_MRN4451102_chest_1.dcm", dict(
        patient_name="DOE^JANE^A", patient_id="MRN4451102", birth_date="19780412",
        sex="F", age="047Y", accession="ACC00099211", study_uid=STUDY_A, series_uid=SERIES_A,
        study_date="20240115", institution="Lucile Packard Childrens Hospital",
        station="XR-ROOM-3", physician="SMITH^ROBERT^J^MD", laterality="L",
        instance_number=1)),
    ("DOE_JANE_MRN4451102_chest_2.dcm", dict(
        patient_name="DOE^JANE^A", patient_id="MRN4451102", birth_date="19780412",
        sex="F", age="047Y", accession="ACC00099211", study_uid=STUDY_A, series_uid=SERIES_A,
        study_date="20240115", institution="Lucile Packard Childrens Hospital",
        station="XR-ROOM-3", physician="SMITH^ROBERT^J^MD", laterality="R",
        instance_number=2)),
    ("GARCIA_LUIS_MRN7782341.dcm", dict(
        patient_name="GARCIA^LUIS", patient_id="MRN7782341", birth_date="19650830",
        sex="M", age="060Y", accession="ACC00099212", study_uid=generate_uid(),
        series_uid=generate_uid(), study_date="20240220",
        institution="LPCH Main Campus", station="XR-ROOM-1",
        physician="OKAFOR^AMARA^MD", laterality="L", instance_number=1)),
    ("patient_003_20240301.dcm", dict(
        patient_name="LEE^MIN^SOO", patient_id="MRN1029384", birth_date="20010105",
        sex="M", age="024Y", accession="ACC00099213", study_uid=generate_uid(),
        series_uid=generate_uid(), study_date="20240301",
        institution="LPCH Satellite Clinic", station="XR-PORTABLE-2",
        physician="NGUYEN^THANH^MD", laterality="R", instance_number=1)),
    ("edge_case_blank_fields.dcm", dict(
        patient_name="", patient_id="MRN0000001", birth_date="", sex="",
        age="", accession="", study_uid=generate_uid(), series_uid=generate_uid(),
        study_date="", institution="LPCH", station="LPCH",
        physician="", laterality="", instance_number=1)),
]


def main():
    default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_dicoms")
    # argparse rather than reading sys.argv[1] directly: a bare sys.argv[1] treats any
    # argument as the output folder, so `--help` silently created a folder named "--help"
    parser = argparse.ArgumentParser(
        description="Generate synthetic DICOM files for testing the anonymizer. "
                    "All values are invented; no real patient data is involved.")
    parser.add_argument("output_folder", nargs="?", default=default_dir,
                        help="where to write the files (default: sample_dicoms/ beside "
                             "this script)")
    args = parser.parse_args()
    out_dir = args.output_folder
    os.makedirs(out_dir, exist_ok=True)

    for filename, kwargs in SAMPLES:
        ds = build_dataset(**kwargs)
        path = os.path.join(out_dir, filename)
        ds.save_as(path, enforce_file_format=True)
        print(f"wrote {path}")

    print(f"\n{len(SAMPLES)} synthetic DICOM files written to {out_dir}/")
    print("All values are invented - these contain no real patient data.")


if __name__ == "__main__":
    main()
