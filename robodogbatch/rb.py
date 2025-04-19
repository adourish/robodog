from os import name
import pandas as pd
import openpyxl
import logging

# pip install openpyxl logging pandas
logging.basicConfig(filename='output.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class Model:
    def init(self, title, group, knowledge):
        self.title = title
        self.group = group
        self.knowledge = knowledge

def readexcel(filepath, group_filter):
    try:
        logging.info("Reading file " + filepath + " with group " + group_filter)
        df = pd.read_excel(filepath)
        models = []
        for _, row in df.iterrows():
            title = row.get('title')
            group = row.get('group')
            knowledge = row.get('knowledge')
            if title and group and knowledge and group == group_filter:
                model = Model(title, group, knowledge)
                models.append(model)
                logging.info("Title: " + title + ", Group: " + group + ", Knowledge: " + knowledge)
            else:
                logging.warning("Missing or unmatched data in row: " + str(row))
        return models
    except FileNotFoundError:
        logging.error("File not found: " + filepath)
        return []
    except Exception as e:
        logging.error("Error: " + str(e))
        return []

def main(filename, group):
    logging.info(f"Processing file: {filename} for group: {group}")
    models = readexcel(filename, group)
    for model in models:
        print(model.title, model.group, model.knowledge)

import sys
print("start")
logging.info("Batch processing started")
if len(sys.argv) > 2:
    filename = sys.argv[1]
    group = sys.argv[2]
    print(filename, group)
    main(filename, group)
else:
    print("Please provide the Excel file name and group as parameters.")