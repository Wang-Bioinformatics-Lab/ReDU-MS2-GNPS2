# main.py
from app import app
from models import *
import views
import views_selection
import dash_selection

if __name__ == '__main__':
    Filename.create_table(True)
    app.run(host='0.0.0.0', port=5000)
