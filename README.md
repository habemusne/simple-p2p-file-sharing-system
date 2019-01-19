# Project Overview

Project Type: Course Project

Course Name: Computer Networking

School: Penn State University

Level: Graduate

Project Requirement: Design and implement a centralized P2P file sharing system using TCP/IP. A peer needs to at least be able to register a file and download a file. File needs to be divided into chunks. Features including multiple connection, parallel downloading, and chunk management are required.

# Sample Output

[Sample Output](https://s3.amazonaws.com/habemusne-public/cse514-project1/sample_output.txt)

# My Grade

10/10

# Usage

`python3 server.py -h`

`python3 peer.py -h`

# Example Usage

4 Modes are available.

## 1. Interactive Mode

Spin up the server: `python3 server.py -H 127.0.0.1 -p 3030 -dpr 49201-49300`

Spin up a peer: `python3 peer.py -H 127.0.0.1 -sH 127.0.0.1 -dpr 49301-49400 -t 4 -c command_files/1.json -n peer2 -p 3029 -sp 3030`

## 2. Automatic Mode

Spin up the server: `python3 server.py -H 127.0.0.1 -p 3030 -dpr 49201-49300`

Spin up a peer: `python3 peer.py -H 127.0.0.1 -sH 127.0.0.1 -dpr 49201-49400 -t 4 -a -c command_files/single_node/1.json -n peer1 -p 3029 -sp 3030`

Spin up another peer: `python3 peer.py -H 127.0.0.1 -sH 127.0.0.1 -dpr 49301-49400 -t 4 -n peer2 -p 3029 -sp 3030`. In this terminal you can issue commands manually.

## 3. Semi-automatic Mode

Spin up the server: `python3 server.py -H 127.0.0.1 -p 3030 -dpr 49201-49300`

Spin up the peer: `python3 peer.py -H 127.0.0.1 -sH 127.0.0.1 -dpr 49201-49400 -t 1 -a -c command_files/single_node/1.json -n peer1 -p 3000 -sp 3030 -sa`

## 4. Integration Mode

Open a terminal then `python3 integration.py -c command_files/multiple_nodes/2.json`

You can use either `1.json` or `2.json`. The latter pretty much covers all use cases except for the rarest-first mechanism.

# In-depth Explanation

[Protocol Specification](https://s3.amazonaws.com/habemusne-public/cse514-project1/protocol.pdf)

[Project Structure](https://s3.amazonaws.com/habemusne-public/cse514-project1/structure.pdf)

[Description of Features](https://s3.amazonaws.com/habemusne-public/cse514-project1/description.pdf)
