# check if a dicom file has been successfully anonymized based on configurations in anonymization script.

from pydicom import dcmread
import csv

def is_anonymized(filepath_to_original_dcm, filepath_to_anon_dcm, tags_to_check):
    filepath_to_original_dcm = "data_analysis/variability_check/dataset-images/images/" + filepath_to_original_dcm
    filepath_to_anon_dcm = "dataset/images/" + filepath_to_anon_dcm
    og_dcm = dcmread(filepath_to_original_dcm)
    anon_dcm = dcmread(filepath_to_anon_dcm)
    count_done = 0
    count_failed = 0

    # set by default that it was anonymized - if any single tag fails, set to False
    anonymized = True

    # create a dictionary: {tag : wasRemoved(bool)} to keep track of which tags passed and which failed
    anonymized_tags_dict = {}

    # go through each tag: see if it existed in the original dcm, and if so, check if it was anonymized in the anon dcm
    for tag in tags_to_check:
        # ignore tag if didn't exist in original dcm
        if tag in og_dcm:
            # check if the tag exists in anonymized dcm
            if tag in anon_dcm:
                # if tag in anonymized data is the same as original, failed anonymization (unless original was blank)
                if anon_dcm[tag].value == og_dcm[tag].value and og_dcm[tag].value != '':
                    anonymized_tags_dict[tag] = False
                    print("tag", tag, "was not anonymized")
                    count_failed += 1
                    anonymized = False
                else:
                    anonymized_tags_dict[tag] = True
                    #print("tag", tag, "worked: cleared/edited")
                    count_done += 1
            else:
                # if tag does not exist in anonymized dcm it was removed -- consider it anonymized
                anonymized_tags_dict[tag] = True
                # print("tag", tag, "worked: removed")
                count_done += 1
    
    print("done:", count_done, "failed:", count_failed)
    
    return anonymized, anonymized_tags_dict

# return a set of numerical dicom header tags that were intended to be removed or modified in the script
def get_removed_tags():
    tags_to_check = dict()
    script_filepath = "data_analysis/dataset_creation/anonymizer/CTP/scripts/dicom-anonymizer.script"
    anonymization_functions = ["@remove", "@empty", "@hash", "@increment", "@replace"]

    try:
        with open(script_filepath, 'r') as file:
            for line in file:
                # check if the line contains any of the anonymization/modification functions
                matched_function = None
                for function in anonymization_functions:
                    if function in line:
                        matched_function = function
                        break
                
                if matched_function:
                    # get the 8-digit dicom tag
                    tag = line[14:22]
                    tag = (int(tag[:4], 16), int(tag[4:], 16))
                    tags_to_check[tag] = matched_function
    except FileNotFoundError:
        print(f"Error: The file '{script_filepath}' was not found")
    except Exception as e:
        print(f"An error occurred: {e}")

    return tags_to_check

def get_nonanon_to_anon_mappings():
    nonanon_to_anon_mappings = {}

    # Open the CSV file
    with open('dataset-copy/new-to-old-mappings-copy.csv', 'r') as file:
        reader = csv.reader(file)
        # Optional: Skip the header row if present
        next(reader, None) 

        # Iterate through each row in the CSV
        for row in reader:
            if len(row) == 2:  # Ensure the row has two columns
                key = row[0]
                value = row[1]
                nonanon_to_anon_mappings[key] = value

    return nonanon_to_anon_mappings

if __name__ == "__main__":
    tags_to_check = get_removed_tags()
    nonanon_to_anon_mappings = get_nonanon_to_anon_mappings()
    
    count_succeeded = 0
    count_failed = 0
    for file in nonanon_to_anon_mappings:
        anonymized, anonymized_tags_dict = is_anonymized(file, nonanon_to_anon_mappings[file], tags_to_check)
        print(anonymized)
        if (anonymized):
            count_succeeded += 1
        else:
            count_failed += 1
    print("count successfully anonymized:", count_succeeded, "count failed:", count_failed)