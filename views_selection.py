from app import app
import json
import pandas as pd
from flask import request

import config
from ontology_utils import resolve_ontology

black_list_attribute = ["SubjectIdentifierAsRecorded", "UniqueSubjectID", "UBERONOntologyIndex", "DOIDOntologyIndex", "ComorbidityListDOIDIndex"]

##############################
# Metadata Selector API Calls
##############################
@app.route('/attributes', methods=['GET'])
def viewattributes():
    # Reading the dump instead of the database
    metadata_df = pd.read_csv(config.PATH_TO_ORIGINAL_MAPPING_FILE, sep="\t", dtype=str)

    all_attributes_list = list(metadata_df.columns)

    output_list = []
    for attribute in all_attributes_list:
        output_dict = {}
        output_dict["attributename"] = attribute
        output_dict["attributedisplay"] = attribute.replace("ATTRIBUTE_", "").replace("Analysis_", "").replace("Subject_", "").replace("Curated_", "")

        all_terms = set(metadata_df[attribute])
        output_dict["countterms"] = len(all_terms)

        if attribute == "filename":
            continue

        if attribute in black_list_attribute:
            continue
        else:
            output_list.append(output_dict)

    output_list = sorted(output_list, key=lambda x: x["attributedisplay"], reverse=False)

    return json.dumps(output_list)
