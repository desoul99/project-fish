from modules.browser import Browser
import yaml
import pika

# Load config
with open('config/config.yaml', 'r') as f_obj:
    config = yaml.load(f_obj, Loader=yaml.SafeLoader)


def consume():
    credentials = pika.PlainCredentials(username=config['rabbitmq']['username'], password=config['rabbitmq']['password'])
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost', credentials=credentials))
    channel = connection.channel()
    channel.queue_declare(queue='pf_urlqueue')
    

    def callback(ch, method, properties, body):
        browser = Browser(config)
        url = body.decode()
        browser.load(url)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='pf_urlqueue', on_message_callback=callback)

    print("Waiting for messages. To exit press CTRL+C")
    channel.start_consuming()

if __name__ == '__main__':
    consume()
