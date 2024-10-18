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
import utils

@app.route('/', methods=['GET'])
def renderhomepage():
    # forward to /selection

    return redirect("/selection")

@app.route('/metadataselection', methods=['GET'])
def metadataselection():
    return render_template('metadataselection.html')

@app.route('/heartbeat', methods=['GET'])
def testapi():
    
    return_obj = {}
    return_obj["status"] = "success"
    return json.dumps(return_obj)

@app.route('/status.json', methods=['GET'])
def status():
    # Checking when this file was last modified
    last_modified = os.path.getmtime(config.PATH_TO_ORIGINAL_MAPPING_FILE)

    # Making this PST time and human readable
    last_modified = str(pd.to_datetime(last_modified, unit='s').tz_localize('UTC').tz_convert('US/Pacific'))

    # Trying to get the text for the nextflow log file
    try:
        with open("./workflows/PublicDataset_ReDU_Metadata_Workflow/.nextflow.log", 'r') as file:
            nextflow_log_data = file.read()
    except:
        nextflow_log_data = "No log file found"

    log_modified = os.path.getmtime("./workflows/PublicDataset_ReDU_Metadata_Workflow/.nextflow.log")
    log_modified = str(pd.to_datetime(log_modified, unit='s').tz_localize('UTC').tz_convert('US/Pacific'))

    # Trying to read the stdout
    try:
        with open("./workflows/PublicDataset_ReDU_Metadata_Workflow/nextflowstdout.log", 'r') as file:
            nextflow_stdout_data = file.read()
    except:
        nextflow_stdout_data = "No log file found"

    stdout_modified = os.path.getmtime("./workflows/PublicDataset_ReDU_Metadata_Workflow/nextflowstdout.log")
    stdout_modified = str(pd.to_datetime(stdout_modified, unit='s').tz_localize('UTC').tz_convert('US/Pacific'))

    return_obj = {}
    return_obj["lastupdate"] = last_modified
    return_obj["nextflow"] = {
        "log": nextflow_log_data,
        "log_lastupdate" : log_modified,
        "stdout" : nextflow_stdout_data,
        "stdout_lastupdate" : stdout_modified
    }

    return json.dumps(return_obj)

@app.route('/status.trace', methods=['GET'])
def status_trace():
    return send_file("./workflows/PublicDataset_ReDU_Metadata_Workflow/trace.txt", cache_timeout=1)

@app.route('/status.timeline', methods=['GET'])
def status_timeline():
    return send_file("./workflows/PublicDataset_ReDU_Metadata_Workflow/timeline.html", cache_timeout=1)


# manually trigger the task
@app.route('/update', methods=['GET'])
def update():
    # run the task
    tasks.tasks_generate_metadata.apply_async()
    
    return "Queued"


@app.route('/dump', methods=['GET'])
def dump():
    return send_file(config.PATH_TO_ORIGINAL_MAPPING_FILE, \
                     max_age=1, as_attachment=True, \
                     download_name="all_sampleinformation.tsv")


