import os
import sys
import json
import hashlib
from collections import defaultdict
from queue import PriorityQueue, Empty
from os.path import join, exists
from traceback import print_exc
from socket import socket
from threading import Thread, Event
from time import sleep
from tempfile import mkdtemp

import protocol
from protocol import DownloadFail
from node import Node
from workers import QueueWorker, Watcher

LOCAL_TMP_DIR_TOP_LEVEL = 'chunks'
MESSAGE_SUCCESS = """

************************************************
****************DOWNLOAD SUCCESS****************
************************************************

CHUNK INFORMATION
{chunk_information}
{cdots}

FILE PATH
{filepath}
************************************************

"""


class Peer(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        #TODO Need to record the server host and port
        self.__server_host = kwargs['server_host']
        self.__server_port = int(kwargs['server_port'])
        self.__num_download_threads = int(kwargs['num_download_threads'])

        if self.name:
            self.tmp_dir = join(LOCAL_TMP_DIR_TOP_LEVEL, self.name)
        else:
            self.tmp_dir = mkdtemp(dir=LOCAL_TMP_DIR_TOP_LEVEL)

    def _preprocess_message_reg_file(self, message):
        """
        Before the peer registers a file, it needs to break the file into chunks and also compute the md5 of each chunk, as well as the whole file. It needs to send all of these md5 to the server. This function modifies the mssage IN PLACE

        @param message: type dict
        @return None
        """

        # Go through all files, remove those that don't exist
        to_be_deleted = []
        for filepath in message['args']['files']:
            if not exists(filepath):
                self._logger.warning('File does not exist: {}'.format(filepath))
                to_be_deleted.append(filepath)
        for filepath in to_be_deleted:
            message['args']['files'].remove(filepath)

        # Compute size and md5 information
        for i, filepath in enumerate(message['args']['files']):
            filename = filepath.split('/')[-1]
            md5_full = self.__get_md5_from_file(filepath)
            md5_chunks = self.__get_chunks_md5_from_file(filepath)
            file_data = {
                'filename': filename,
                'bytes': os.stat(filepath).st_size,
                'md5_full': md5_full,
                'md5_chunks': md5_chunks,
            }
            message['args']['files'][i] = file_data

            file_data['filepath'] = filepath
            self.__split_file_into_chunks(filepath)
        message['args']['count'] = len(message['args']['files'])

    def __request_server(self, action, args):
        """
        This function serves to request a server
        """
        message = {
            'action': action,
            'args': args,
        }
        preprocess_function_name = '_preprocess_message_' + action
        if hasattr(self, preprocess_function_name):
            getattr(self, preprocess_function_name)(message)
        return self.request(self.__server_host, self.__server_port, message)

    def __request_peers(self, action, args):
        """
        This function serves to request a peer. Curently it only handles 'download' action.
        """
        if action == 'download':
            """
            In download, procedures are divided into 3 groups: preprocessing, processing, postprocessing.
            """

            """
            Preprocessing:

            1. request file information from the server. 
            2. precompute essential mappings for optimization of computation
            3. initialize a priority queue based on the chunks. Each item is a chunk info.
            """
            response = self.__request_server('loc', {
                'filename': args['filename'],
                'include_md5': True,
            })
            response = json.loads(response.decode('utf-8'))
            if len(response['addresses']) == 0:
                self._logger.info('Fail. Reason: file does not exist in network or no available peers have the file')
                return
            file_bytes = response['bytes']
            file_md5 = response['md5']
            addresses = response['addresses']

            chunkid_to_addresses = defaultdict(dict)
            chunkid_to_md5 = dict()
            for entry in addresses:
                address = ':'.join([entry['host'], str(entry['port'])])
                for chunk in entry['chunks']:
                    chunkid_to_addresses[chunk['id']][address] = True
                    chunkid_to_md5[chunk['id']] = chunk['md5']
            sorted_chunkids = sorted([key for key in chunkid_to_addresses])

            task_queue = self.__make_download_task_queue(args['filename'], args['scheme'], chunkid_to_addresses, chunkid_to_md5)
            
            """
            Processing:

            1. Initialize a watcher. All download threads will notify the watcher if they encounter a critical issue during downloading. The watcher will then notify all other threads to stop
            2. Initialize all download threads
            3. Start all threads
            4. Wait until all tasks in the queue are consumed
            5. Stop all threads
            """
            fail = False
            def handle_fail():
                """
                This function clears the queue upon download failure
                """
                fail = True
                while not task_queue.empty():
                    try:
                        task_queue.get(False)
                    except Empty:
                        continue
                    task_queue.task_done()

            def watcher_routine(caller):
                num_total = len(sorted_chunkids)
                num_complete = len(caller.data)
                percentage = num_complete / num_total
                total_marks = 50
                num_marks = int(percentage * total_marks)
                sys.stdout.write('\r{}{}> {}%'.format(self.name, '='*(num_marks),round(percentage, 4) * 100))
                sys.stdout.flush()

            watcher = Watcher(self._logger, handle_fail, routine_function=watcher_routine)
            watcher.start()
            workers = []
            for i in range(self.__num_download_threads):
                worker = QueueWorker(
                    self.__task_handler_download_chunk,
                    self._logger,
                    task_queue,
                    watcher,
                    name=str(i),
                )
                workers.append(worker)
                worker.start()
            task_queue.join()
            for worker in workers:
                worker.shutdown_flag.set()
            for worker in workers:
                worker.join()
            watcher.shutdown_flag.set()
            watcher.join()

            """
            Postprocessing:

            1. If download fail, notify failure.
            2. If md5 calculated by adding all chunks together does not match the md5 returned from the server, notify failure.
            3. Combine chunks to file.
            4. If file size does not match, remove the downloaded file and notify failure.
            5. Otherwise, notify success and output the result
            """
            if fail:
                self._logger.info('Fail. Reason: download fail.')
            elif self.__check_md5_equal(args['filename'], sorted_chunkids, file_md5):
                self._logger.info('Fail. Reason: MD5 not match')
            else:
                self.__combine_chunks_to_file(args['destination'], args['filename'], sorted_chunkids)
                if not self.__check_bytes_equal(args['destination'], file_bytes):
                    self._logger.info('Fail. Reason: size not match.')
                    os.system('rm {}'.format(args['destination']))
                else:
                    chunk_information = '\n'.join([
                        'Chunk{chunkid}: downloaded from {download_from_address}. Available from: {available_addresses}'.format(
                            chunkid=entry['chunkid'],
                            download_from_address=entry['download_from_address'],
                            available_addresses=entry['available_addresses'],
                        )
                        for entry in watcher.data[:20]
                    ])
                    self._logger.info(MESSAGE_SUCCESS.format(
                        filepath=args['destination'],
                        chunk_information=chunk_information,
                        cdots='......' if len(watcher.data) > 20 else '',
                    ))

    def __task_handler_download_chunk(self, task_queue, task):
        """
        This is the function for all download thread to run.
        """
        addresses = [key for key in task[2]['addresses']]
        address = addresses[0]
        peer_host, peer_port = address.split(':')
        message = {
            'action': 'download',
            'args': {
                'filename': task[2]['filename'],
                'chunkid': task[2]['chunkid'],
            },
        }
        response = self.request(peer_host, peer_port, message)
        chunk_md5 = self.__get_md5_from_data(response)

        # If md5 does not match, then we call this chunk download a failure
        if chunk_md5 != task[2]['md5']:
            self._logger.warning('MD5 not match: file {filename} of chunk {chunkid} from address {address}'.format(
                filename=task[2]['filename'],
                chunkid=task[2]['chunkid'],
                address=address,
            ))

            # This chunk from this address should be blacklisted. We don't want to download it again.
            if len(addresses) == 1:
                # this is the last address on this chunk that can be attempted... We call the whole file download a failure
                self._logger.warning('No more peers available on chunk {}. Download fail.'.format(task[2]['chunkid']))
                task_queue.task_done()
                raise DownloadFail

            # If there are still other addresses available, push a new task in for this chunk
            task[2]['addresses'].pop(address)
            if task[2]['scheme'] == 'rarest_first':
                task[0] -= 1
            # else:
            #     task[2]['num_retries_left'] -= 1
            #     if task[2]['num_retries_left'] <= -1:
            #         self._logger.warning('Retry limit exceeded on chunk {}. Download fail.'.format(task[2]['chunkid']))
            #         task_queue.task_done()
            #         raise DownloadFail
            task_queue.put(task)
            task_queue.task_done()

        # If md5 does match, then we call it a success. We write the chunk to local and register the chunk on the network.
        else:
            with open(self.__get_chunk_path(task[2]['filename'], task[2]['chunkid']), 'wb') as f:
                f.write(response)
            response = self.__request_server('reg_chunk', {
                'filename': task[2]['filename'],
                'chunkid': task[2]['chunkid'],
                'md5': task[2]['md5'],
            })
            if json.loads(response.decode('utf-8'))['result'] == False:
                self._logger.error('Fail to register chunk {} to the network'.format(task[2]['chunkid']))
            task_queue.task_done()
            return {
                'chunkid': task[2]['chunkid'],
                'download_from_address': address,
                'available_addresses': addresses,
            }

    def __make_download_task_queue(self, filename, scheme, chunkid_to_addresses, chunkid_to_md5):
        """
        This function makes a task queue, which is a priority queue. Two schemes are supported: 'rarest_first' and 'normal'

        rarest_first: number of addresses available for the chunk is used as the key

        normal: chunkid is used as the key. They are basically incremental
        """

        task_queue = PriorityQueue()
        if scheme == 'rarest_first':
            counter = 0
            for key, value in chunkid_to_addresses.items():
                task_queue.put((len(value), counter, {
                    'addresses': value,
                    'filename': filename,
                    'chunkid': key,
                    'md5': chunkid_to_md5[key],
                    'scheme': scheme,
                }))
                counter += 1
        else:
            for i, chunkid in enumerate(sorted([key for key in chunkid_to_md5])):
                task_queue.put((i, 0, {
                    'addresses': chunkid_to_addresses[chunkid],
                    'filename': filename,
                    'chunkid': chunkid,
                    'md5': chunkid_to_md5[chunkid],
                    'scheme': scheme,
                    'num_retries_left': protocol.CHUNK_RETRY_LIMIT,
                }))
        return task_queue

    def handler_download(self, args):
        """
        This function is triggered when the a node received a download request from another node

        args = {
            'address': '168.0.0.3:4444',
            'filename': 'f1.txt',
            'chunkid': 0
        }
        """
        chunk_path = self.__get_chunk_path(args['filename'], args['chunkid'])
        if not exists(chunk_path):
            return b''
        with open(chunk_path, 'rb') as f:
            return f.read()

    def __combine_chunks_to_file(self, destination, filename, chunkids):
        with open(destination, 'wb') as f:
            for chunkid in chunkids:
                with open(self.__get_chunk_path(filename, chunkid), 'rb') as g:
                    f.write(g.read())

    def __check_md5_equal(self, filename, chunkids, target_md5):
        md5_full = hashlib.md5()
        for chunkid in chunkids:
            with open(self.__get_chunk_path(filename, chunkid), 'rb') as f:
                md5_full.update(f.read())
        return md5_full == target_md5

    def __check_bytes_equal(self, filepath, target_bytes):
        return os.stat(filepath).st_size == target_bytes

    def __get_md5_from_data(self, data):
        return hashlib.md5(data).hexdigest()

    def __get_md5_from_file(self, filepath):
        md5_full = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(protocol.BYTES_PER_CHUNK), b''):
                md5_full.update(chunk)
        return md5_full.hexdigest()

    def __get_chunks_md5_from_file(self, filepath):
        md5_chunks = []
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(protocol.BYTES_PER_CHUNK), b''):
                md5_chunks.append(self.__get_md5_from_data(chunk))
        return md5_chunks

    def __get_chunk_path(self, filename, chunkid):
        parent = join(self.tmp_dir, filename)
        if not exists(parent):
            os.system('mkdir -p {}'.format(parent))
        return join(parent, str(chunkid) + '.chunk')

    def __split_file_into_chunks(self, filepath):
        filename = filepath.split('/')[-1]
        with open(filepath, 'rb') as f:
            for chunkid, chunk in enumerate(iter(lambda: f.read(protocol.BYTES_PER_CHUNK), b'')):
                local_chunk_path = self.__get_chunk_path(filename, chunkid)
                with open(local_chunk_path, 'wb') as g:
                    g.write(chunk)

    def command_generator(self, **kwargs):
        if not kwargs.get('auto_mode'):
            sleep(0.5)
            self._logger.info(self.info_usage())
            while True:
                yield input('Please enter command: ')
        else:
            if kwargs.get('command_file'):
                with open(kwargs.get('command_file'), 'r') as f:
                    commands = json.loads(f.read())
            else:
                commands = kwargs.get('command_json')
            for entry in commands:
                if not kwargs.get('semi_auto_mode'):
                    sleep(entry['wait_seconds'])
                self._logger.info('Request sent: {}'.format(entry['command']))
                yield entry['command']
                if kwargs.get('semi_auto_mode'):
                    input('Please hit ENTER to continue: ')

    def run(self, **kwargs):
        t = Thread(target=self.listen)
        t.start()
        commands = self.command_generator(**kwargs)
        while True:
            try:
                command = commands.__next__()
                if not command:
                    continue
                action = command.split(' ')[0]
                args = json.loads(command[len(action) + 1:])
                if protocol.COMMANDS[action]['request_to'] == 'server':
                    request_funcion = self.__request_server
                else:
                    request_funcion = self.__request_peers
                response = request_funcion(action, args)
                self._logger.info('Response received: {}'.format(response))
            except KeyboardInterrupt:
                break
            except StopIteration:
                break
            except Exception as e:
                print_exc()
                break


if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('-H', '--host', required=True)
    parser.add_argument('-p', '--port', required=True)
    parser.add_argument('-sH', '--server_host', required=True)
    parser.add_argument('-sp', '--server_port', required=True)
    parser.add_argument('-dpr', '--dynamic_port_range', required=True)
    parser.add_argument('-t', '--num_download_threads', required=True)
    parser.add_argument('-n', '--name', help='name of this peer. it will be used as the tmp dir name')

    parser.add_argument('-a', '--auto_mode', action='store_true', help='if this is specified, the program does not for user input; it will use the configured command file to run')
    parser.add_argument('-c', '--command_file', help='(only available at auto mode) the command file to use')
    parser.add_argument('-j', '--command_json', help='(only available at auto mode; only available at integration) the json containing all commands')
    parser.add_argument('-sa', '--semi_auto_mode', action='store_true', help='(only available at auto mode) if this is specified, the program uses the configured command file to run. But at each command, it pauses until the user tells it to continue.')
    args = parser.parse_args()
    peer = Peer(
        host=args.host,
        port=args.port,
        server_host=args.server_host,
        server_port=args.server_port,
        dynamic_port_range=args.dynamic_port_range,
        num_download_threads=args.num_download_threads,
        name=args.name,
    )
    peer.run(
        auto_mode=args.auto_mode,
        command_file=args.command_file,
        command_json=args.command_json,
        semi_auto_mode=args.semi_auto_mode,
    )
