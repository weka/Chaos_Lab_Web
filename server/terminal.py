import os
import glob
import threading
from flask import request
from flask_socketio import SocketIO, emit
import paramiko

# For demonstration, we create our own SocketIO instance.
# In production, you should import your main app's SocketIO instance.
socketio = SocketIO(message_queue='redis://')  # Adjust if you're not using Redis.

# Global dictionary to map client session IDs to SSH channels.
terminal_channels = {}

def start_ssh_terminal(sid, socketio):
    try:
        # Log the start of the connection attempt.
        print(f"[terminal.py] Starting SSH terminal for SID: {sid}")
        
        # Get the scenario folder from the environment.
        scenario_folder = os.environ.get("SCENARIO_FOLDER")
        print(f"[terminal.py] SCENARIO_FOLDER: {scenario_folder}")
        if not scenario_folder:
            raise Exception("SCENARIO_FOLDER environment variable not set.")

        # Read the backend IP from scenario_chaos_ip.txt.
        host_file = os.path.join(scenario_folder, "scenario_chaos_ip.txt")
        print(f"[terminal.py] Looking for host file at: {host_file}")
        if not os.path.exists(host_file):
            raise Exception(f"Host file not found at {host_file}")
        with open(host_file, "r") as f:
            host = f.read().strip()
        print(f"[terminal.py] Host resolved to: {host}")

        # Find a PEM file in the folder.
        pem_files = glob.glob(os.path.join(scenario_folder, "*.pem"))
        print(f"[terminal.py] Found PEM files: {pem_files}")
        if not pem_files:
            raise Exception("No .pem file found in the scenario folder.")
        pem_file = pem_files[0]
        print(f"[terminal.py] Using PEM file: {pem_file}")

        username = "ec2-user"  # Hard-coded username.
        
        # Initialize the SSH client.
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        print("[terminal.py] Connecting via SSH...")
        client.connect(hostname=host, username=username, key_filename=pem_file)
        print("[terminal.py] SSH connection established, invoking shell...")
        channel = client.invoke_shell()

        # Send a newline to trigger the prompt.
        channel.send("\r\n")
        socketio.emit('output', "\r\nConnected! You can try commands like 'ls -la'\r\n", room=sid, namespace='/terminal')
        terminal_channels[sid] = channel

        # Function to continuously read from the SSH channel.
        def read_from_channel():
            while True:
                try:
                    if channel.recv_ready():
                        data = channel.recv(1024)
                        if not data:
                            break
                        socketio.emit('output', data.decode('utf-8'), room=sid, namespace='/terminal')
                except Exception as read_error:
                    socketio.emit('output', f"\r\nError reading data: {str(read_error)}\r\n", room=sid, namespace='/terminal')
                    break
        thread = threading.Thread(target=read_from_channel)
        thread.daemon = True
        thread.start()
        print(f"[terminal.py] SSH terminal thread started for SID: {sid}")

    except Exception as e:
        error_message = f"SSH error: {str(e)}"
        print(f"[terminal.py] {error_message}")
        socketio.emit('output', error_message, room=sid, namespace='/terminal')

@socketio.on('connect', namespace='/terminal')
def terminal_connect():
    sid = request.sid
    print(f"[terminal.py] Client connected: {sid}")
    threading.Thread(target=start_ssh_terminal, args=(sid, socketio)).start()

@socketio.on('input', namespace='/terminal')
def handle_input(data):
    sid = request.sid
    channel = terminal_channels.get(sid)
    if channel:
        try:
            channel.send(data)
        except Exception as e:
            error_msg = f"Error sending data: {str(e)}"
            print(f"[terminal.py] {error_msg}")
            socketio.emit('output', error_msg, room=sid, namespace='/terminal')
    else:
        socketio.emit('output', "No active SSH channel found.", room=sid, namespace='/terminal')

@socketio.on('disconnect', namespace='/terminal')
def terminal_disconnect():
    sid = request.sid
    if sid in terminal_channels:
        del terminal_channels[sid]
    print(f"[terminal.py] Terminal client disconnected: {sid}")

