import pandas as pd
# pip install pandas
class Model:
    def init(self, title, group, knowledge):
        self.title = title
        self.group = group
        self.knowledge = knowledge

def readexcel(filepath):
    try:
        df = pd.read_excel(filepath)
        models = []
        for _, row in df.iterrows():
            title = row.get('title')
            group = row.get('group')
            knowledge = row.get('knowledge')
            if title and group and knowledge:
                model = Model(title, group, knowledge)
                models.append(model)
            else:
                print("Missing data in row:", row)
        return models
    except FileNotFoundError:
        print("File not found.")
    except Exception as e:
        print("Error:", e)

def main(filename):
    models = readexcel(filename)
    for model in models:
        print(model.title, model.group, model.knowledge)

if name == "main":
    import sys
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        print("Please provide the Excel file name as a parameter.")