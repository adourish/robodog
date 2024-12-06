import logging
from flask import Flask, jsonify, make_response
from flask_cors import CORS, cross_origin
from flask import Flask, request
from flask_restful import Resource, Api
import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument('-s', '--server', default='localhost')
parser.add_argument('-p', '--port', type=int, default=2500)
parser.add_argument('-f', '--file', default='k.txt')
args = parser.parse_args()

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": ["localhost", "file:///", "your_client_origin"]}}, send_wildcard=True)

logging.basicConfig(level=logging.DEBUG)
logging.info('start')

@app.after_request
def after_request(response):

    logging.info('Response header: %s', str(response.headers))
    for name, value in response.headers:
        if name.lower() == 'access-control-allow-origin':
            logging.info(f"CORS header {name} is set to {value}")
        elif name.lower().startswith('access-control-allow-'):
            logging.warning(f"CORS header {name} is set to {value}, which may indicate a potential CORS error")
    return response

class SendMessage(Resource):

    def post(self):
        try:
            message = request.get_json()
            if not message:
                return {'error': 'Message cannot be empty'}, 400
            with open(args.file, 'a') as file:
                file.write(str(message) + '\n')
            return {'message': 'Message written to file successfully'}, 200
        except Exception as e:
            logging.error('Failed to post message: %s', str(e))
            return {'error': str(e)}, 500

class GetMessage(Resource):
    @cross_origin(origins=["localhost", "file:///"], allow_headers=['Content-Type','Authorization'])
    def get(self):
        try:
            if not os.path.exists(args.file):
                logging.error('File does not exist')
                return {'error': 'File does not exist'}, 404

            file_size = os.stat(args.file).st_size
            logging.info('File size: %s bytes name: %s ', file_size, args.file)

            with open(args.file, 'r', encoding='utf-8') as file:
                data = file.readlines()
                
            response = make_response(jsonify({'message': data}))
            response.headers.add("Access-Control-Allow-Origin", "*")
            logging.info('Response message: %s', str(response))
            return response
        except Exception as e:
            logging.error('Failed to get message: %s', str(e))
            return {'error': str(e)}, 500

api = Api(app)
api.add_resource(SendMessage, '/api/sendMessage')
api.add_resource(GetMessage, '/api/getMessage')

if __name__ == '__main__':
    app.run(host=args.server, port=args.port)