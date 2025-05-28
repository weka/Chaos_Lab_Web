// client/src/components/TerminalView.jsx
import React, { useEffect, useRef, useCallback, memo } from 'react';
import PropTypes from 'prop-types';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { io } from 'socket.io-client';
import 'xterm/css/xterm.css';
import './TerminalView.css'; // Make sure this file exists or remove if not used

const API_BASE_URL = import.meta.env.VITE_APP_BASE_URL || 'http://localhost:5000';

function TerminalView({ sessionId, websocketPath, onCloseTerminal }) {
  const termContainerRef = useRef(null);
  const xtermInstanceRef = useRef(null);
  const socketRef = useRef(null);
  const fitAddonRef = useRef(null);

  const sendResize = useCallback(() => {
    if (socketRef.current && socketRef.current.connected && xtermInstanceRef.current && fitAddonRef.current) {
      try {
        fitAddonRef.current.fit();
        const { cols, rows } = xtermInstanceRef.current;
        socketRef.current.emit('resize', { // This event name seems to work based on logs
          sessionId: sessionId,
          cols: cols,
          rows: rows,
        });
        console.log(`[TerminalView ${sessionId}] Sent resize: ${cols}x${rows}`);
      } catch (e) {
        console.error(`[TerminalView ${sessionId}] Error during resize:`, e);
      }
    }
  }, [sessionId]);

  useEffect(() => {
    let term;
    let fitAddon;
    let socket;

    if (termContainerRef.current && !xtermInstanceRef.current && sessionId && websocketPath) {
      console.log(`[TerminalView ${sessionId}] Initializing... Path: ${websocketPath}`);

      term = new Terminal({
        cursorBlink: true,
        convertEol: true,
        rows: 24,
        cols: 80,
        fontSize: 14,
        fontFamily: 'monospace, "Courier New", Courier',
        theme: {
          background: '#1e1e1e',
          foreground: '#00FF00',
          cursor: '#00FF00',
          selectionBackground: '#555555',
        },
        allowProposedApi: true,
        scrollback: 1000,
      });
      xtermInstanceRef.current = term;

      fitAddon = new FitAddon();
      fitAddonRef.current = fitAddon;
      term.loadAddon(fitAddon);

      term.open(termContainerRef.current);
      try {
        fitAddon.fit();
      } catch(e) {
        console.error(`[TerminalView ${sessionId}] Initial fit failed:`, e);
      }
      term.focus();

      const fullWebsocketUrl = `${API_BASE_URL}${websocketPath}`;
      console.log(`[TerminalView ${sessionId}] Attempting Socket.IO connection to: ${fullWebsocketUrl}`);
      
      socket = io(fullWebsocketUrl, {
        path: '/socket.io',
        transports: ['websocket'],
        reconnectionAttempts: 3,
      });
      socketRef.current = socket;

      socket.on('connect', () => {
        term.writeln('\r\n\x1b[32mSocket.IO: Connected to backend session.\x1b[0m');
        console.log(`[TerminalView ${sessionId}] Socket.IO Connected. SID: ${socket.id}. Emitting 'join_scenario'.`);
        socket.emit('join_scenario', { sessionId: sessionId });
        setTimeout(sendResize, 150);
      });

      socket.on('pty-output', (data) => { // This event name seems to work for receiving
        if (data && typeof data.output === 'string') {
          term.write(data.output);
        }
      });
      
      socket.on('disconnect', (reason) => {
        const msg = `\r\n\x1b[31mSocket.IO Disconnected: ${reason}. SID was: ${socket.id || 'N/A'}\x1b[0m`;
        term.writeln(msg);
        console.error(`[TerminalView ${sessionId}] Socket.IO Disconnected: ${reason}. Previous SID: ${socket.id || 'N/A'}`);
      });

      socket.on('connect_error', (error) => {
        term.writeln(`\r\n\x1b[31mSocket.IO Connection Error: ${error.message}\x1b[0m`);
        console.error(`[TerminalView ${sessionId}] Socket.IO connection error:`, error);
      });

      term.onData((data) => {
        console.log(`[TerminalView ${sessionId}] Data from xterm:`, data);
        if (socketRef.current && socketRef.current.connected) {
          const payload = { input: data, sessionId: sessionId };
          // CHANGED EVENT NAME HERE:
          console.log(`[TerminalView ${sessionId}] Emitting 'terminalInput' with payload:`, payload); 
          socketRef.current.emit('terminalInput', payload, (ack) => { // CHANGED EVENT NAME
            if (ack && ack.status === 'ok') {
              console.log(`[TerminalView ${sessionId}] Backend ACKNOWLEDGED terminalInput:`, ack);
            } else {
              console.error(`[TerminalView ${sessionId}] Backend DID NOT acknowledge terminalInput or error:`, ack);
              term.writeln(`\r\n\x1b[31m[Client: Error sending input to backend: ${ack?.message || 'No acknowledgement'}]\x1b[0m`);
            }
          });
        } else {
          console.warn(`[TerminalView ${sessionId}] Socket not connected, dropping input: ${data}`);
          term.writeln('\r\n\x1b[31m[Client: Not connected to server. Cannot send input.]\x1b[0m');
        }
      });

      window.addEventListener('resize', sendResize);
    }

    return () => {
      console.log(`[TerminalView ${sessionId}] Cleaning up component...`);
      window.removeEventListener('resize', sendResize);
      if (socketRef.current) {
        console.log(`[TerminalView ${sessionId}] Disconnecting socket on unmount.`);
        socketRef.current.disconnect();
        socketRef.current = null;
      }
      if (xtermInstanceRef.current) {
        xtermInstanceRef.current.dispose();
        xtermInstanceRef.current = null;
      }
      if (fitAddonRef.current) {
        fitAddonRef.current.dispose();
        fitAddonRef.current = null;
      }
    };
  }, [sessionId, websocketPath, sendResize, onCloseTerminal]);

  return <div ref={termContainerRef} className="terminal-container" style={{ height: '500px' }} />;
}

TerminalView.propTypes = {
  sessionId: PropTypes.string.isRequired,
  websocketPath: PropTypes.string.isRequired,
  onCloseTerminal: PropTypes.func.isRequired,
};

export default memo(TerminalView);
