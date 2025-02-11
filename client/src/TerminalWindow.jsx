import React, { useEffect, useRef } from 'react';
import { Terminal } from 'xterm';
import 'xterm/css/xterm.css';
import io from 'socket.io-client';

const TerminalWindow = () => {
  const terminalRef = useRef(null);
  const term = useRef(null);
  const socketRef = useRef(null);

  useEffect(() => {
    // Initialize the terminal
    term.current = new Terminal({
      cols: 80,
      rows: 24,
      cursorBlink: true,
    });
    term.current.open(terminalRef.current);
    term.current.write('Connecting...\r\n');

    // Connect directly to the /terminal namespace
    socketRef.current = io(import.meta.env.VITE_APP_BASE_URL + '/terminal', {
      transports: ['websocket'],
    });

    socketRef.current.on('connect', () => {
      term.current.write('\r\nConnected to backend SSH.\r\n');
    });

    // Listen for output from the server and write it into the terminal
    socketRef.current.on('output', (data) => {
      term.current.write(data);
    });

    // When the terminal receives data from the user, send it to the server
    term.current.onData((data) => {
      socketRef.current.emit('input', data);
    });

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
      term.current.dispose();
    };
  }, []);

  return (
    <div style={{ height: '100%', width: '100%' }} ref={terminalRef} />
  );
};

export default TerminalWindow;

