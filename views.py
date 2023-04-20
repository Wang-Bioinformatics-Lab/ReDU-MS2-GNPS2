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
import config

import tasks

@app.route('/', methods=['GET'])
def renderhomepage():
    metadata_df = pd.read_csv(config.PATH_TO_ORIGINAL_MAPPING_FILE, sep="\t", dtype=str)
    total_files = len(metadata_df["filename"].unique())
    
    return render_template('homepage.html', total_files=total_files, total_identifications=0, total_compounds=0)

@app.route('/metadataselection', methods=['GET'])
def metadataselection():
    return render_template('metadataselection.html')

@app.route('/heartbeat', methods=['GET'])
def testapi():
    return_obj = {}
    return_obj["status"] = "success"
    return json.dumps(return_obj)


# manually trigger the task
@app.route('/update', methods=['GET'])
def update():
    # run the task
    tasks.tasks_generate_metadata.apply_async()
    
    return "Queued"