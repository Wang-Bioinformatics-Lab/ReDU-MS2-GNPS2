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

    last_modified = _metadata_mtime()
    if _cached_df is not None and _cached_mtime == last_modified:
        return _cached_df

    with _cache_lock:
        if _cached_df is None or _cached_mtime != last_modified:
            _cached_df = _read_redu_sampledata()
            _cached_mtime = last_modified
        return _cached_df


def _metadata_mtime():
    # The table version: changes when the TSV or its Parquet copy is replaced, in either order (the later
    # mtime would not: the Parquet is always the newer file, and the workflow may publish it first)
    tsv = os.stat(config.PATH_TO_ORIGINAL_MAPPING_FILE)
    try:
        parquet = os.stat(config.PATH_TO_PARQUET_MAPPING_FILE)
        parquet = (parquet.st_mtime, parquet.st_size)
    except OSError:
        parquet = None
    return (tsv.st_mtime, tsv.st_size, parquet)


def _parquet_is_current():
    """The workflow's Parquet copy is used while it belongs to the current TSV: not older than it and
    written from a TSV of the same size (a TSV published without its copy, e.g. by an earlier workflow version,
    leaves an older copy behind)."""
    path = config.PATH_TO_PARQUET_MAPPING_FILE
    try:
        if os.path.getmtime(path) < os.path.getmtime(config.PATH_TO_ORIGINAL_MAPPING_FILE):
            return False
        import pyarrow.parquet as pq
        recorded = (pq.read_schema(path).metadata or {}).get(b'redu_tsv_bytes')
        return recorded == str(os.path.getsize(config.PATH_TO_ORIGINAL_MAPPING_FILE)).encode()
    except Exception:
        return False


_ARROW_THREADS = 8


def _read_parquet_sampledata(path):
    """The Parquet copy holds the TSV's text: the values pd.read_csv turns into NaN become NaN here
    too, so the table is the same as the one read from the TSV (~2 s instead of ~14 s)."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    from pandas._libs.parsers import STR_NA_VALUES

    # Each Arrow thread keeps its own allocator heap: with all cores of a large server the process
    # stays ~2 GB bigger, while 8 threads read the table nearly as fast as 64 (2.4 s vs 2.1 s)
    pa.set_cpu_count(min(pa.cpu_count(), _ARROW_THREADS))
    table = pq.read_table(path)
    na_values = pa.array(sorted(STR_NA_VALUES), type=pa.string())
    na_masks = {}
    for name in table.column_names:
        if pa.types.is_string(table.schema.field(name).type):
            mask = pc.is_in(table[name], value_set=na_values)
            if pc.any(mask).as_py():
                na_masks[name] = mask.to_numpy()
    # (one block per type, as read from the TSV or feather: with a block per column, every copy of the
    # whole table, e.g. the unfiltered view, merges them again, ~0.65 s per request)
    df = table.to_pandas(self_destruct=True)
    del table
    # (hands Arrow's freed buffers back to the system; pyarrow >= 9)
    getattr(pa.default_memory_pool(), 'release_unused', lambda: None)()
    for name, mask in na_masks.items():
        df.loc[mask, name] = np.nan
    return df


def _read_redu_sampledata():
    if _parquet_is_current():
        try:
            return _read_parquet_sampledata(config.PATH_TO_PARQUET_MAPPING_FILE)
        except Exception as e:
            print("Could not read the Parquet file, reading the TSV:", e)

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