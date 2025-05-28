import React, { useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { io } from 'socket.io-client'; // Import socket.io-client
import 'xterm/css/xterm.css';
import './TerminalView.css'; // Optional: for custom styling

const API_BASE_URL = import.meta.env.VITE_APP_BASE_URL || 'http://localhost:5000';

function TerminalView({ sessionId, websocketPath }) {
  const termRef = useRef(null);
  const xtermInstance = useRef(null);
  const socketRef = useRef(null);
  const fitAddonRef = useRef(null);

  useEffect(() => {
    if (termRef.current && !xtermInstance.current && sessionId && websocketPath) {
      console.log(`TerminalView: Initializing for sessionId: ${sessionId}, websocketPath: ${websocketPath}`);

      const term = new Terminal({
        cursorBlink: true,
        convertEol: true, // Convert \n to \r\n for proper line feeds
        rows: 20, // Default rows
      });
      xtermInstance.current = term;

      const fitAddon = new FitAddon();
      fitAddonRef.current = fitAddon;
      term.loadAddon(fitAddon);

      term.open(termRef.current);
      fitAddon.fit(); // Fit to parent element size

      // Initialize Socket.IO connection
      // The path option for Socket.IO client usually defaults to /socket.io,
      // Flask-SocketIO uses this by default. The `websocketPath` here is the namespace.
      const socket = io(API_BASE_URL, {
        path: '/socket.io', // Standard Socket.IO path
        transports: ['websocket'], // Force WebSockets
      });
      socketRef.current = socket;

      socket.on('connect', () => {
        term.writeln('Connected to backend terminal session.');
        console.log(`TerminalView: Connected to Socket.IO, joining scenario ${sessionId}`);
        socket.emit('join_scenario', { sessionId: sessionId }); // Tell backend which scenario session to join
      });

      socket.on('disconnect', (reason) => {
        term.writeln(`\r\nDisconnected from backend: ${reason}`);
        console.log(`TerminalView: Disconnected from Socket.IO: ${reason}`);
      });

      socket.on('pty-output', (data) => {
        if (data && typeof data.output === 'string') {
          term.write(data.output);
        }
      });

      socket.on('connect_error', (error) => {
        term.writeln(`\r\nConnection Error: ${error.message}`);
        console.error('TerminalView: Socket.IO connection error:', error);
      });

      term.onData((data) => {
        if (socket.current && socket.current.connected) {
          socket.current.emit('pty-input', { input: data, sessionId: sessionId });
        }
      });

      const handleResize = () => {
        fitAddonRef.current?.fit();
      };
      window.addEventListener('resize', handleResize);

      return () => { // Cleanup
        console.log("TerminalView: Cleaning up...");
        window.removeEventListener('resize', handleResize);
        if (socketRef.current) {
          socketRef.current.disconnect();
          socketRef.current = null;
        }
        if (xtermInstance.current) {
          xtermInstance.current.dispose();
          xtermInstance.current = null;
        }
      };
    }
  }, [sessionId, websocketPath]); // Re-run if sessionId or websocketPath changes

  return <div ref={termRef} className="terminal-container" />;
}

TerminalView.propTypes = {
  sessionId: PropTypes.string.isRequired,
  websocketPath: PropTypes.string.isRequired,
};

export default TerminalView;
