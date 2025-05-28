from flask import request, current_app
from flask_socketio import emit, join_room, leave_room
from app import socketio # Import the socketio instance from app/__init__.py
from .scenarios import SCENARIO_SESSIONS # Import the session store
import subprocess
import os
import pty # For PTY management (basic example)
import select # For reading from PTY

# Store PTY processes and file descriptors associated with session IDs
# WARNING: This is a simplified in-memory store and not robust for production.
# It also doesn't handle multiple simultaneous terminals per session well.
PTY_PROCESSES = {}


@socketio.on('connect', namespace='/terminal_ws')
def handle_terminal_connect():
    session_id = request.sid # Socket.IO provides a unique session ID for each connection
    # We need a way for the client to tell us WHICH scenario session this terminal is for.
    # For now, we'll just log it. The client will need to send a 'join' event with its scenario_session_id
    current_app.logger.info(f"Terminal client connected: SID {session_id}")
    emit('pty-output', {"output": f"Welcome! WebSocket Connection SID: {session_id}\r\nSend a 'join_scenario' event with your scenario's sessionId.\r\n"})


@socketio.on('join_scenario', namespace='/terminal_ws')
def handle_join_scenario(data):
    client_sid = request.sid
    scenario_session_id = data.get('sessionId')

    if not scenario_session_id or scenario_session_id not in SCENARIO_SESSIONS:
        current_app.logger.error(f"Client {client_sid} tried to join invalid scenario session: {scenario_session_id}")
        emit('pty-output', {"output": f"Error: Invalid or unknown scenario session ID: {scenario_session_id}\r\n"})
        return

    join_room(scenario_session_id) # Socket.IO room for this scenario
    current_app.logger.info(f"Client SID {client_sid} joined scenario room: {scenario_session_id}")
    
    # --- Phase 2/3: PTY/SSH/Docker exec would happen here ---
    # For Phase 1, we just confirm and provide a prompt.
    # In a real scenario, you'd start the PTY process now if not already started for this session.
    # For this simplified echo example, we don't need to manage a separate PTY process per client yet.
    
    # Store client SID against the scenario_session_id if needed for direct messaging
    if scenario_session_id not in PTY_PROCESSES:
         PTY_PROCESSES[scenario_session_id] = {"clients": set(), "pty_master_fd": None, "pty_child_pid": None}
    PTY_PROCESSES[scenario_session_id]["clients"].add(client_sid)


    emit('pty-output', {"output": f"Joined scenario '{SCENARIO_SESSIONS[scenario_session_id]['repo']}'.\r\nPhase 1: Echo mode active.\r\n$ "})
    # Example: Starting a simple bash shell in a PTY (VERY basic, needs error handling & robust management)
    # if PTY_PROCESSES[scenario_session_id].get("pty_master_fd") is None:
    #     try:
    #         master_fd, slave_fd = pty.openpty()
    #         # To make it non-blocking for select
    #         os.set_blocking(master_fd, False)
            
    #         child_pid = os.fork()
    #         if child_pid == 0: # Child process
    #             os.setsid()
    #             os.dup2(slave_fd, 0) # stdin
    #             os.dup2(slave_fd, 1) # stdout
    #             os.dup2(slave_fd, 2) # stderr
    #             os.close(master_fd)
    #             os.close(slave_fd)
    #             # In a real case, you might 'cd' into scenario_specific_dir
    #             # and then execute something specific to that scenario.
    #             # For now, just a bash shell.
    #             # IMPORTANT: This bash shell is running AS THE FLASK SERVER USER.
    #             #            This is a huge security risk if not managed carefully.
    #             os.execv('/bin/bash', ['/bin/bash']) 
    #         else: # Parent process
    #             os.close(slave_fd)
    #             PTY_PROCESSES[scenario_session_id]["pty_master_fd"] = master_fd
    #             PTY_PROCESSES[scenario_session_id]["pty_child_pid"] = child_pid
    #             current_app.logger.info(f"PTY master_fd {master_fd} and child_pid {child_pid} created for {scenario_session_id}")
    #             # Start a background thread/task to read from this PTY master_fd
    #             socketio.start_background_task(target=read_from_pty, scenario_id=scenario_session_id, master_fd=master_fd)

    #     except Exception as e:
    #         current_app.logger.error(f"Failed to create PTY for {scenario_session_id}: {e}")
    #         emit('pty-output', {"output": f"\r\nError starting terminal: {e}\r\n"})


# def read_from_pty(scenario_id, master_fd):
#     """Background task to read from PTY and emit to clients in the room."""
#     current_app.logger.info(f"Background PTY reader started for {scenario_id} on fd {master_fd}")
#     try:
#         while True:
#             socketio.sleep(0.01) # Yield for other greenlets
#             r, _, _ = select.select([master_fd], [], [], 0) # Non-blocking read
#             if r:
#                 try:
#                     output = os.read(master_fd, 1024)
#                     if output:
#                         socketio.emit('pty-output', {'output': output.decode(errors='replace')}, room=scenario_id, namespace='/terminal_ws')
#                     else: # PTY closed (child exited)
#                         current_app.logger.info(f"PTY for {scenario_id} closed (EOF).")
#                         break 
#                 except OSError as e:
#                     current_app.logger.error(f"OSError reading from PTY for {scenario_id}: {e}")
#                     break # Exit loop on error
#     except Exception as e:
#         current_app.logger.error(f"Exception in PTY reader for {scenario_id}: {e}")
#     finally:
#         current_app.logger.info(f"PTY reader for {scenario_id} stopping.")
#         if master_fd:
#             os.close(master_fd)
#         if PTY_PROCESSES.get(scenario_id):
#             PTY_PROCESSES[scenario_id]["pty_master_fd"] = None
#             # Consider more cleanup, like ensuring child_pid is terminated

@socketio.on('pty-input', namespace='/terminal_ws')
def handle_terminal_input(data):
    client_sid = request.sid
    scenario_session_id = None
    # Find which scenario session this client SID belongs to
    for s_id, session_data in PTY_PROCESSES.items():
        if client_sid in session_data.get("clients", set()):
            scenario_session_id = s_id
            break
    
    if not scenario_session_id:
        current_app.logger.warning(f"Pty-input from unknown client SID: {client_sid}")
        return

    input_data = data.get('input', '')
    current_app.logger.debug(f"Input from SID {client_sid} for scenario {scenario_session_id}: {input_data!r}")

    # --- Phase 1: Echo back ---
    emit('pty-output', {"output": f"{input_data}$ "}, room=scenario_session_id) # Echo back to the room

    # --- Phase 2/3: Write to PTY ---
    # master_fd = PTY_PROCESSES[scenario_session_id].get("pty_master_fd")
    # if master_fd:
    #     try:
    #         os.write(master_fd, input_data.encode())
    #     except OSError as e:
    #         current_app.logger.error(f"OSError writing to PTY for {scenario_session_id}: {e}")
    #         emit('pty-output', {"output": f"\r\nError writing to terminal: {e}\r\n"}, room=scenario_session_id)
    # else:
    #     current_app.logger.warning(f"No PTY master_fd for session {scenario_session_id} to write input.")
    #     emit('pty-output', {"output": f"\r\nTerminal not fully initialized for this session.\r\n$ "}, room=scenario_session_id)


@socketio.on('disconnect', namespace='/terminal_ws')
def handle_terminal_disconnect():
    client_sid = request.sid
    current_app.logger.info(f"Terminal client disconnected: SID {client_sid}")
    
    scenario_to_cleanup = None
    for s_id, session_data in PTY_PROCESSES.items():
        if client_sid in session_data.get("clients", set()):
            session_data["clients"].remove(client_sid)
            if not session_data["clients"]: # If last client for this scenario session
                scenario_to_cleanup = s_id
            break

    if scenario_to_cleanup:
        current_app.logger.info(f"Last client for scenario {scenario_to_cleanup} disconnected. Cleaning up.")
        # --- Phase 2/3: Terminate PTY and run terraform destroy ---
        # master_fd = PTY_PROCESSES[scenario_to_cleanup].get("pty_master_fd")
        # if master_fd:
        #     try:
        #         os.close(master_fd)
        #     except OSError:
        #         pass # May already be closed
        
        # child_pid = PTY_PROCESSES[scenario_to_cleanup].get("pty_child_pid")
        # if child_pid:
        #     try:
        #         os.kill(child_pid, 15) # SIGTERM
        #         os.waitpid(child_pid, 0) # Wait for child to exit
        #     except ProcessLookupError:
        #         pass # Process already exited
        #     except Exception as e:
        #         current_app.logger.error(f"Error terminating PTY child {child_pid}: {e}")

        # tf_dir = SCENARIO_SESSIONS.get(scenario_to_cleanup, {}).get("terraform_dir")
        # if tf_dir and os.path.exists(tf_dir):
        #     try:
        #         current_app.logger.info(f"Running terraform destroy for {scenario_to_cleanup} in {tf_dir}")
        #         # subprocess.run(['terraform', 'destroy', '--auto-approve'], check=True, cwd=tf_dir)
        #         # shutil.rmtree(tf_dir) # Clean up the directory
        #         current_app.logger.info(f"Terraform destroy (placeholder) and cleanup for {scenario_to_cleanup} done.")
        #     except Exception as e:
        #         current_app.logger.error(f"Error during terraform destroy for {scenario_to_cleanup}: {e}")
        
        del PTY_PROCESSES[scenario_to_cleanup]
        if scenario_to_cleanup in SCENARIO_SESSIONS:
            del SCENARIO_SESSIONS[scenario_to_cleanup]
