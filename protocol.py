BYTES_PER_CHUNK = 1024
BUFF_SIZE = 4096
CHUNK_RETRY_LIMIT = 5

COMMANDS = {
    'reg_file': {
        'available_node_types': 'peer',
        'args': '{"files": [filepath1, filepath2]}',
        'help': 'register files by file paths',
        'request_to': 'server',
        'handler': 'handler_register_file',
        'type_request': 'json',
        'type_response': 'json'
    },
    'list': {
        'available_node_types': 'peer',
        'args': '{}',
        'help': 'list files available',
        'request_to': 'server',
        'handler': 'handler_file_list',
        'type_request': 'json',
        'type_response': 'json'
    },
    'loc': {
        'available_node_types': 'peer',
        'args': '{"filename": filename, "include_md5": false}',
        'help': 'get ip of peers that contain the requested file name. The "include_md5" argument is optional',
        'request_to': 'server',
        'handler': 'handler_file_locations',
        'type_request': 'json',
        'type_response': 'json'
    },
    'reg_chunk': {
        'available_node_types': 'peer',
        'args': '{"filename": filename, "chunkid": chunkid}, "md5": chunk_md5',
        'help': 'register a chunk of a file',
        'request_to': 'server',
        'handler': 'handler_register_chunk',
        'type_request': 'json',
        'type_response': 'json'
    },
    'leave': {
        'available_node_types': 'peer',
        'args': '{}',
        'help': 'remove this peer from network',
        'request_to': 'server',
        'handler': 'handler_leave',
        'type_request': 'json',
        'type_response': 'json'
    },
    'download': {
        'available_node_types': 'peer',
        'args': '{"filename": filename, "destination": destination, "scheme": scheme}',
        'help': 'download file by filename. scheme can be either "normal" or "rarest_first"',
        'request_to': 'peer',
        'handler': 'handler_download',
        'type_request': 'json',
        'type_response': 'byte'
    },
    'inspect': {
        'available_node_types': 'server,peer',
        'args': '{"variable": variable}',
        'help': 'inspect a variable in this node',
        'handler': 'handler_inspect',
        'type_request': 'json',
        'type_response': 'json'
    }
}


class DownloadFail(Exception):
    pass
