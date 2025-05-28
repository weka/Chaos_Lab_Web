import os
import select
import time
import paramiko
import io
import subprocess
import shutil
from flask import request, current_app, Flask
from flask_socketio import emit, join_room, leave_room, disconnect, Namespace
from app import socketio 
from .scenarios import SCENARIO_SESSIONS
import boto3

PTY_PROCESSES = {}

def ssh_output_reader(app_for_context, scenario_id, channel):
    with app_for_context.app_context():
        current_app.logger.info(f"[SSH Reader {scenario_id}]: Starting PTY output reader for channel {channel}.")
        try:
            while channel and channel.active:
                socketio.sleep(0.01) 
                read_ready, _, _ = select.select([channel], [], [], 0.05) 
                if read_ready:
                    if channel.recv_ready():
                        output = channel.recv(4096).decode(errors='replace')
                        if output:
                            socketio.emit('pty-output', {'output': output}, room=scenario_id, namespace='/terminal_ws')
                        else:
                            current_app.logger.info(f"[SSH Reader {scenario_id}]: Channel recv_ready but got empty output, may be closing.")
                            if channel.exit_status_ready(): break
                    if channel.recv_stderr_ready():
                        stderr_output = channel.recv_stderr(4096).decode(errors='replace')
                        if stderr_output:
                            socketio.emit('pty-output', {'output': stderr_output}, room=scenario_id, namespace='/terminal_ws')
                if channel.exit_status_ready():
                    current_app.logger.info(f"[SSH Reader {scenario_id}]: Channel exit status ready. Exiting reader.")
                    break
        except paramiko.SSHException as e:
            current_app.logger.error(f"[SSH Reader {scenario_id}]: SSHException in reader: {e}", exc_info=False)
            socketio.emit('pty-output', {'output': f"\r\n[SSH Connection Error in reader: {e}]\r\n"}, room=scenario_id, namespace='/terminal_ws')
        except Exception as e:
            current_app.logger.error(f"[SSH Reader {scenario_id}]: Unhandled exception in reader: {e}", exc_info=True)
            socketio.emit('pty-output', {'output': f"\r\n[Error reading from remote: {e}]\r\n"}, room=scenario_id, namespace='/terminal_ws')
        finally:
            current_app.logger.info(f"[SSH Reader {scenario_id}]: PTY output reader stopped for channel {channel}.")
            if scenario_id in PTY_PROCESSES and PTY_PROCESSES[scenario_id].get("ssh_channel") == channel :
                 socketio.emit('pty-output', {'output': '\r\n[Terminal session may have ended or encountered an issue.]\r\n$ '}, room=scenario_id, namespace='/terminal_ws')
            if scenario_id in PTY_PROCESSES and PTY_PROCESSES[scenario_id].get("ssh_channel") == channel:
                PTY_PROCESSES[scenario_id]["ssh_channel"] = None


def cleanup_scenario_session(app_for_context, scenario_id):
    with app_for_context.app_context():
        current_app.logger.info(f"Starting cleanup for scenario session: {scenario_id}")
        session_pty_data = PTY_PROCESSES.pop(scenario_id, None)
        scenario_meta_data = SCENARIO_SESSIONS.pop(scenario_id, None)

        if session_pty_data:
            channel = session_pty_data.get("ssh_channel")
            if channel:
                try: 
                    current_app.logger.info(f"Closing SSH channel for {scenario_id}")
                    channel.close()
                except Exception as e: current_app.logger.error(f"Error closing SSH channel for {scenario_id}: {e}")
            
            ssh_client = session_pty_data.get("ssh_client")
            if ssh_client:
                try: 
                    current_app.logger.info(f"Closing SSH client for {scenario_id}")
                    ssh_client.close()
                except Exception as e: current_app.logger.error(f"Error closing SSH client for {scenario_id}: {e}")
            
            reader_greenlet = session_pty_data.get("reader_greenlet")
            if reader_greenlet and hasattr(reader_greenlet, 'kill'):
                 try:
                     current_app.logger.info(f"Attempting to kill reader greenlet for {scenario_id}")
                     reader_greenlet.kill()
                 except Exception as e:
                     current_app.logger.error(f"Error killing reader greenlet for {scenario_id}: {e}")

        if scenario_meta_data:
            tf_dir = scenario_meta_data.get("terraform_dir")
            terraform_name_prefix_var = scenario_meta_data.get("terraform_name_prefix_for_run", scenario_id) 

            if tf_dir and os.path.exists(tf_dir):
                current_app.logger.info(f"Running terraform destroy for {scenario_id} (using name_prefix: {terraform_name_prefix_var}) in {tf_dir}")
                try:
                    destroy_cmd = ['terraform', 'destroy', '--auto-approve', '-no-color']
                    destroy_result = subprocess.run(destroy_cmd, cwd=tf_dir, capture_output=True, text=True, timeout=600)
                    if destroy_result.returncode == 0:
                        current_app.logger.info(f"Terraform destroy successful for {scenario_id}:\n{destroy_result.stdout}")
                    else:
                        current_app.logger.error(f"Terraform destroy FAILED for {scenario_id}. Stderr:\n{destroy_result.stderr}\nStdout:\n{destroy_result.stdout}")
                    
                    aws_key_name = scenario_meta_data.get("key_name_aws")
                    if aws_key_name:
                        current_app.logger.info(f"Attempting to delete AWS key pair: {aws_key_name}")
                        try:
                            ec2_client = boto3.client('ec2')
                            ec2_client.delete_key_pair(KeyName=aws_key_name)
                            current_app.logger.info(f"Successfully deleted AWS key pair: {aws_key_name}")
                        except Exception as key_del_e:
                            current_app.logger.error(f"Failed to delete AWS key pair {aws_key_name}: {key_del_e}")

                    current_app.logger.info(f"Attempting to remove directory: {tf_dir}")
                    shutil.rmtree(tf_dir, ignore_errors=True)
                    current_app.logger.info(f"Cleaned up directory {tf_dir}")

                except subprocess.TimeoutExpired:
                    current_app.logger.error(f"Terraform destroy timed out for {scenario_id}")
                except Exception as e:
                    current_app.logger.error(f"Error during terraform destroy or directory cleanup for {scenario_id}: {e}", exc_info=True)
            else:
                current_app.logger.warning(f"Terraform directory not found for cleanup: {tf_dir}")
        else:
            current_app.logger.warning(f"No scenario metadata found for cleanup of {scenario_id}")
        current_app.logger.info(f"Full cleanup process finished for scenario session {scenario_id}")


class TerminalNamespace(Namespace):
    def on_connect(self):
        client_sid = request.sid
        current_app.logger.info(f"Client SID {client_sid} connected to {self.namespace} namespace.")
        emit('pty-output', {"output": f"Socket.IO Connected (SID: {client_sid}). Send 'join_scenario' with your scenario's sessionId.\r\n"})

    def on_join_scenario(self, data):
        client_sid = request.sid
        scenario_session_id = data.get('sessionId')

        if not scenario_session_id or scenario_session_id not in SCENARIO_SESSIONS:
            current_app.logger.error(f"Client {client_sid} attempted to join invalid/unknown scenario session: {scenario_session_id}")
            emit('pty-output', {"output": f"\r\nError: Invalid or unknown scenario session ID: {scenario_session_id}\r\n"})
            disconnect() 
            return

        join_room(scenario_session_id, sid=client_sid)
        current_app.logger.info(f"Client SID {client_sid} joined scenario room: {scenario_session_id}")

        if scenario_session_id not in PTY_PROCESSES:
            PTY_PROCESSES[scenario_session_id] = {"clients": set(), "ssh_client": None, "ssh_channel": None, "reader_greenlet": None}
        
        PTY_PROCESSES[scenario_session_id]["clients"].add(client_sid)
        
        session_pty_data = PTY_PROCESSES[scenario_session_id]
        if session_pty_data.get("ssh_channel") and session_pty_data["ssh_channel"].active:
            current_app.logger.info(f"Client {client_sid} rejoining active SSH session for {scenario_session_id}")
            emit('pty-output', {"output": f"\r\nRejoined active session for '{SCENARIO_SESSIONS[scenario_session_id]['repo']}'.\r\n"})
            try:
                session_pty_data["ssh_channel"].send("\n") 
            except Exception as e:
                current_app.logger.warning(f"Could not send newline to re-joined channel for {scenario_session_id}: {e}")
            return

        emit('pty-output', {"output": f"\r\nJoining scenario '{SCENARIO_SESSIONS[scenario_session_id]['repo']}'. Establishing SSH connection...\r\n"})
        
        scenario_data = SCENARIO_SESSIONS[scenario_session_id]
        instance_ip = scenario_data.get("instance_ip")
        private_key_pem_str = scenario_data.get("private_key_pem_content")

        if not instance_ip or not private_key_pem_str:
            msg = "\r\nError: Instance IP or private key not found for this session.\r\n"
            current_app.logger.error(f"Config error for session {scenario_session_id}: Missing IP or PEM content.")
            emit('pty-output', {"output": msg})
            disconnect()
            return

        try:
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            private_key_file = io.StringIO(private_key_pem_str)
            pkey = paramiko.Ed25519Key.from_private_key(private_key_file) if "BEGIN OPENSSH PRIVATE KEY" in private_key_pem_str and "ed25519" in private_key_pem_str.lower() else paramiko.RSAKey.from_private_key(private_key_file)
            private_key_file.close()

            username = "ec2-user"
            current_app.logger.info(f"Attempting SSH to {username}@{instance_ip} for session {scenario_session_id} using key type: {type(pkey)}")
            ssh_client.connect(hostname=instance_ip, username=username, pkey=pkey, timeout=30, look_for_keys=False, allow_agent=False)
            
            channel = ssh_client.invoke_shell(term='xterm-256color', width=80, height=24)
            channel.settimeout(0.0)

            session_pty_data["ssh_client"] = ssh_client
            session_pty_data["ssh_channel"] = channel
            
            app_context_obj = current_app._get_current_object() 
            reader_greenlet = socketio.start_background_task(
                target=ssh_output_reader, 
                app_for_context=app_context_obj,
                scenario_id=scenario_session_id, 
                channel=channel
            )
            session_pty_data["reader_greenlet"] = reader_greenlet
            current_app.logger.info(f"SSH connection and PTY established for session {scenario_session_id}.")
        
        except Exception as e:
            current_app.logger.error(f"SSH connection or PTY setup FAILED for {scenario_session_id}: {e}", exc_info=True)
            emit('pty-output', {"output": f"\r\nSSH Connection Error: {str(e)}\r\n"})
            if session_pty_data.get("ssh_client"):
                session_pty_data["ssh_client"].close()
            session_pty_data["ssh_client"] = None
            session_pty_data["ssh_channel"] = None
            return

    # CHANGED METHOD NAME HERE (and corresponding logging)
    def on_terminalInput(self, data): # Handles 'terminalInput' event
        client_sid = request.sid
        scenario_session_id = data.get('sessionId') 
        input_data = data.get('input', '')

        current_app.logger.error( # Using ERROR level for high visibility
             f"!!!!!!!!!! [TERMINAL_INPUT_HANDLER - terminalInput EVENT] Triggered by SID {client_sid} " +
             f"for scenario_session_id '{scenario_session_id}'. Input: {input_data!r} !!!!!!!!!!"
        )
        
        if not scenario_session_id:
            current_app.logger.error(f"[TERMINAL_INPUT_HANDLER] No sessionId in terminalInput data from {client_sid}")
            return {"status": "error", "message": "No sessionId provided with input"}

        if scenario_session_id not in PTY_PROCESSES:
            current_app.logger.warning(f"[TERMINAL_INPUT_HANDLER] terminalInput for unknown/inactive session {scenario_session_id} from {client_sid}")
            emit('pty-output', {'output': '\r\nError: Session not active or invalid.\r\n'}) 
            return {"status": "error", "message": "Session not active or invalid"}

        session_info = PTY_PROCESSES[scenario_session_id]
        channel = session_info.get("ssh_channel")

        if channel and channel.active:
            current_app.logger.info(f"[TERMINAL_INPUT_HANDLER] Channel for {scenario_session_id} is active.")
            try:
                bytes_sent = channel.send(input_data) 
                current_app.logger.info(f"[TERMINAL_INPUT_HANDLER] Sent {bytes_sent} bytes to PTY for {scenario_session_id}: {input_data!r}")
                if not input_data and bytes_sent == 0:
                     pass 
                elif bytes_sent == 0 and input_data:
                     current_app.logger.warning(f"[TERMINAL_INPUT_HANDLER] Sent 0 bytes to PTY for non-empty input data for {scenario_session_id}.")
                return {"status": "ok", "message": f"Input '{input_data[:20]}' processed, {bytes_sent} bytes sent."}
            except Exception as e:
                current_app.logger.error(f"[TERMINAL_INPUT_HANDLER] Error writing to SSH PTY for {scenario_session_id}: {e}", exc_info=True)
                emit('pty-output', {'output': f'\r\nError sending input: {e}\r\n'}, room=scenario_session_id)
                return {"status": "error", "message": f"Server error sending input: {str(e)}"}
        else:
            current_app.logger.warning(f"[TERMINAL_INPUT_HANDLER] No active SSH PTY channel for session {scenario_session_id} to write input. Input: {input_data!r}")
            emit('pty-output', {'output': '\r\nTerminal session not active or not fully initialized.\r\n'}, room=scenario_session_id)
            return {"status": "error", "message": "No active channel"}
         
        current_app.logger.error(f"[TERMINAL_INPUT_HANDLER] Fell through for {scenario_session_id}. This should not happen.")
        return {"status": "unhandled_error", "message": "Input processing logic error on server."}


    def on_resize(self, data):
        client_sid = request.sid
        scenario_session_id = data.get('sessionId')
        rows = data.get('rows')
        cols = data.get('cols')

        if not scenario_session_id or scenario_session_id not in PTY_PROCESSES or not isinstance(rows, int) or not isinstance(cols, int): 
            current_app.logger.warning(f"Invalid resize data for {scenario_session_id} from {client_sid}: rows={rows}, cols={cols}")
            return

        session_info = PTY_PROCESSES[scenario_session_id]
        channel = session_info.get("ssh_channel")

        if channel and channel.active:
            try:
                channel.resize_pty(width=cols, height=rows)
                current_app.logger.info(f"Resized PTY for {scenario_session_id} (client {client_sid}) to {cols}x{rows}")
            except Exception as e:
                current_app.logger.error(f"Error resizing PTY for {scenario_session_id}: {e}")
    
    def on_disconnect_request(self, data):
        client_sid = request.sid
        scenario_session_id = data.get('sessionId')
        current_app.logger.info(f"Client SID {client_sid} sent disconnect_request for scenario {scenario_session_id}")
        self.on_disconnect(manual_scenario_id_override=scenario_session_id)
        disconnect(sid=client_sid, namespace=self.namespace)


    def on_disconnect(self, manual_scenario_id_override=None):
        client_sid = request.sid
        current_app.logger.info(f"Processing disconnect for Client SID {client_sid} in namespace {self.namespace}")
        
        scenario_to_cleanup = None
        target_scenario_id_for_client = manual_scenario_id_override
        
        if not target_scenario_id_for_client:
            for s_id, session_data_val in PTY_PROCESSES.items():
                if client_sid in session_data_val.get("clients", set()):
                    target_scenario_id_for_client = s_id
                    break
        
        if target_scenario_id_for_client and target_scenario_id_for_client in PTY_PROCESSES:
            session_data = PTY_PROCESSES[target_scenario_id_for_client]
            if client_sid in session_data.get("clients", set()):
                session_data["clients"].remove(client_sid)
                current_app.logger.info(f"Client SID {client_sid} removed from scenario {target_scenario_id_for_client} client set. Remaining clients: {len(session_data['clients'])}")
                if not session_data["clients"]: 
                    current_app.logger.info(f"Last client for scenario {target_scenario_id_for_client} disconnected. Scheduling full cleanup.")
                    scenario_to_cleanup = target_scenario_id_for_client
            else:
                current_app.logger.warning(f"Client SID {client_sid} was in scenario {target_scenario_id_for_client} but not in its 'clients' set (possibly already removed).")
        else:
            current_app.logger.warning(f"Client SID {client_sid} disconnected. Could not determine associated scenario session or PTY_PROCESSES entry not found for '{target_scenario_id_for_client}'.")

        if scenario_to_cleanup:
            app_context_obj = current_app._get_current_object()
            socketio.start_background_task(target=cleanup_scenario_session, app_for_context=app_context_obj, scenario_id=scenario_to_cleanup)

socketio.on_namespace(TerminalNamespace('/terminal_ws'))
