# views.py
from flask import abort, jsonify, render_template, request, redirect, url_for, send_file, make_response

from app import app
from models import *

import os
import csv
import json
import uuid
import requests

@app.route('/', methods=['GET'])
def renderhomepage():
    return render_template('homepage.html')

@app.route('/heartbeat', methods=['GET'])
def testapi():
    return_obj = {}
    return_obj["status"] = "success"
    return json.dumps(return_obj)
