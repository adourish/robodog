import logging
from flask import Flask, jsonify, make_response
from flask_cors import CORS, cross_origin
from flask import Flask, request
from flask_restful import Resource, Api
import argparse
import os
import yaml
# pip install Flask flask_cors Flask-RESTful argparse pyyaml
parser = argparse.ArgumentParser()
parser.add_argument('-s', '--server', default='localhost')
parser.add_argument('-p', '--port', type=int, default=2500)
parser.add_argument('-f', '--file', default='k2.txt')
parser.add_argument('-g', '--group', default=None)
args = parser.parse_args()

try:
    with open('robodogw.yaml', 'r') as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    print("Config file not found. Please make sure the 'robodogw.yaml' file exists.")
    exit()

# Create list of files based on command line arguments
listof_files = []
if args.group:
    for group in config['groups']:
        if group['name'] == args.group:
            listof_files.extend(group['files'])

if args.file:
    if os.path.isfile(args.file):
        listof_files.append(args.file)
    else:
        print(f"File {args.file} does not exist. Please check the file name and try again.")
        exit()

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": ["localhost", "file:///", "your_client_origin"]}}, send_wildcard=True)

logging.basicConfig(level=logging.DEBUG)
logging.info('start')

@app.after_request
def after_request(response):
    logging.debug('Response header: %s', str(response.headers))
    for name, value in response.headers:
        if name.lower() == 'access-control-allow-origin':
            logging.debug(f"CORS header {name} is set to {value}")
        elif name.lower().startswith('access-control-allow-'):
            logging.warning(f"CORS header {name} is set to {value}, which may indicate a potential CORS error")
    return response

class SendMessage(Resource):
    @cross_origin(origins=["localhost", "file:///"], allow_headers=['Content-Type','Authorization'])
    def post(self):
        try:
            message = request.get_json()
            if not message:
                return {'error': 'Message cannot be empty'}, 400
            with open(args.file, 'a') as file:
                file.write(str(message) + '\n')
            
            response = make_response({'message': 'Message written to file successfully'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 200
        except Exception as e:
            logging.error('Failed to post message: %s', str(e))
            return {'error': str(e)}, 500



class GetGroups(Resource):
    @cross_origin(origins=["localhost", "file:///"], allow_headers=['Content-Type','Authorization'])
    def get(self):
        try:
            if 'groups' in config:
                groups = [group['name'] for group in config['groups']]
                response = make_response(jsonify({'groups': groups}))
                response.headers.add("Access-Control-Allow-Origin", "*")
                return response, 200
            else:
                return {'error': 'No groups found in config'}, 404
        except KeyError as ke:
            logging.error('KeyError: %s', str(ke))
            return {'error': 'KeyError occurred'}, 500
        except Exception as e:
            logging.error('Failed to get groups: %s', str(e))
            return {'error': str(e)}, 500
        
class GetMessage(Resource):
    @cross_origin(origins=["localhost", "file:///"], allow_headers=['Content-Type','Authorization'])
    def get(self):
        try:
            result = ""
            for file_name in listof_files:
                if os.path.exists(file_name):
                    with open(file_name, 'r', encoding='utf-8') as file:
                        file_content = file.read()

                    result += f"group:{args.group}\n{file_name}:\n{file_content}\n"
                else:
                    logging.error(f'File {file_name} does not exist')

            response = make_response(jsonify({'message': result}))
            response.headers.add("Access-Control-Allow-Origin", "*")
            logging.debug('Response message: %s', str(response))
            return response
        except Exception as e:
            logging.error('Failed to get message: %s', str(e))
            return {'error': str(e)}, 500

class SetActiveGroup(Resource):
    @cross_origin(origins=["localhost", "file:///"], allow_headers=['Content-Type', 'Authorization'])
    def post(self):
        try:
            data = request.get_json()
            if 'group' in data:
                args.group = data['group']
                response = make_response({'message': f'Active group set to {args.group}'}, 200)
                response.headers.add("Access-Control-Allow-Origin", "*")
                return response
            else:
                return {'error': 'Group data not provided in request'}, 400
        except Exception as e:
            logging.error('Failed to set active group: %s', str(e))
            return {'error': str(e)}, 500

class SetActiveFile(Resource):
    @cross_origin(origins=["localhost", "file:///"], allow_headers=['Content-Type', 'Authorization'])
    def post(self):
        try:
            data = request.get_json()
            if 'file' in data:
                if os.path.isfile(data['file']):
                    args.file = data['file']
                    response = make_response({'message': f'Active file set to {args.file}'}, 200)
                    response.headers.add("Access-Control-Allow-Origin", "*")
                    return response
                else:
                    return {'error': 'File does not exist'}, 404
            else:
                return {'error': 'File data not provided in request'}, 400
        except Exception as e:
            logging.error('Failed to set active file: %s', str(e))
            return {'error': str(e)}, 500

api = Api(app)
api.add_resource(SendMessage, '/api/sendMessage')
api.add_resource(GetMessage, '/api/getMessage')
api.add_resource(GetGroups, '/api/getGroups')
api.add_resource(SetActiveGroup, '/api/activateGroup')
api.add_resource(SetActiveFile, '/api/activateFile')

if __name__ == '__main__':
    app.run(host=args.server, port=args.port)