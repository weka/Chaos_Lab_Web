# --- START server/app/api/terminal_events.py ---
import os
import select
import time
import paramiko
import io
import subprocess
import shutil
from flask import request, current_app # Flask import was missing in one version
from flask_socketio import emit, join_room, leave_room, disconnect, Namespace
from app import socketio # Import the main socketio instance
from .scenarios import SCENARIO_SESSIONS # Import from scenarios.py in the same package
import boto3

# NEW: Import remove_timer
from app.timer_manager import remove_timer as remove_session_timer

PTY_PROCESSES = {} # To store PTY process info (client, channel, greenlet)

def ssh_output_reader(app_for_context, scenario_id, channel):
    with app_for_context.app_context(): # Ensure Flask app context for logging etc.
        logger = app_for_context.logger # Use logger from passed app instance for consistency
        logger.info(f"[SSH Reader {scenario_id}]: Starting PTY output reader for channel {channel}.")
        try:
            while channel and channel.active:
                socketio.sleep(0.01) # Yield for eventlet
                read_ready, _, _ = select.select([channel], [], [], 0.05) # Check if channel is ready
                if read_ready:
                    if channel.recv_ready(): # Check for stdout
                        output = channel.recv(4096).decode(errors='replace')
                        if output:
                            socketio.emit('pty-output', {'output': output}, room=scenario_id, namespace='/terminal_ws')
                        # else: # Can be noisy if channel is just idle
                        #     logger.debug(f"[SSH Reader {scenario_id}]: Channel recv_ready but got empty output.")
                    
                    if channel.recv_stderr_ready(): # Check for stderr
                        stderr_output = channel.recv_stderr(4096).decode(errors='replace')
                        if stderr_output:
                            socketio.emit('pty-output', {'output': stderr_output}, room=scenario_id, namespace='/terminal_ws')
                
                if channel.exit_status_ready(): # Check if remote command/shell has exited
                    logger.info(f"[SSH Reader {scenario_id}]: Channel exit status ready. Exiting reader.")
                    break
        except paramiko.SSHException as e:
            logger.error(f"[SSH Reader {scenario_id}]: SSHException in PTY reader: {e}", exc_info=False)
            socketio.emit('pty-output', {'output': f"\r\n[SSH Connection Error in reader: {e}]\r\n"}, room=scenario_id, namespace='/terminal_ws')
        except Exception as e:
            logger.error(f"[SSH Reader {scenario_id}]: Unhandled exception in PTY reader: {e}", exc_info=True)
            socketio.emit('pty-output', {'output': f"\r\n[Error reading from remote: {e}]\r\n"}, room=scenario_id, namespace='/terminal_ws')
        finally:
            logger.info(f"[SSH Reader {scenario_id}]: PTY output reader stopped for channel {channel}.")
            if scenario_id in PTY_PROCESSES and PTY_PROCESSES[scenario_id].get("ssh_channel") == channel:
                 socketio.emit('pty-output', {'output': '\r\n[Terminal session may have ended or encountered an issue.]\r\n$ '}, room=scenario_id, namespace='/terminal_ws')
                 PTY_PROCESSES[scenario_id]["ssh_channel"] = None


def cleanup_scenario_session(app_for_context, scenario_id): # Renamed function to match call from on_disconnect
    with app_for_context.app_context():
        logger = app_for_context.logger # Use logger from passed app instance
        logger.info(f"Cleanup: Starting for scenario session: {scenario_id}")

        # NEW: Remove timer early in the cleanup process
        was_timer_removed = remove_session_timer(scenario_id, app_logger=logger)
        if was_timer_removed:
            logger.info(f"Cleanup: Timer removed for session {scenario_id}.")
        # else: # This is fine if timer was already gone or never set for this session
        #     logger.debug(f"Cleanup: No timer found to remove for session {scenario_id}, or already removed.")

        # Clean up PTY process data
        session_pty_data = PTY_PROCESSES.pop(scenario_id, None)
        if session_pty_data:
            channel = session_pty_data.get("ssh_channel")
            if channel:
                try: 
                    logger.info(f"Cleanup: Closing SSH channel for {scenario_id}")
                    channel.close()
                except Exception as e: logger.error(f"Cleanup: Error closing SSH channel for {scenario_id}: {e}")
            
            ssh_client = session_pty_data.get("ssh_client")
            if ssh_client:
                try: 
                    logger.info(f"Cleanup: Closing SSH client for {scenario_id}")
                    ssh_client.close()
                except Exception as e: logger.error(f"Cleanup: Error closing SSH client for {scenario_id}: {e}")
            
            reader_greenlet = session_pty_data.get("reader_greenlet")
            if reader_greenlet and hasattr(reader_greenlet, 'kill'):
                 try:
                     logger.info(f"Cleanup: Attempting to kill reader greenlet for {scenario_id}")
                     reader_greenlet.kill()
                 except Exception as e:
                     logger.error(f"Cleanup: Error killing reader greenlet for {scenario_id}: {e}")
            logger.info(f"Cleanup: PTY resources processed for {scenario_id}.")
        else:
            logger.info(f"Cleanup: No PTY process data found for {scenario_id} (already cleaned or never existed).")


        # Clean up scenario metadata and Terraform resources
        scenario_meta_data = SCENARIO_SESSIONS.pop(scenario_id, None)
        if scenario_meta_data:
            tf_dir = scenario_meta_data.get("terraform_dir")
            terraform_name_prefix_var = scenario_meta_data.get("terraform_name_prefix_for_run", scenario_id) 

            if tf_dir and os.path.exists(tf_dir):
                logger.info(f"Cleanup: Running terraform destroy for {scenario_id} (prefix: {terraform_name_prefix_var}) in {tf_dir}")
                try:
                    destroy_cmd = ['terraform', 'destroy', '--auto-approve', '-no-color', '-input=false']
                    # For Step A, we don't differentiate parallelism yet based on timer. That's Step D.
                    destroy_result = subprocess.run(destroy_cmd, cwd=tf_dir, capture_output=True, text=True, timeout=600) # 10 min timeout
                    if destroy_result.returncode == 0:
                        logger.info(f"Cleanup: Terraform destroy successful for {scenario_id}:\n{destroy_result.stdout}")
                    else:
                        logger.error(f"Cleanup: Terraform destroy FAILED for {scenario_id}. Code: {destroy_result.returncode}\nStderr:\n{destroy_result.stderr}\nStdout:\n{destroy_result.stdout}")
                    
                    aws_key_name = scenario_meta_data.get("key_name_aws")
                    if aws_key_name:
                        logger.info(f"Cleanup: Attempting to delete AWS key pair: {aws_key_name}")
                        try:
                            ec2_client = boto3.client('ec2')
                            ec2_client.delete_key_pair(KeyName=aws_key_name)
                            logger.info(f"Cleanup: Successfully deleted AWS key pair: {aws_key_name}")
                        except Exception as key_del_e:
                            logger.error(f"Cleanup: Failed to delete AWS key pair {aws_key_name}: {key_del_e}")
                    else:
                        logger.warning(f"Cleanup: No 'key_name_aws' in metadata for {scenario_id}, skipping key deletion.")

                    logger.info(f"Cleanup: Attempting to remove directory: {tf_dir}")
                    shutil.rmtree(tf_dir, ignore_errors=True)
                    logger.info(f"Cleanup: Removed directory {tf_dir}")

                except subprocess.TimeoutExpired:
                    logger.error(f"Cleanup: Terraform destroy timed out for {scenario_id} in {tf_dir}")
                except Exception as e:
                    logger.error(f"Cleanup: Error during terraform destroy or directory cleanup for {scenario_id} in {tf_dir}: {e}", exc_info=True)
            else:
                logger.warning(f"Cleanup: Terraform directory '{tf_dir}' not found or not specified for cleanup of {scenario_id}")
        else:
            logger.warning(f"Cleanup: No scenario metadata (SCENARIO_SESSIONS) found for {scenario_id} (already cleaned or never existed).")
        logger.info(f"Cleanup: Full cleanup process finished for scenario session {scenario_id}")


class TerminalNamespace(Namespace):
    def on_connect(self):
        client_sid = request.sid
        current_app.logger.info(f"SocketIO: Client SID {client_sid} connected to namespace {self.namespace}.")
        emit('pty-output', {"output": f"Socket.IO Connected (SID: {client_sid}). Send 'join_scenario' with your scenario's sessionId.\r\n"})

    def on_join_scenario(self, data):
        client_sid = request.sid
        scenario_session_id = data.get('sessionId')
        current_app.logger.info(f"SocketIO: Client {client_sid} attempting to join scenario: {scenario_session_id}")

        if not scenario_session_id or scenario_session_id not in SCENARIO_SESSIONS:
            current_app.logger.error(f"SocketIO: Client {client_sid} - Invalid/unknown scenario session ID: {scenario_session_id}")
            emit('pty-output', {"output": f"\r\nError: Invalid or unknown scenario session ID: {scenario_session_id}\r\n"})
            disconnect(sid=client_sid) 
            return

        join_room(scenario_session_id, sid=client_sid, namespace=self.namespace)
        current_app.logger.info(f"SocketIO: Client SID {client_sid} joined scenario room: {scenario_session_id}")

        if scenario_session_id not in PTY_PROCESSES:
            PTY_PROCESSES[scenario_session_id] = {"clients": set(), "ssh_client": None, "ssh_channel": None, "reader_greenlet": None}
        
        PTY_PROCESSES[scenario_session_id]["clients"].add(client_sid)
        
        session_pty_data = PTY_PROCESSES[scenario_session_id]
        if session_pty_data.get("ssh_channel") and session_pty_data["ssh_channel"].active:
            current_app.logger.info(f"SocketIO: Client {client_sid} rejoining active SSH for {scenario_session_id}")
            emit('pty-output', {"output": f"\r\nRejoined active session for '{SCENARIO_SESSIONS[scenario_session_id]['repo']}'.\r\n"}, room=client_sid)
            try:
                session_pty_data["ssh_channel"].send("\n") 
            except Exception as e:
                current_app.logger.warning(f"SocketIO: Could not send newline to re-joined channel for {scenario_session_id}: {e}")
            return

        emit('pty-output', {"output": f"\r\nJoining scenario '{SCENARIO_SESSIONS[scenario_session_id]['repo']}'. Establishing SSH connection...\r\n"}, room=client_sid)
        
        scenario_data = SCENARIO_SESSIONS[scenario_session_id]
        instance_ip = scenario_data.get("instance_ip")
        private_key_pem_str = scenario_data.get("private_key_pem_content")

        if not instance_ip or not private_key_pem_str:
            msg = "\r\nError: Instance IP or private key not found for this session.\r\n"
            current_app.logger.error(f"SocketIO: SSH Config error for session {scenario_session_id}: Missing IP or PEM.")
            emit('pty-output', {"output": msg}, room=client_sid)
            disconnect(sid=client_sid)
            return

        try:
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            private_key_file = io.StringIO(private_key_pem_str)
            pkey = None
            # Attempt to load key, trying common types
            key_load_error = None
            for key_type_class in [paramiko.Ed25519Key, paramiko.RSAKey, paramiko.DSSKey, paramiko.ECDSAKey]:
                try:
                    private_key_file.seek(0) # Reset for each attempt
                    pkey = key_type_class.from_private_key(private_key_file)
                    current_app.logger.info(f"SocketIO: Loaded private key as {key_type_class.__name__} for {scenario_session_id}.")
                    break 
                except paramiko.SSHException as e:
                    key_load_error = e # Store last error
                    continue 
            private_key_file.close()
            if not pkey:
                current_app.logger.error(f"SocketIO: Failed to load private key with any known type for {scenario_session_id}. Last error: {key_load_error}")
                raise paramiko.SSHException(f"Could not load private key. Last error: {key_load_error}")


            username = "ec2-user"
            current_app.logger.info(f"SocketIO: Attempting SSH to {username}@{instance_ip} for session {scenario_session_id} (Key: {type(pkey).__name__})")
            ssh_client.connect(hostname=instance_ip, username=username, pkey=pkey, timeout=30, look_for_keys=False, allow_agent=False)
            
            channel = ssh_client.invoke_shell(term='xterm-256color', width=80, height=24)
            channel.settimeout(0.0) # Non-blocking

            session_pty_data["ssh_client"] = ssh_client
            session_pty_data["ssh_channel"] = channel
            
            app_for_bg_task = current_app._get_current_object() 
            reader_greenlet = socketio.start_background_task(
                target=ssh_output_reader, 
                app_for_context=app_for_bg_task,
                scenario_id=scenario_session_id, 
                channel=channel
            )
            session_pty_data["reader_greenlet"] = reader_greenlet
            current_app.logger.info(f"SocketIO: SSH connection and PTY established for session {scenario_session_id}.")
        
        except Exception as e:
            current_app.logger.error(f"SocketIO: SSH connection or PTY setup FAILED for {scenario_session_id}: {e}", exc_info=True)
            emit('pty-output', {"output": f"\r\nSSH Connection Error: {str(e)}\r\n"}, room=client_sid)
            if session_pty_data.get("ssh_client"):
                session_pty_data["ssh_client"].close()
            session_pty_data["ssh_client"] = None
            session_pty_data["ssh_channel"] = None
            return

    def on_terminalInput(self, data):
        client_sid = request.sid
        scenario_session_id = data.get('sessionId') 
        input_data = data.get('input', '')
        # current_app.logger.debug(f"SocketIO Input: SID {client_sid} for session '{scenario_session_id}'. Input: {input_data!r}")
        
        if not scenario_session_id:
            current_app.logger.error(f"SocketIO Input: No sessionId in terminalInput from {client_sid}")
            return {"status": "error", "message": "No sessionId provided with input"}

        if scenario_session_id not in PTY_PROCESSES or not PTY_PROCESSES[scenario_session_id].get("ssh_channel"):
            current_app.logger.warning(f"SocketIO Input: terminalInput for unknown/inactive PTY session {scenario_session_id} from {client_sid}")
            emit('pty-output', {'output': '\r\nError: Session not active or channel invalid.\r\n'}, room=client_sid) 
            return {"status": "error", "message": "Session not active or channel invalid"}

        session_info = PTY_PROCESSES[scenario_session_id]
        channel = session_info.get("ssh_channel")

        if channel and channel.active:
            try:
                bytes_sent = channel.send(input_data) 
                if not input_data and bytes_sent == 0: pass 
                elif bytes_sent == 0 and input_data: current_app.logger.warning(f"SocketIO Input: Sent 0 bytes for non-empty input for {scenario_session_id}.")
                return {"status": "ok", "bytes_sent": bytes_sent}
            except Exception as e:
                current_app.logger.error(f"SocketIO Input: Error writing to SSH PTY for {scenario_session_id}: {e}", exc_info=True)
                emit('pty-output', {'output': f'\r\n[Server Error: Could not send input: {e}]\r\n'}, room=client_sid)
                return {"status": "error", "message": f"Server error sending input: {str(e)}"}
        else:
            current_app.logger.warning(f"SocketIO Input: No active SSH PTY channel for session {scenario_session_id}. Input: {input_data!r}")
            emit('pty-output', {'output': '\r\nTerminal session not active or not fully initialized.\r\n'}, room=client_sid)
            return {"status": "error", "message": "No active channel"}

    def on_resize(self, data):
        client_sid = request.sid
        scenario_session_id = data.get('sessionId')
        rows = data.get('rows')
        cols = data.get('cols')
        current_app.logger.debug(f"SocketIO Resize: SID {client_sid} for {scenario_session_id}. Rows: {rows}, Cols: {cols}")

        if not all([scenario_session_id, isinstance(rows, int), isinstance(cols, int)]):
            current_app.logger.warning(f"SocketIO Resize: Invalid data from {client_sid}: {data}")
            return

        if scenario_session_id not in PTY_PROCESSES or not PTY_PROCESSES[scenario_session_id].get("ssh_channel"):
            current_app.logger.warning(f"SocketIO Resize: For unknown/inactive PTY session {scenario_session_id} from {client_sid}")
            return

        session_info = PTY_PROCESSES[scenario_session_id]
        channel = session_info.get("ssh_channel")

        if channel and channel.active:
            try:
                channel.resize_pty(width=cols, height=rows)
                current_app.logger.info(f"SocketIO Resize: Resized PTY for {scenario_session_id} (client {client_sid}) to {cols}x{rows}")
            except Exception as e:
                current_app.logger.error(f"SocketIO Resize: Error resizing PTY for {scenario_session_id}: {e}")
        else:
            current_app.logger.warning(f"SocketIO Resize: Attempt for {scenario_session_id} but no active channel.")
    
    def on_disconnect_request(self, data):
        client_sid = request.sid
        scenario_session_id = data.get('sessionId')
        current_app.logger.info(f"SocketIO DisconnectReq: Client SID {client_sid} for scenario {scenario_session_id}")
        self.on_disconnect(manual_scenario_id_override=scenario_session_id)
        disconnect(sid=client_sid, namespace=self.namespace)
        current_app.logger.info(f"SocketIO DisconnectReq: Client SID {client_sid} disconnected from namespace.")


    def on_disconnect(self, manual_scenario_id_override=None):
        client_sid = request.sid
        current_app.logger.info(f"SocketIO Disconnect: Processing for Client SID {client_sid}. Override ID: {manual_scenario_id_override}")
        
        scenario_to_cleanup_if_last = None
        target_scenario_id_for_client = manual_scenario_id_override
        if not target_scenario_id_for_client:
            for s_id, pty_data_val in PTY_PROCESSES.items():
                if client_sid in pty_data_val.get("clients", set()):
                    target_scenario_id_for_client = s_id
                    break
        
        if target_scenario_id_for_client and target_scenario_id_for_client in PTY_PROCESSES:
            pty_session_data = PTY_PROCESSES[target_scenario_id_for_client]
            if client_sid in pty_session_data.get("clients", set()):
                pty_session_data["clients"].remove(client_sid)
                current_app.logger.info(f"SocketIO Disconnect: Client SID {client_sid} removed from PTY session {target_scenario_id_for_client}. Remaining clients: {len(pty_session_data['clients'])}")
                if not pty_session_data["clients"]: 
                    current_app.logger.info(f"SocketIO Disconnect: Last client for PTY session {target_scenario_id_for_client} disconnected.")
                    scenario_to_cleanup_if_last = target_scenario_id_for_client
            # else: (Client already removed or not in set, can be normal)
        else:
            current_app.logger.info(f"SocketIO Disconnect: Client SID {client_sid}. No PTY session for '{target_scenario_id_for_client}'.")

        if scenario_to_cleanup_if_last:
            if scenario_to_cleanup_if_last in SCENARIO_SESSIONS: # Check if main scenario session still active
                app_for_bg_task = current_app._get_current_object()
                current_app.logger.info(f"SocketIO Disconnect: Scheduling full cleanup for {scenario_to_cleanup_if_last} (last PTY client, session active).")
                socketio.start_background_task(
                    target=cleanup_scenario_session, 
                    app_for_context=app_for_bg_task, 
                    scenario_id=scenario_to_cleanup_if_last
                    # For Step A, triggered_by_timer=False is implied as this is client disconnect
                )
            else:
                current_app.logger.info(f"SocketIO Disconnect: PTY for {scenario_to_cleanup_if_last} ended, but SCENARIO_SESSIONS entry already gone.")
        current_app.logger.info(f"SocketIO Disconnect: Processing complete for {client_sid}.")

socketio.on_namespace(TerminalNamespace('/terminal_ws'))
# --- END server/app/api/terminal_events.py ---
