# views.py
from flask import abort, jsonify, render_template, request, redirect, url_for, send_file, make_response

from app import app
from models import *

import os
import csv
import json
import uuid
import requests
import pandas as pd

# Local imports
import config
import tasks

@app.route('/', methods=['GET'])
def renderhomepage():
    metadata_df = pd.read_csv(config.PATH_TO_ORIGINAL_MAPPING_FILE, sep="\t", dtype=str)
    total_files = len(metadata_df["filename"].unique())

    # Checking when this file was last modified
    last_modified = os.path.getmtime(config.PATH_TO_ORIGINAL_MAPPING_FILE)

    # Making this PST time and human readable
    last_modified = pd.to_datetime(last_modified, unit='s').tz_localize('UTC').tz_convert('US/Pacific')
    
    return render_template('homepage.html', total_files=total_files, total_identifications=0, total_compounds=0, last_modified=last_modified)

@app.route('/metadataselection', methods=['GET'])
def metadataselection():
    return render_template('metadataselection.html')

@app.route('/heartbeat', methods=['GET'])
def testapi():
    # Checking when this file was last modified
    last_modified = os.path.getmtime(config.PATH_TO_ORIGINAL_MAPPING_FILE)

    # Making this PST time and human readable
    last_modified = pd.to_datetime(last_modified, unit='s').tz_localize('UTC').tz_convert('US/Pacific')

    return_obj = {}
    return_obj["status"] = "success"
    return_obj["lastupdate"] = last_modified
    return json.dumps(return_obj)


# manually trigger the task
@app.route('/update', methods=['GET'])
def update():
    # run the task
    tasks.tasks_generate_metadata.apply_async()
    
    return "Queued"


@app.route('/dump', methods=['GET'])
def dump():
    return send_file(config.PATH_TO_ORIGINAL_MAPPING_FILE, cache_timeout=1, as_attachment=True, attachment_filename="all_sampleinformation.tsv")


