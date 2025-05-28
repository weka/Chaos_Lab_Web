// client/src/components/TerminalView.jsx
import React, { useEffect, useRef, useCallback, memo } from 'react';
import PropTypes from 'prop-types';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { WebLinksAddon } from 'xterm-addon-web-links';
import { io } from 'socket.io-client';
import 'xterm/css/xterm.css';
import './TerminalView.css';

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
        socketRef.current.emit('resize', {
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
    let webLinksAddon;
    let socket;

    if (termContainerRef.current && !xtermInstanceRef.current && sessionId && websocketPath) {
      console.log(`[TerminalView ${sessionId}] Initializing... Path: ${websocketPath}`);

      term = new Terminal({
        cursorBlink: true,
        convertEol: true, // This handles line endings
        rows: 24,
        cols: 80,
        fontSize: 15,
        fontFamily: '"Fira Code", "JetBrains Mono", "DejaVu Sans Mono", Consolas, "Liberation Mono", Menlo, Courier, monospace',
        theme: {
          background: '#282828',
          foreground: '#ebdbb2',
          cursor: '#fe8019',
          cursorAccent: '#3c3836',
          selectionBackground: 'rgba(146, 131, 116, 0.5)',
          black: '#282828',
          brightBlack: '#928374',
          red: '#cc241d',
          brightRed: '#fb4934',
          green: '#98971a',
          brightGreen: '#b8bb26',
          yellow: '#d79921',
          brightYellow: '#fabd2f',
          blue: '#458588',
          brightBlue: '#83a598',
          magenta: '#b16286',
          brightMagenta: '#d3869b',
          cyan: '#689d6a',
          brightCyan: '#8ec07c',
          white: '#a89984',
          brightWhite: '#ebdbb2',
        },
        allowProposedApi: true,
        scrollback: 2000,
        // windowsMode: os.platform() === 'win32', // REMOVED THIS LINE
      });
      xtermInstanceRef.current = term;

      fitAddon = new FitAddon();
      fitAddonRef.current = fitAddon;
      term.loadAddon(fitAddon);

      webLinksAddon = new WebLinksAddon();
      term.loadAddon(webLinksAddon);

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

      socket.on('pty-output', (data) => {
        if (data && typeof data.output === 'string') {
          term.write(data.output);
        }
      });
      
      socket.on('disconnect', (reason) => {
        const msg = `\r\n\x1b[31mSocket.IO Disconnected: ${reason}. SID was: ${socket?.id || 'N/A'}\x1b[0m`;
        if (term && term.element) term.writeln(msg);
        console.error(`[TerminalView ${sessionId}] Socket.IO Disconnected: ${reason}. Previous SID: ${socket?.id || 'N/A'}`);
      });

      socket.on('connect_error', (error) => {
        const errorMsg = `\r\n\x1b[31mSocket.IO Connection Error: ${error.message}\x1b[0m`;
        if (term && term.element) term.writeln(errorMsg);
        console.error(`[TerminalView ${sessionId}] Socket.IO connection error:`, error);
      });

      term.onData((data) => {
        // console.log(`[TerminalView ${sessionId}] Data from xterm:`, data);
        if (socketRef.current && socketRef.current.connected) {
          const payload = { input: data, sessionId: sessionId };
          // console.log(`[TerminalView ${sessionId}] Emitting 'terminalInput' with payload:`, payload);
          socketRef.current.emit('terminalInput', payload, (ack) => {
            if (ack && ack.status === 'ok') {
              // console.log(`[TerminalView ${sessionId}] Backend ACKNOWLEDGED terminalInput:`, ack);
            } else {
              console.error(`[TerminalView ${sessionId}] Backend DID NOT acknowledge terminalInput or error:`, ack);
              if (term && term.element) term.writeln(`\r\n\x1b[31m[Client: Error sending input: ${ack?.message || 'No ack'}]\x1b[0m`);
            }
          });
        } else {
          console.warn(`[TerminalView ${sessionId}] Socket not connected, dropping input: ${data}`);
          if (term && term.element) term.writeln('\r\n\x1b[31m[Client: Not connected. Cannot send input.]\x1b[0m');
        }
      });

      window.addEventListener('resize', sendResize);
    }

    return () => {
      console.log(`[TerminalView ${sessionId}] Cleaning up component...`);
      window.removeEventListener('resize', sendResize);
      if (socketRef.current) {
        console.log(`[TerminalView ${sessionId}] Disconnecting socket on unmount.`);
        socketRef.current.emit('disconnect_request', {sessionId: sessionId});
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

  return <div className="terminal-container-wrapper">
      <div ref={termContainerRef} className="terminal-instance" />
    </div>;
}

TerminalView.propTypes = {
  sessionId: PropTypes.string.isRequired,
  websocketPath: PropTypes.string.isRequired,
  onCloseTerminal: PropTypes.func.isRequired,
};

export default memo(TerminalView);
