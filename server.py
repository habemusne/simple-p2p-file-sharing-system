import json
import heapq
from collections import defaultdict
from traceback import print_exc
from socket import socket
from threading import Thread

from node import Node


class Server(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.files = {}
        """
        self.files = {
            'f1.txt': {
                'bytes': 444,
                'md5': '03c7c0ace395d80182db07ae2c30f034',
                'chunks': [{
                    'peers': { '168.0.0.1:4444': True },
                    'md5': '4b43b0aee35624cd95b910189b3dc231',
                    'id': 0,
                }, {
                    'peers': { '168.0.0.1:4444': True, '153.43.44.2:5311': True },
                    'md5': 'e22428ccf96cda9674a939c209ad1000',
                    'id': 1,
                }]
            }
        }
        """

    def handler_register_file(self, args):
        """
        args = {
            'address': '168.0.0.3:4444',
            'files': [{
                'filename': 'f1.txt',
                'bytes': 444,
                'md5_full': 'e22428ccf96cda9674a939c209ad1000'
                'md5_chunks': ['03c7c0ace395d80182db07ae2c30f034', '4b43b0aee35624cd95b910189b3dc231']
            }]
        }

        returns: [{
            'f1.txt': True,
            'f2.txt': True,
            'f3.txt': False,
        }]
        """
        address = args['address']
        result = []
        for entry in args['files']:
            if entry['filename'] in self.files:
                # for chunk in self.files[entry['filename']]['chunks']:
                #     chunk['peers'][address] = True
                result.append({ entry['filename']: False })
            else:
                self.files[entry['filename']] = {
                    'bytes': entry['bytes'],
                    'md5': entry['md5_full'],
                    'chunks': [{
                        'peers': { address: True },
                        'md5': md5_chunk,
                        'id': i,
                    } for i, md5_chunk in enumerate(entry['md5_chunks'])],
                }
                result.append({ entry['filename']: True })
        return result

    def handler_file_list(self, args):
        """
        args = {
            'address': '168.0.0.3:4444'
        }

        returns: {
            'count': 2,
            'result': ['f1.txt', 'f2.txt']
        }
        """
        return {
            'count': len(self.files),
            'result': [{
                'filename': filename,
                'bytes': self.files[filename]['bytes'],
            } for filename in self.files],
        }

    def handler_file_locations(self, args):
        """
        args = {
            'address': '168.0.0.3:4444',
            'filename': 'f1.txt',
            'include_md5': True
        }

        returns: {
            'bytes': 444,
            'md5': '03c7c0ace395d80182db07ae2c30f034',
            'count': 1,
            'addresses': [{
                'host': '127.0.0.3',
                'port': 4321,
                'chunks': [{
                    'id': 0,
                    'md5': '4b43b0aee35624cd95b910189b3dc231',
                }]
            }, {
                'host': '154.0.0.3',
                'port': 3333,
                'chunks': [{
                    'id': 1,
                    'md5': 'e22428ccf96cda9674a939c209ad1000',
                }]
            }]
        }
        """

        filename = args['filename']
        address_to_chunks = defaultdict(list)
        if filename not in self.files:
            return { 'count': 0, 'addresses': [] }
        for chunk in self.files[filename]['chunks']:
            for address in chunk['peers']:
                if args.get('include_md5'):
                    address_to_chunks[address].append({
                        'id': chunk['id'],
                        'md5': chunk['md5'],
                    })
                else:
                    address_to_chunks[address].append(chunk['id'])
        return {
            'bytes': self.files[filename]['bytes'],
            'md5': self.files[filename]['md5'],
            'count': len(address_to_chunks),
            'addresses': [{
                'host': key.split(':')[0],
                'port': key.split(':')[1],
                'chunks': address_to_chunks[key],
            } for key in address_to_chunks],
        }

    def handler_register_chunk(self, args):
        """
        args = {
            'address': '168.0.0.3:4444',
            'filename': 'f1.txt',
            'chunkid': 0,
            'md5': 'e22428ccf96cda9674a939c209ad1000'
        }

        returns {
            'result': True
        }
        """
        address = args['address']
        filename = args['filename']
        chunkid = args['chunkid']
        md5 = args['md5']
        # if the server does not have this file, or the passed-in chunkid is invalid, or the passed-in md5 does not match the record, then return False. Otherwise, register.
        if filename not in self.files or\
                chunkid < 0 or\
                chunkid >= len(self.files[filename]['chunks']) or\
                self.files[filename]['chunks'][chunkid]['md5'] != md5:
            return { 'result': False }
        self.files[filename]['chunks'][chunkid]['peers'][address] = True
        return { 'result': True }

    def handler_leave(self, args):
        """
        args = {
            'address': '168.0.0.3:4444'
        }
        """
        address = args['address']
        filenames_to_be_deleted = []
        for filename in self.files:
            for chunk in self.files[filename]['chunks']:
                if address in chunk['peers']:
                    if len(chunk['peers']) == 0:
                        filenames_to_be_deleted.append(filename)
                    chunk['peers'].pop(address)
        for filename in filenames_to_be_deleted:
            self.files.pop(filename)
        return { 'result': True }

    def run(self):
        t = Thread(target=self.listen)
        t.start()
        t.join()


if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('-H', '--host', required=True)
    parser.add_argument('-p', '--port', required=True)
    parser.add_argument('-dpr', '--dynamic_port_range', required=True)
    args = parser.parse_args()
    server = Server(host=args.host, port=args.port, dynamic_port_range=args.dynamic_port_range)
    server.run()
