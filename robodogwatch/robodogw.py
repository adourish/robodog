import logging
from flask import Flask, jsonify, make_response
from flask_cors import CORS, cross_origin
from flask import Flask, request
from flask_restful import Resource, Api
import argparse
import os
import yaml
from urllib.parse import unquote
import fnmatch

# pip install Flask flask_cors Flask-RESTful argparse pyyaml urllib

parser = argparse.ArgumentParser()
parser.add_argument('-s', '--server', default='localhost')
parser.add_argument('-p', '--port', type=int, default=2500)
parser.add_argument('-f', '--file', default='k2.txt')
parser.add_argument('-g', '--group', default='g1')
args = parser.parse_args()

try:
    with open('robodogw.yaml', 'r') as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    print("Config file not found. Please make sure the 'robodogw.yaml' file exists.")
    exit()



app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": ["localhost", "file:///", "your_client_origin"]}}, send_wildcard=True)

logging.basicConfig(level=logging.INFO)
logging.info('start')

def update_listof_files():
    # Create list of files based on command line arguments
    listof_files = []
    if args.group:
        for group in config['groups']:
            if group['name'] == args.group:
                logging.info(f"update_listof_files group key found{group['name']}")
                for file in group['files']:
                    # Adding the logic to allow or deny file based on the lists
                    file_path = os.path.join(os.getcwd(), file)
                    # Convert file_path and patterns to lowercase for case-insensitive comparison
                    file_path_lower = file_path.lower()
                    # Check if file_path matches any pattern in the allow list and does not match any pattern in the deny list
                    if any(fnmatch.fnmatch(file_path_lower, pattern.lower()) for pattern in config['allow']) and not any(fnmatch.fnmatch(file_path_lower, pattern.lower()) for pattern in config['deny']):
                        listof_files.append(file)
                        logging.info(f"update_listof_files group not found:{file} path file_path:{file_path}")
                    else:
                        print(f"update_listof_files File {file} is not allowed or is denied. Please check the file path and try again.")
                        logging.info(f"found but not allowed not allowed file:{file}  file_path:{file_path}")
            else:
                logging.debug(f"update_listof_files group not found:{args.group}  file_path:{file_path}")
    return listof_files

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
            response = make_response({'error': str(e)})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 500

class GetMessage(Resource):
    @cross_origin(origins=["localhost", "file:///"], allow_headers=['Content-Type','Authorization'])
    def get(self):
        try:
            
            result = ""
            listof_files = update_listof_files()
            for file_name in listof_files:
                if os.path.exists(file_name):
                    with open(file_name, 'r', encoding='utf-8') as file:
                        file_content = file.read()

                    result += f"group:{args.group}\n{file_name}:\n{file_content}\n"
                else:
                    logging.error(f'GetMessage File {file_name} does not exist')

            response = make_response(jsonify({'message': result}))
            response.headers.add("Access-Control-Allow-Origin", "*")
            logging.debug('GetMessage message: %s', str(response))
            return response
        except Exception as e:
            logging.error('GetMessage Failed to get message: %s', str(e))
            response = make_response({'error': str(e)})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 500

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
                logging.error('GetGroups no group')
                response = make_response({'error': 'No groups found in config'})
                response.headers.add("Access-Control-Allow-Origin", "*")
                return response, 404
        except KeyError as ke:
            logging.error('GetGroups KeyError: %s', str(ke))
            response = make_response({'error': 'KeyError occurred'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 500
        except Exception as e:
            logging.error('Failed to get groups: %s', str(e))
            response = make_response({'error': str(e)})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 500

class SetActiveGroup(Resource):
    @cross_origin(origins=["localhost", "file:///"], allow_headers=['Content-Type', 'Authorization'])
    def get(self, group):
        logging.info('SetActiveGroup group: %s', str(group))
        try:
            group = unquote(group)
            args.group = group
            if group in [group['name'] for group in config['groups']]:
                logging.debug('SetActiveGroup success' + group)
                args.group = group
                response = make_response({'group': group, 'message':'success'}, 200)
                response.headers.add("Access-Control-Allow-Origin", "*")
                return response
            else:
                response = make_response({'file': group, 'message':'nogroup'})
                logging.debug('SetActiveGroup no group' + group)
                response.headers.add("Access-Control-Allow-Origin", "*")
                return response, 404
        except Exception as e:
            logging.error({'group': group, 'message':'error', 'error': str(e)})
            response = make_response({'file': group, 'message':'error', 'error': str(e)})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 500

class SetActiveFile(Resource):
    @cross_origin(origins=["localhost", "file:///"], allow_headers=['Content-Type', 'Authorization'])
    def get(self, file):
        try:
            file = unquote(file)
            if os.path.isfile(file):
                args.file = file
                response = make_response({'file': file, 'message':'success'}, 200)
                logging.debug('SetActiveFile success ' + file)
                response.headers.add("Access-Control-Allow-Origin", "*")
                return response
            else:
                response = make_response({'file': file, 'message':'nofile'})
                logging.debug('SetActiveFile no file' + file)
                response.headers.add("Access-Control-Allow-Origin", "*")
                return response, 404
        except Exception as e:
            logging.error({'file': file, 'message':'error', 'error': str(e)})
            response = make_response({'file': file, 'message':'error', 'error': str(e)})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 500
        
api = Api(app)
api.add_resource(SendMessage, '/api/sendMessage')
api.add_resource(GetMessage, '/api/getMessage')
api.add_resource(GetGroups, '/api/getGroups')
api.add_resource(SetActiveGroup, '/api/activateGroup/<string:group>')
api.add_resource(SetActiveFile, '/api/activateFile/<string:file>')

if __name__ == '__main__':
    app.run(host=args.server, port=args.port)