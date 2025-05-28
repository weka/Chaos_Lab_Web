// client/src/App.jsx
import { useState } from 'react';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import { Header, ScenarioCard, ScenarioContainer } from './components';
import TerminalView from './components/TerminalView';
import './App.css'; // Your main app styles
// You can add specific styles for .app-container or .terminal-view-wrapper here if needed

const theme = createTheme({
  // Your theme overrides
});

function App() {
  const [terminalSession, setTerminalSession] = useState(null);

  const handleStartScenario = (repoName, sessionId, websocketPath) => {
    setTerminalSession({ repoName, sessionId, websocketPath });
  };

  const handleCloseTerminalAndCleanup = () => {
    if (terminalSession && terminalSession.sessionId) {
      console.log(`App.jsx: Closing terminal for session ${terminalSession.sessionId}`);
    }
    setTerminalSession(null); // This will unmount TerminalView and trigger its cleanup
  };

  return (
    <ThemeProvider theme={theme}>
      {/* .app-container can be styled in App.css for overall page layout if desired */}
      <div className="app-container"> 
        <Header />

        {terminalSession ? (
          // .terminal-view-wrapper is styled by TerminalView.css for centering the terminal block
          <div className="terminal-view-wrapper"> 
            <h2 style={{ color: '#ebdbb2', fontFamily: 'var(--primary-font)' }}>
              Terminal for {terminalSession.repoName} (Session: {terminalSession.sessionId})
            </h2>
            <TerminalView
              sessionId={terminalSession.sessionId}
              websocketPath={terminalSession.websocketPath}
              onCloseTerminal={handleCloseTerminalAndCleanup} 
            />
            <button 
              onClick={handleCloseTerminalAndCleanup} 
              style={{ 
                marginTop: '1.5rem', 
                padding: '0.75em 1.5em', 
                backgroundColor: '#458588', // Gruvbox blue
                color: '#ebdbb2',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '0.9em'
              }}
            >
              Close Terminal & Destroy Scenario
            </button>
          </div>
        ) : (
          <ScenarioContainer>
            {/* ScenarioCards as before, passing onStartScenario */}
            <ScenarioCard
              label="Weka Fully Installed"
              repo="weka-fully-installed"
              onStartScenario={handleStartScenario}
            />
            <ScenarioCard
              label="Weka Agent Failure"
              repo="weka-agent-failure"
              onStartScenario={handleStartScenario}
            />
            <ScenarioCard
              label="Dual Backend Failure"
              repo="dual-backend-failure"
              onStartScenario={handleStartScenario}
            />
            <ScenarioCard
              label="Drive 0 Error"
              repo="drives0-error"
              onStartScenario={handleStartScenario}
            />
            <ScenarioCard
              label="Setup Weka (Terminal Test)"
              repo="setup-weka"
              onStartScenario={handleStartScenario}
            />
            <ScenarioCard
              label="Client Scenarios"
              repo="client-scenarios"
              onStartScenario={handleStartScenario}
            />
          </ScenarioContainer>
        )}
      </div>
    </ThemeProvider>
  );
}

export default App;
