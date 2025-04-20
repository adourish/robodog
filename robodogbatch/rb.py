from os import name
import pandas as pd
import openpyxl
import openai
import logging
import os

logging.basicConfig(filename='output.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class Model:
    def __init__(self, title, group, knowledge, question, outputfile, m):
        self.title = title
        self.group = group
        self.question = question
        self.m = m
        self.knowledge = knowledge
        self.outputfile = outputfile
        self.output = ""

def writeoutput(model, outputdir='dataout'):
    try:

        with open(model.outputfile, 'w', encoding='utf-8') as f:
            f.write(model.output)
        logging.debug(f"Output written to {model.output}")
    except Exception as e:
        logging.error(f"Error writing output for {model.title}: {e}")

def processmodelswith_openai(models, token):
    openai.api_key = token
    for model in models:
        try:
            model.output = read_output(model.outputfile) or ""
            logging.info(f"{model.title}: {model.outputfile}")
            client = openai.OpenAI(
                api_key=token,
            )
            response = client.chat.completions.create(
                model=model.m,
                messages=[
                    {"role": "user", "content": "knowledge:" + model.knowledge},
                    {"role": "user", "content": "output:" + model.output},
                    {"role": "user", "content": "question:" + model.question},
                    {"role": "user", "content": "instructions:" + "Analyze the provided 'output:' and 'knowledge:' to understand and answer the user's 'Question:' Do not provide answers based solely on the chat history or context."},
 
                ]
            )
            model.output = response.choices[0].message.content.strip()
            logging.info(f"{model.title}: {model.outputfile}")
            writeoutput(model)
        except Exception as e:
            logging.error(f"OpenAI API error for {model.title}: {e}")

def read_output(outputfile):
    if os.path.exists(outputfile):
        with open(outputfile, 'r', encoding='utf-8') as f:
            return f.read()
    return None

def readexcel(filepath, group_filter):
    try:
        logging.debug("Reading file " + filepath + " with group " + group_filter)
        df = pd.read_excel(filepath)
        models = []
        for _, row in df.iterrows():
            title = row.get('title')
            group = row.get('group')
            question = row.get('question')
            m = row.get('model')
            knowledge = row.get('knowledge')
            outputfile = row.get('outputfile')
            if title and group and knowledge and pd.notna(group) and group == group_filter:
                model = Model(title, group, knowledge, question, outputfile, m)
                models.append(model)
                logging.debug(f"Model: {m} Title: {title}, Group: {group}, Question: {question}, Output: {outputfile}")
            else:
                logging.debug("Missing or unmatched data in row: " + str(row))
        return models
    except FileNotFoundError:
        logging.error("File not found: " + filepath)
        return []
    except Exception as e:
        logging.error("Error: " + str(e))
        return []

def main(filename, group, token):
    logging.info(f"Processing file: {filename} for group: {group}")
    models = readexcel(filename, group)
    processmodelswith_openai(models, token)
    for model in models:
        print(model.title, model.group, model.knowledge, model.output)

import sys
print("start")
logging.info("Batch processing started")
if len(sys.argv) > 3:
    filename = sys.argv[1]
    group = sys.argv[2]
    token = sys.argv[3]
    main(filename, group, token)
else:
    print("Provide Excel file, group, and token.")