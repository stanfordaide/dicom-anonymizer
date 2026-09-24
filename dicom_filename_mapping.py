# # map original input dicom filenames to anonymized filenames outputted by CTP.

# # in anonymizer script, anonymize everything except AccessionNumber
# # create a function that receives dictionary of {AccessionNumber : filename} of original files, and anon files
# # use those dictionaries to map the ones with the same SOPInstanceID
# # use pydicom to manually remove AccessionNumber from the file after mapping to original

# from pydicom import dcmread
# import os
# import pickle

# def create_dictionary_uid_to_filename(image_dir):
#     uid_to_filepath_dict = {}

#     for root, _, files in os.walk(image_dir):
#         for file in files:
#             if ".dcm" in file:
#                 # get filepath and sopinstanceuid of dicom image
#                 dcm_filepath = os.path.join(root, file)
#                 dcm_file = dcmread(dcm_filepath)
#                 accessionnumber_tag = (0x0008,0x0018)
#                 try:
#                     # get SOPInstanceUID by numerical tag
#                     accessionnumber = dcm_file[accessionnumber_tag].value
#                     # check if duplicate exists in dict
#                     if accessionnumber in uid_to_filepath_dict:
#                         print("duplicate accessionnumber", accessionnumber, "filename:", file)
#                     else:
#                         # store {SOPInstanceUID : filepath} in dict
#                         uid_to_filepath_dict[accessionnumber] = dcm_filepath
#                 except Exception as e:
#                     print("something went wrong accessing accessionnumber from", file)
#                     print(e)
    
#     return uid_to_filepath_dict

# # returns a dictionary mapping the filepath of the non-anonymized dicom image to anonymized
# def map_filepaths(nonanon_mapping_dict, anon_mapping_dict):
#     anon_to_nonanon_filepaths = {}
    
#     for accessionnumber in nonanon_mapping_dict:
#         # find anonymized and non-anonymized filenames with matching SOPInstanceUID
#         if accessionnumber in anon_mapping_dict:
#             nonanon_filepath = nonanon_mapping_dict[accessionnumber]
#             anon_filepath = anon_mapping_dict[accessionnumber]
#             anon_to_nonanon_filepaths[anon_filepath] = nonanon_filepath

#             # remove SOPInstanceUID from anon_filename to complete anonymization
#             try:
#                 dcm_file = dcmread(anon_filepath)
#                 accessionnumber_tag = (0x0008,0x0018)
#                 # replace element with empty string
#                 del dcm_file[accessionnumber_tag]
#             except Exception as e:
#                 print("there was an error:", e, ", while anonymizing", anon_filepath)
#         else:
#             print("could not find matching accessionnumber for", nonanon_mapping_dict[accessionnumber])
    
#     return anon_to_nonanon_filepaths

# non_anon_dir = "images-anon"
# non_anon_uid_to_filepath = create_dictionary_uid_to_filename(non_anon_dir)
# anon_dir = "CTP/output"
# anon_uid_to_filepath = create_dictionary_uid_to_filename(anon_dir)
# anon_to_nonanon_mappings = map_filepaths(non_anon_uid_to_filepath, anon_uid_to_filepath)

# if __name__ == "__main__":
#     non_anon_dir = "images-anon"
#     non_anon_uid_to_filepath = create_dictionary_uid_to_filename(non_anon_dir)

#     anon_dir = "CTP/output"
#     anon_uid_to_filepath = create_dictionary_uid_to_filename(anon_dir)

#     print(non_anon_uid_to_filepath)
#     print(anon_uid_to_filepath)

#     anon_to_nonanon_mappings = map_filepaths(non_anon_uid_to_filepath, anon_uid_to_filepath)
#     print(anon_to_nonanon_mappings)
#     filename = 'exported_dict_0.pkl'
#     try:
#         with open(filename, 'wb') as file:
#             pickle.dump(anon_to_nonanon_mappings, file)
#         print(f"Dictionary successfully exported")
#     except FileNotFoundError:
#         print(f"Error: The folder does not exist.")
#     except Exception as e:
#         print(f"An error occurred: {e}")
    

from pydicom import dcmread
import os
import pickle
import shutil

def create_dictionary_uid_to_filename(image_dir):
    uid_to_filepath_dict = {}

    for root, _, files in os.walk(image_dir):
        for file in files:
            if ".dcm" in file:
                dcm_filepath = os.path.join(root, file)
                try:
                    dcm_file = dcmread(dcm_filepath)
                    sopinstanceuid_tag = (0x0008, 0x0018)  # SOPInstanceUID
                    sopinstanceuid = dcm_file[sopinstanceuid_tag].value
                    
                    if sopinstanceuid in uid_to_filepath_dict:
                        print(f"Duplicate SOPInstanceUID {sopinstanceuid} in file: {file}")
                    else:
                        uid_to_filepath_dict[sopinstanceuid] = dcm_filepath
                        
                except Exception as e:
                    print(f"Error accessing SOPInstanceUID from {file}: {e}")
    
    return uid_to_filepath_dict
def map_and_copy_files(nonanon_mapping_dict, anon_mapping_dict, output_dir):
    """Map anonymized files to original filenames and copy to new directory"""
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    copied_count = 0
    
    for sopinstanceuid in nonanon_mapping_dict:
        if sopinstanceuid in anon_mapping_dict:
            nonanon_filepath = nonanon_mapping_dict[sopinstanceuid]
            anon_filepath = anon_mapping_dict[sopinstanceuid]
            
            # Get original filename
            original_filename = os.path.basename(nonanon_filepath)
            new_filepath = os.path.join(output_dir, original_filename)
            
            try:
                # Read the anonymized file
                dcm_file = dcmread(anon_filepath)
                
                # Remove SOPInstanceUID to complete anonymization
                sopinstanceuid_tag = (0x0008, 0x0018)
                if sopinstanceuid_tag in dcm_file:
                    del dcm_file[sopinstanceuid_tag]

                # Remove LPCH from ALL tags (like remove_lpch function)
                lpch_removed = False
                for element in dcm_file.iterall():
                    if hasattr(element, 'value') and isinstance(element.value, str) and "LPCH" in element.value:
                        original_value = element.value
                        # Remove LPCH with various spacing patterns
                        new_value = original_value.replace("LPCH ", "").replace(" LPCH", "").replace("LPCH", "")
                        # Clean up extra spaces
                        new_value = " ".join(new_value.split())
                        element.value = new_value
                        print(f"Removed LPCH from {element.keyword or element.tag}: '{original_value}' -> '{new_value}'")
                        lpch_removed = True
                
                if lpch_removed:
                    print(f"LPCH cleanup completed for {original_filename}")
                
                # Save to new directory with original filename
                dcm_file.save_as(new_filepath)
                
                print(f"Copied: {os.path.basename(anon_filepath)} -> {original_filename}")
                copied_count += 1
                
            except Exception as e:
                print(f"Error processing {anon_filepath}: {e}")
        else:
            original_filename = os.path.basename(nonanon_mapping_dict[sopinstanceuid])
            print(f"Could not find matching SOPInstanceUID for {original_filename}")
    
    print(f"Successfully copied {copied_count} files to {output_dir}")
    return copied_count

if __name__ == "__main__":
    # Directories
    non_anon_dir = "images-anon"        # Original filenames (before anonymization)
    anon_dir = "CTP/output"             # Anonymized files with random filenames
    output_dir = "new-anon-images-copy-1" # New directory for final anonymized files
    
    print("Creating mappings...")
    non_anon_uid_to_filepath = create_dictionary_uid_to_filename(non_anon_dir)
    anon_uid_to_filepath = create_dictionary_uid_to_filename(anon_dir)
    
    print(f"Found {len(non_anon_uid_to_filepath)} original files")
    print(f"Found {len(anon_uid_to_filepath)} anonymized files")
    
    # Map and copy files to new directory
    print(f"Copying files to {output_dir}...")
    copied_count = map_and_copy_files(non_anon_uid_to_filepath, anon_uid_to_filepath, output_dir)
    
    print("Process complete!")
    print(f"Anonymized files with original filenames are in: {output_dir}")
    print(f"SOPInstanceUID has been removed from all files")
    
    # Optional: Create mapping dictionary for reference
    anon_to_nonanon_mappings = {}
    for sopinstanceuid in non_anon_uid_to_filepath:
        if sopinstanceuid in anon_uid_to_filepath:
            original_filename = os.path.basename(non_anon_uid_to_filepath[sopinstanceuid])
            new_filepath = os.path.join(output_dir, original_filename)
            anon_to_nonanon_mappings[new_filepath] = non_anon_uid_to_filepath[sopinstanceuid]
    
    # Export mapping for reference
    filename = 'new_to_old_mappings.pkl'
    try:
        with open(filename, 'wb') as file:
            pickle.dump(anon_to_nonanon_mappings, file)
        print(f"Mapping dictionary exported to {filename}")
    except Exception as e:
        print(f"Error exporting dictionary: {e}")