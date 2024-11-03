**⚠️ Warning**  
The refactored worker code is available in the `worker-refactor` branch.

# Project Fish

Project Fish is a web analysis tool designed to track and correlate resources accessed by malicious websites such as phishing or fake shops websites. Inspired by services like urlquery and urlscan, Project Fish aims to provide a simple solution for easily identifying clusters of websites.


## Overview

The project is divided into three main components:

1. **Browser worker**: Responsible for accessing websites, extracting information about browser requests and responses, and storing them in a MongoDB database. It utilizes the 'nodriver' library for efficient web scraping.

2. **Proxy**: Utilizes 'mitmproxy' to capture all responses from websites and hash every resource encountered. This information is then added to the response headers so that the Browser worker can add it to the MongoDB database along with the rest of the data.

3. **Website**: A frontend interface that allows users to submit URLs to the worker through a RabbitMQ queue and visualize the information stored in the database using a force-directed graph. This makes it easy to identify correlations between websites based on shared resources.

The diagram below illustrates the components of the project and their relationships. It provides a visual representation of how the Worker, Proxy, RabbitMQ, MongoDB, and Website interact within the system.
![image](https://github.com/desoul99/project-fish/assets/72390215/54a3de99-a5da-423f-bafc-906e4296d7cc)


## Usage

To use Project Fish, follow these steps:

1. Clone the repository to your local machine.
2. Install the necessary dependencies for the worker and website components.
3. Set up a MongoDB database and a RabbitMQ instance (You can use the docker-compose.yaml file to quickly setup containers for these services).
4. Download mitmproxy and start mitmdump specifying the 'mitm_script.py' file as an addon. You can use the following snippet: ```mitmdump -s mitm_script.py --listen-port 8082 --set validate-inbound-headers=false --set  ssl_insecure=true```
6. Run the worker and website components to start analyzing websites and capturing responses.
7. Access the website frontend to submit URLs and visualize the data using the provided graph visualization tool.

You can also use the 'producer.py' script to send URLs to the Browser worker.

![image](https://github.com/desoul99/project-fish/assets/72390215/3f04adf3-9d32-4c16-ac62-0b5f6bc708ed)


## Example

As an example, we analyzed 500 malicious URLs obtained from 'https://openphish.com/feed.txt'. The resulting graph displayed visual clusters of websites sharing similar phishing kits. For instance, the cluster highlighted in yellow (left) revealed multiple URLs with identical phishing kit characteristics (right).

![image](https://github.com/desoul99/project-fish/assets/72390215/9040c925-ae22-4d5a-86c9-40f3321ff342)


## Disclaimer

Project Fish is a proof-of-concept project developed over a weekend and is not intended for production use. As such, it will not be maintained or updated. However, feel free to explore the codebase and adapt it for your own purposes.
