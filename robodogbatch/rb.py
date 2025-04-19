from os import name
import pandas as pd
import openpyxl
import openai
import logging

logging.basicConfig(filename='output.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class Model:
    def __init__(self, title, group, knowledge, question, output, m):
        self.title = title
        self.group = group
        self.question = question
        self.m = m
        self.knowledge = knowledge
        self.output = output

def processmodelswith_openai(models, token):
    openai.api_key = token
    for model in models:
        try:
            logging.info(f"{model.title}: {model.output}")
            client = openai.OpenAI(
                api_key=token,
            )
            response = client.chat.completions.create(
                model=model.m,
                messages=[
                    {"role": "user", "content": model.knowledge},
                    {"role": "user", "content": model.question}
                ]
            )
            model.output = response.choices[0].message.content.strip()
            logging.info(f"{model.title}: {model.output}")
        except Exception as e:
            logging.error(f"OpenAI API error for {model.title}: {e}")

def readexcel(filepath, group_filter):
    try:
        logging.info("Reading file " + filepath + " with group " + group_filter)
        df = pd.read_excel(filepath)
        models = []
        for _, row in df.iterrows():
            title = row.get('title')
            group = row.get('group')
            question = row.get('question')
            m = row.get('model')
            knowledge = row.get('knowledge')
            output = row.get('output')
            if title and group and knowledge and pd.notna(group) and group == group_filter:
                model = Model(title, group, knowledge, question, output, m)
                models.append(model)
                logging.info(f"Model: {m} Title: {title}, Group: {group}, Knowledge: {knowledge}, Question: {question}, Output: {output}")
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