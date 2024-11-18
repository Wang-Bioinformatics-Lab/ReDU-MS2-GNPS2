import pandas as pd
import numpy as np
import config
import os


def _load_redu_sampledata():
    path_to_binary_version = "./database/merged_metadata.feather"

    # Checking age of files
    last_modified = os.path.getmtime(config.PATH_TO_ORIGINAL_MAPPING_FILE)

    use_feather = True

    # Checking if the feather file is older than the TSV file
    if os.path.exists(path_to_binary_version):
        last_modified_binary = os.path.getmtime(path_to_binary_version)

        # If the feather file is older than the TSV file, we need to regenerate it
        if last_modified_binary < last_modified:
            print("Binary file is older than TSV file, regenerating")
            use_feather = False
    else:
        print("Binary file does not exist, creating")
        use_feather = False
    
    if use_feather:
        df_redu = pd.read_feather(path_to_binary_version)
    else:
        df_redu = pd.read_csv(config.PATH_TO_ORIGINAL_MAPPING_FILE, sep='\t')
        df_redu['YearOfAnalysis'] = df_redu['YearOfAnalysis'].astype(str)

        # making nan or inf to -1 in the MS2spectra_count column
        df_redu['MS2spectra_count'] = df_redu['MS2spectra_count'].replace([np.inf, -np.inf], -1)
        # making nan to -1
        df_redu['MS2spectra_count'] = df_redu['MS2spectra_count'].fillna(-1)
        # casting to int
        df_redu['MS2spectra_count'] = df_redu['MS2spectra_count'].astype(int)

        df_redu.to_feather(path_to_binary_version)

    return df_redu

def _metadata_last_modified():
    # Checking when this file was last modified
    last_modified = os.path.getmtime(config.PATH_TO_ORIGINAL_MAPPING_FILE)

    # Making this PST time and human readable
    last_modified = pd.to_datetime(last_modified, unit='s').tz_localize('UTC').tz_convert('US/Pacific')

    return last_modified