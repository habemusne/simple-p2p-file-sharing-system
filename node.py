import heapq
import json
import os
import logging
from traceback import print_exc
from socket import socket
from threading import Thread

import protocol


class Node:
    _logger = None

    def __init__(self, **kwargs):
        self.host = kwargs['host']
        self.port = int(kwargs['port'])
        self.name = kwargs.get('name', self.__get_class_name())
        dynamic_port_range = kwargs.get('dynamic_port_range', '49152-65535')
        self.available_ports = list(range(*[int(port) for port in dynamic_port_range.split('-')]))
        heapq.heapify(self.available_ports)

        logging.basicConfig(level=logging.INFO)
        self._logger = logging.getLogger(self.name)

    @classmethod
    def __get_class_name(cls):
        return cls.__name__

    def __recvall(self, sock):
        data = b''
        while True:
            part = sock.recv(protocol.BUFF_SIZE)
            data += part
            if len(part) < protocol.BUFF_SIZE:
                break
        return data

    def __preprocess_message(self, message):
        message['args']['address'] = ':'.join([self.host, str(self.port)])
        if protocol.COMMANDS[message['action']]['type_request'] == 'json':
            message = json.dumps(message)
        return message

    def __on_new_client(self, sock, address):
        # ASSUMPTION: number of ports is good enough
        port = heapq.heappop(self.available_ports)
        try:
            message = self.__recvall(sock)
            length, body = self.parse_message(message)
            if len(body) != length:
                raise Exception('Corrupted body')
            body = json.loads(body)
            action = body['action']
            args = body['args']
            self._logger.debug('Request received: {}'.format(action))

            # If this action is not valid, or not supported from this node type (Peer or Server), then send back 404
            if action not in protocol.COMMANDS or self.__get_class_name().lower() not in protocol.COMMANDS[action]['request_to'].split(','):
                self._logger.warning('No handler available for this action')
                sock.sendall(json.dumps({ 'status': 404 }).encode('utf-8'))
            else:
                handler = getattr(self, protocol.COMMANDS[action]['handler'])
                response = handler(args)
                if protocol.COMMANDS[action]['type_response'] == 'json':
                    response = self.encode_byte_json(response)
                sock.sendall(response)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print_exc()
        sock.close()
        heapq.heappush(self.available_ports, port)

    @classmethod
    def info_usage(cls):
        text = 'Available commands:\n\n{command_list}'
        node_type = cls.__get_class_name().lower()

        command_list = '\n'.join([
            '{index}. {command} {args}: {help}'.format(
                index=i,
                command=command,
                args=','.join(['{arg}'.format(arg=arg)
                    for arg in protocol.COMMANDS[command]['args'].split('|')]),
                help=protocol.COMMANDS[command]['help'],
            )
            for i, command in enumerate(protocol.COMMANDS)
            if node_type in protocol.COMMANDS[command]['available_node_types'].split(',')
        ])

        return text.format(command_list=command_list)

    @staticmethod
    def encode_byte_json(data):
        return json.dumps(data).encode('utf-8')

    def handler_inspect(self, variable):
        self._logger.info(getattr(self, variable))

    def parse_message(self, message):
        """
        Parse a message and returns the action (str) and args (byte json str). Example:

        input: 'reg_file {"files": ["/Users/a67/Desktop/test.sql"]}'
        output: 'reg_file', '{"files": ["/Users/a67/Desktop/test.sql"]}'
        """
        if not message:
            return -1, ''
        length = ''
        body = ''
        message = message.decode('utf-8')
        for i in range(0, len(message)):
            if message[i].isdigit():
                length += message[i]
            elif message[i] == ' ':
                body = message[i+1:]
                break
            else:
                raise Exception('ERROR: Incorrect separator between length and body')
        return int(length), body

    def request(self, host, port, message):
        message = self.__preprocess_message(message)
        with socket() as sock:
            sock.connect((host, int(port)))
            sock.sendall('{message_length} {message}'.format(
                message_length=len(message),
                message=message,
            ).encode('utf-8'))
            response = self.__recvall(sock)
        return response

    def listen(self):
        sock = socket()
        sock.bind((self.host, self.port))
        sock.listen()
        self._logger.info('Waiting for new connections...')
        while True:
            try:
                conn, address = sock.accept()
                t = Thread(target=self.__on_new_client, args=(conn, address))
                t.start()
            except KeyboardInterrupt:
                break
            except Exception as e:
                print_exc()
                break
        sock.close()
