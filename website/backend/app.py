# backend/app.py

from flask import Flask, render_template, request, jsonify
from itertools import combinations
import pika
import pymongo
import yaml

app = Flask(__name__, template_folder='../frontend/templates', static_folder='../frontend/static')

# Load config
with open('config/config.yaml', 'r') as f_obj:
    config = yaml.load(f_obj, Loader=yaml.SafeLoader)

# Connect to RabbitMQ
credentials = pika.PlainCredentials(username=config['rabbitmq']['username'], password=config['rabbitmq']['password'])
connection = pika.BlockingConnection(pika.ConnectionParameters('localhost', credentials=credentials))
channel = connection.channel()
channel.queue_declare(queue='pf_urlqueue')

# Connect to MongoDB
client = pymongo.MongoClient(f'mongodb://{config["mongodb"]["username"]}:{config["mongodb"]["password"]}@{config["mongodb"]["host"]}:{config["mongodb"]["port"]}/', uuidRepresentation='standard')  
db = client[config["mongodb"]["database"]]   
collection = db[config["mongodb"]["collection"]]

def calculate_links(data):
    links = []
    for pair in combinations(data.keys(), 2):
        common_elements = set(data[pair[0]]) & set(data[pair[1]])
        if common_elements:
            links.append({"source": pair[0], "target": pair[1], "value": len(common_elements)})
    return links

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit')
def submit():
    return render_template('submit.html')

@app.route('/view')
def view():
    return render_template('view.html')

@app.route('/submitUrl', methods=['POST'])
def submit_url():
    url = request.form['url']
    
    # Publish data to RabbitMQ
    channel.basic_publish(exchange='', routing_key='pf_urlqueue', body=url)
    
    return jsonify({'message': 'Data submitted successfully'})

@app.route('/get_data')
def get_data():
    data = dict()
    documents = [x for x in collection.find({}, {"_id":0, "hashes": 1, "requests": {"$slice": 1}})]
    for document in documents:
        data[document['requests'][0]['request']['document_url']] = document['hashes']
    links = calculate_links(data)
    return jsonify({"nodes": list(data.keys()), "links": links})

if __name__ == '__main__':
    app.run(debug=True)

