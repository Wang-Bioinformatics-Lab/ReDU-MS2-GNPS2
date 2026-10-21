import os

PATH_TO_ORIGINAL_MAPPING_FILE = os.environ.get("REDU_METADATA_PATH", "/app/workflows/PublicDataset_ReDU_Metadata_Workflow/nf_output/merged_metadata.tsv") #global ReDU metadata

# Parquet copy of the same table that the workflow writes next to the TSV; the app reads it instead of the
# TSV while it belongs to the current TSV (see utils._parquet_is_current)
PATH_TO_PARQUET_MAPPING_FILE = os.environ.get("REDU_METADATA_PARQUET_PATH", os.path.splitext(PATH_TO_ORIGINAL_MAPPING_FILE)[0] + ".parquet")

# The workflow's rows per repository and each repository's last update (last_update, last_run_status), written next
# to the table by the run that wrote it
PATH_TO_SOURCE_SUMMARY_FILE = os.path.join(os.path.dirname(PATH_TO_ORIGINAL_MAPPING_FILE), "source_summary.tsv")
