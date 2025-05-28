import { useState } from 'react';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import { Header, ScenarioCard, ScenarioContainer } from './components'; // Assuming these are fine
import TerminalView from './components/TerminalView'; // New import
import './App.css';

const theme = createTheme({
  // Your theme overrides
  components: {
    MuiFormLabel: { styleOverrides: { root: { color: 'var(--weka-purple)', "&.Mui-focused": { color: 'var(--weka-purple)' } } } },
    MuiFormHelperText: { styleOverrides: { root: { color: 'var(--weka-purple)' } } },
    MuiTextField: { styleOverrides: { root: { "& .MuiOutlinedInput-root": { backgroundColor: 'var(--primary-bg-color)', color: 'var(--weka-light-gray)', "&.Mui-focused": { "& .MuiOutlinedInput-notchedOutline": { borderColor: "var(--weka-purple)" } }, "& .MuiInputLabel-outlined": { color: 'var(--weka-purple)' } } } } }
  }
});

function App() {
  const [terminalSession, setTerminalSession] = useState(null); // { sessionId, websocketPath, repoName }

  const handleStartScenario = (repoName, sessionId, websocketPath) => {
    setTerminalSession({ repoName, sessionId, websocketPath });
  };

  const handleCloseTerminal = () => {
    setTerminalSession(null);
    // Here you might want to send a message to the backend to clean up the session/terraform
  };

  return (
    <ThemeProvider theme={theme}>
      <div>
        <Header />

        {terminalSession ? (
          <div>
            <h2>Terminal for {terminalSession.repoName} (Session: {terminalSession.sessionId})</h2>
            <TerminalView
              sessionId={terminalSession.sessionId}
              websocketPath={terminalSession.websocketPath}
            />
            <button onClick={handleCloseTerminal} style={{ marginTop: '1rem' }}>Close Terminal</button>
          </div>
        ) : (
          <ScenarioContainer>
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
              label="Setup Weka (Echo Test)" // Renamed for clarity in Phase 1
              repo="setup-weka" // This will use the echo terminal
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
