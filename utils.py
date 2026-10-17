import pandas as pd
import numpy as np
import config
import os
import threading

# The table is ~1M rows; keep one parsed copy per process and only reload it when the
# workflow writes a new TSV, instead of re-reading it from disk on every callback.
_cache_lock = threading.Lock()
_cached_df = None
_cached_mtime = None


def _load_redu_sampledata():
    global _cached_df, _cached_mtime

    last_modified = os.path.getmtime(config.PATH_TO_ORIGINAL_MAPPING_FILE)
    if _cached_df is not None and _cached_mtime == last_modified:
        return _cached_df

    with _cache_lock:
        if _cached_df is None or _cached_mtime != last_modified:
            _cached_df = _read_redu_sampledata()
            _cached_mtime = last_modified
        return _cached_df


def _metadata_mtime():
    return os.path.getmtime(config.PATH_TO_ORIGINAL_MAPPING_FILE)


def _read_redu_sampledata():
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
        try:
            return pd.read_feather(path_to_binary_version)
        except Exception as e:
            print("Could not read binary file, rereading TSV:", e)

    # Everything is read as text so that a new or changed column with mixed values
    # cannot break parsing or the feather cache; only known count columns become numbers.
    df_redu = pd.read_csv(config.PATH_TO_ORIGINAL_MAPPING_FILE, sep='\t', dtype=str)

    if 'MS2spectra_count' in df_redu.columns:
        # nan, inf or unparsable values become -1
        counts = pd.to_numeric(df_redu['MS2spectra_count'], errors='coerce')
        df_redu['MS2spectra_count'] = counts.replace([np.inf, -np.inf], np.nan).fillna(-1).astype(int)

    try:
        df_redu.to_feather(path_to_binary_version)
    except Exception as e:
        print("Could not write binary file, continuing without it:", e)

    return df_redu

def _metadata_last_modified():
    # Checking when this file was last modified
    last_modified = os.path.getmtime(config.PATH_TO_ORIGINAL_MAPPING_FILE)

    # Making this PST time and human readable
    last_modified = pd.to_datetime(last_modified, unit='s').tz_localize('UTC').tz_convert('US/Pacific')

    return last_modified