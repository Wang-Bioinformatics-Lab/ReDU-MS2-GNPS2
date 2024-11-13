import pandas as pd
import argparse
import numpy as np

def _classify_mri_file(row):

    # Get the filename
    mri = row['mri']

    target_prop_equal = row["target_prop_equal"]
    if np.isnan(target_prop_equal):
        target_prop_equal = row["prec_prop_equal"]
    target_prop_increase = row['target_prop_increase']
    if np.isnan(target_prop_increase):
        target_prop_increase = row["prec_prop_increase"]
    target_prop_decrease = row['target_prop_decrease']
    if np.isnan(target_prop_decrease):
        target_prop_decrease = row["target_prop_decrease"]

    # Calculating top 1 delta percent
    try:
        top_1_precursor_delta_count = float(row["top_k_prec_mz_diff_counts"].split(";")[0])
        precursor_total = sum([int(x) for x in row["top_k_prec_mz_diff_counts"].split(";")]) 
        top_1_precursor_delta_percent = top_1_precursor_delta_count / precursor_total
    except:
        top_1_precursor_delta_percent = 0
    
    unique_precursor_count = row['Num_Unique_Precursor_MZ']

    if row['MS2_count'] == 0:
        return 'NO_MS2'
    elif row['MS2_count'] < 50:
        return 'inconclusive (limited MS2)'
    elif (target_prop_equal > 0.995) and (row['MS2_Isolation_Width'] > 10):
        return 'DIA-MSE'
    elif (target_prop_equal > 0.995) and (row['MS2_Isolation_Width'] < 10):
        return 'TARGETED'
    elif (target_prop_equal > 0.995) and (np.isnan(row['MS2_Isolation_Width'])):
        return 'DIA OR TARGETED'
    elif (target_prop_equal < 0.80) and (target_prop_increase < 0.8) and (target_prop_decrease < 0.8):
        return 'DDA'
    elif (target_prop_increase > 0.9) and (top_1_precursor_delta_percent > 0.9):
        return 'DIA-SWATH'
    elif (target_prop_increase > 0.9) and (unique_precursor_count < 100):
        return 'DIA-SWATH'
    elif (target_prop_increase > 0.9) and (unique_precursor_count > 1000) and (top_1_precursor_delta_percent < 0.3):
        return 'DDA'
    elif (row['prec_prop_increase'] > 0.9):
        return 'Inconclusive (Can be DDA or DIA-SWATH)'
    else:
        return 'Unclassified'
    



def classify_mri_files(df):
    """
    Classify the MRI files in the input dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        The input dataframe with the columns:
        - filename: str

    Returns
    -------
    """

    # Classify the files
    df['classification'] = df.apply(_classify_mri_file, axis=1)

    return df

def main():
    parser = argparse.ArgumentParser(description='Classify MRI LCMS Files')
    parser.add_argument('input_csv', type=str, help='Input file')
    parser.add_argument('output_csv', type=str, help='Output file')
    args = parser.parse_args()

    # Load the input file really fast with pyarrow
    df = pd.read_csv(args.input_csv, engine='pyarrow')
    #df = pd.read_csv(args.input_csv)

    # Classify the files
    print(len(df))
    print(df.columns)

    df = classify_mri_files(df)

    print(df.head())

    # Save the output
    df.to_csv(args.output_csv, index=False, sep=",")


if __name__ == '__main__':
    main()
