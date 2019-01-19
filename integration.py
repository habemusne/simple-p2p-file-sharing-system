import json
from threading import Thread
from argparse import ArgumentParser
from server import Server
from peer import Peer


parser = ArgumentParser()
parser.add_argument('-c', '--command_file', help='command file for multiple nodes')
args = parser.parse_args()

with open(args.command_file, 'r') as f:
    config = json.loads(f.read())

server = Server(
    host=config['server']['parameters']['host'],
    port=config['server']['parameters']['port'],
    dynamic_port_range= config['server']['parameters']['dynamic_port_range']
)
thread_server = Thread(target=server.run)

thread_peers = []
for peer_config in config['peers']:
    parameters = peer_config['parameters']
    commands = peer_config['commands']
    peer = Peer(
        host=parameters['host'],
        port=parameters['port'],
        server_host=config['server']['parameters']['host'],
        server_port=config['server']['parameters']['port'],
        dynamic_port_range=parameters['dynamic_port_range'],
        num_download_threads=parameters['num_download_threads'],
        name=parameters['name'],
    )
    thread_peers.append(Thread(target=peer.run, kwargs={
        'auto_mode': True,
        'command_json': commands,
    }))

thread_server.start()
for t in thread_peers:
    t.start()

