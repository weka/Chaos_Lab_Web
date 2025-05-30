// client/src/components/TerminalView.jsx
import React, { useEffect, useRef, useCallback, memo } from 'react';
import PropTypes from 'prop-types';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { WebLinksAddon } from 'xterm-addon-web-links';
import { io } from 'socket.io-client';
import 'xterm/css/xterm.css';    // Imports CSS from node_modules
import './TerminalView.css';    // Imports CSS from the same directory (src/components/TerminalView.css)

const API_BASE_URL = import.meta.env.VITE_APP_BASE_URL || 'http://localhost:5000';

const MAXIMIZED_CLASS = 'terminal-instance-maximized';
const FULLSCREEN_CLASS = 'terminal-instance-fullscreen';

function TerminalView({ sessionId, websocketPath, onCloseTerminal, isMaximized, isFullscreen }) {
  const termContainerRef = useRef(null);
  const xtermInstanceRef = useRef(null);
  const socketRef = useRef(null);
  const fitAddonRef = useRef(null);

  const sendResizeToBackend = useCallback(() => {
    if (socketRef.current && socketRef.current.connected && xtermInstanceRef.current && fitAddonRef.current) {
      try {
        fitAddonRef.current.fit(); 
        const { cols, rows } = xtermInstanceRef.current;
        socketRef.current.emit('resize', {
          sessionId: sessionId,
          cols: cols,
          rows: rows,
        });
        console.log(`[TerminalView ${sessionId}] Sent resize to backend: ${cols}x${rows}`);
      } catch (e) {
        console.error(`[TerminalView ${sessionId}] Error during backend resize notification:`, e);
      }
    }
  }, [sessionId]);

  const handleResizeAndNotify = useCallback(() => {
    if (xtermInstanceRef.current && fitAddonRef.current) {
      try {
        fitAddonRef.current.fit();
        console.log(`[TerminalView ${sessionId}] Fit addon executed.`);
        sendResizeToBackend();
      } catch (e) {
        console.error(`[TerminalView ${sessionId}] Error during fit or notify:`, e)
      }
    }
  }, [sessionId, sendResizeToBackend]);

  useEffect(() => {
    let term;
    let fitAddonInstance; // Renamed to avoid conflict with addon class
    let webLinksAddonInstance;
    let socket;

    if (termContainerRef.current && !xtermInstanceRef.current && sessionId && websocketPath) {
      console.log(`[TerminalView ${sessionId}] Initializing... Path: ${websocketPath}`);

      term = new Terminal({
        cursorBlink: true,
        convertEol: true,
        rows: 24,
        cols: 80,
        fontSize: 15,
        fontFamily: '"Fira Code", "JetBrains Mono", "DejaVu Sans Mono", Consolas, "Liberation Mono", Menlo, Courier, monospace',
        theme: {
          background: '#282828', foreground: '#ebdbb2', cursor: '#fe8019',
          cursorAccent: '#3c3836', selectionBackground: 'rgba(146, 131, 116, 0.5)',
          black: '#282828', brightBlack: '#928374', red: '#cc241d', brightRed: '#fb4934',
          green: '#98971a', brightGreen: '#b8bb26', yellow: '#d79921', brightYellow: '#fabd2f',
          blue: '#458588', brightBlue: '#83a598', magenta: '#b16286', brightMagenta: '#d3869b',
          cyan: '#689d6a', brightCyan: '#8ec07c', white: '#a89984', brightWhite: '#ebdbb2',
        },
        allowProposedApi: true,
        scrollback: 2000,
      });
      xtermInstanceRef.current = term;

      fitAddonInstance = new FitAddon();
      fitAddonRef.current = fitAddonInstance; // Store the instance
      term.loadAddon(fitAddonInstance);

      webLinksAddonInstance = new WebLinksAddon();
      term.loadAddon(webLinksAddonInstance);

      term.open(termContainerRef.current);
      try {
        handleResizeAndNotify();
      } catch(e) {
        console.error(`[TerminalView ${sessionId}] Initial fit/notify failed:`, e);
      }
      term.focus();

      const fullWebsocketUrl = `${API_BASE_URL}${websocketPath}`;
      console.log(`[TerminalView ${sessionId}] Attempting Socket.IO connection to: ${fullWebsocketUrl}`);
      
      socket = io(fullWebsocketUrl, {
        path: '/socket.io', // Ensure this matches your server's Socket.IO path
        transports: ['websocket'],
        reconnectionAttempts: 3,
      });
      socketRef.current = socket;

      socket.on('connect', () => {
        term.writeln('\r\n\x1b[32mSocket.IO: Connected to backend session.\x1b[0m');
        console.log(`[TerminalView ${sessionId}] Socket.IO Connected. SID: ${socket.id}. Emitting 'join_scenario'.`);
        socket.emit('join_scenario', { sessionId: sessionId });
        setTimeout(handleResizeAndNotify, 150);
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
        if (socketRef.current && socketRef.current.connected) {
          const payload = { input: data, sessionId: sessionId };
          socketRef.current.emit('terminalInput', payload, (ack) => {
            if (ack && ack.status === 'ok') {
              // Acknowledged
            } else {
              console.error(`[TerminalView ${sessionId}] Backend NACK/error for terminalInput:`, ack);
              if (term && term.element) term.writeln(`\r\n\x1b[31m[Client: Error sending input: ${ack?.message || 'No ack'}]\x1b[0m`);
            }
          });
        } else {
          console.warn(`[TerminalView ${sessionId}] Socket not connected, dropping input: ${data}`);
          if (term && term.element) term.writeln('\r\n\x1b[31m[Client: Not connected. Cannot send input.]\x1b[0m');
        }
      });

      window.addEventListener('resize', handleResizeAndNotify);
    }

    return () => {
      console.log(`[TerminalView ${sessionId}] Cleaning up component...`);
      window.removeEventListener('resize', handleResizeAndNotify);
      if (socketRef.current) {
        console.log(`[TerminalView ${sessionId}] Disconnecting socket on unmount.`);
        socketRef.current.emit('disconnect_request', {sessionId: sessionId}); // Notify backend
        socketRef.current.disconnect();
        socketRef.current = null;
      }
      if (xtermInstanceRef.current) {
        xtermInstanceRef.current.dispose();
        xtermInstanceRef.current = null;
      }
      if (fitAddonRef.current) { // fitAddonRef stores the instance
        fitAddonRef.current.dispose();
        fitAddonRef.current = null;
      }
      // No need to dispose webLinksAddonInstance explicitly if it's just loaded
    };
  }, [sessionId, websocketPath, onCloseTerminal, handleResizeAndNotify]); 

  useEffect(() => {
    const container = termContainerRef.current;
    if (container) {
      if (isFullscreen) {
        container.classList.add(FULLSCREEN_CLASS);
        container.classList.remove(MAXIMIZED_CLASS);
      } else if (isMaximized) {
        container.classList.add(MAXIMIZED_CLASS);
        container.classList.remove(FULLSCREEN_CLASS);
      } else {
        container.classList.remove(MAXIMIZED_CLASS);
        container.classList.remove(FULLSCREEN_CLASS);
      }
      setTimeout(handleResizeAndNotify, 50); // Refit after class changes
    }
  }, [isMaximized, isFullscreen, handleResizeAndNotify]);

  return (
    // The parent .terminal-container-wrapper (from App.jsx) handles overall centering
    // This div IS the terminal instance that gets styled/resized.
    <div ref={termContainerRef} className="terminal-instance" />
  );
}

TerminalView.propTypes = {
  sessionId: PropTypes.string.isRequired,
  websocketPath: PropTypes.string.isRequired,
  onCloseTerminal: PropTypes.func.isRequired,
  isMaximized: PropTypes.bool.isRequired,
  isFullscreen: PropTypes.bool.isRequired,
  // onToggleMaximize and onToggleFullscreen are not directly called by TerminalView, but App.jsx passes them.
  // It's fine to keep them in propTypes if App.jsx is providing them.
};

export default memo(TerminalView);
