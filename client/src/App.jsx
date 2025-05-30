// --- START client/src/App.jsx ---
import React, { useState, useCallback } from 'react'; // Added useCallback
import { createTheme, ThemeProvider } from '@mui/material/styles';
import { Header, ScenarioCard, ScenarioContainer } from './components';
import TerminalView from './components/TerminalView';
import TimerDisplay from './components/TimerDisplay'; // NEW: Import TimerDisplay
import './App.css';

const theme = createTheme({
  // Your theme overrides
});

const API_BASE_URL = import.meta.env.VITE_APP_BASE_URL || 'http://localhost:5000'; // For extend timer API call

function App() {
  const [terminalSession, setTerminalSession] = useState(null); // { repoName, sessionId, websocketPath }
  const [sessionEndTimeEpoch, setSessionEndTimeEpoch] = useState(null); // NEW: Store timer end time (Unix timestamp in seconds)
  const [isExtendingTimer, setIsExtendingTimer] = useState(false); // NEW: State for extend button

  // MODIFIED: handleStartScenario now accepts initialEndTimeEpoch
  const handleStartScenario = useCallback((repoName, sessionId, websocketPath, initialEndTimeEpoch) => {
    setTerminalSession({ repoName, sessionId, websocketPath });
    setSessionEndTimeEpoch(initialEndTimeEpoch); // NEW: Set the initial end time
    console.log(`App.jsx: Scenario started. Session ID: ${sessionId}, Initial End Time (Epoch): ${initialEndTimeEpoch}`);
  }, []); // Empty dependency array as it doesn't close over changing state/props

  const handleCloseTerminalAndCleanup = useCallback(() => {
    if (terminalSession && terminalSession.sessionId) {
      console.log(`App.jsx: Closing terminal for session ${terminalSession.sessionId}.`);
    }
    setTerminalSession(null);
    setSessionEndTimeEpoch(null); // NEW: Clear end time when terminal closes
  }, [terminalSession]); // Depends on terminalSession

  // NEW: Function to handle extending the timer
  const handleExtendTimer = async () => {
    if (!terminalSession || !terminalSession.sessionId) {
      console.warn("Extend timer called but no active terminal session.");
      return;
    }
    
    setIsExtendingTimer(true);
    console.log(`App.jsx: Attempting to extend timer for session ${terminalSession.sessionId}`);

    try {
      const response = await fetch(`${API_BASE_URL}/api/scenarios/${terminalSession.sessionId}/extend_timer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }, // Good practice, though this endpoint might not need a body
      });
      
      const data = await response.json();

      if (response.ok && data.newEndTime) {
        setSessionEndTimeEpoch(data.newEndTime); // Update with the new Unix timestamp from backend
        console.log(`App.jsx: Timer extended for ${terminalSession.sessionId}. New end time (Epoch): ${data.newEndTime}`);
      } else {
        const errorMsg = data.error || `Failed to extend timer (HTTP ${response.status})`;
        console.error("Failed to extend timer:", errorMsg, data);
        alert(`Error extending timer: ${errorMsg}`); // Notify user
      }
    } catch (error) {
      console.error("Error calling extend timer API:", error);
      alert('Network error while extending timer. Please check console.');
    } finally {
      setIsExtendingTimer(false);
    }
  };

  return (
    <ThemeProvider theme={theme}>
      <div className="app-container"> 
        <Header />

        {terminalSession ? (
          <div className="terminal-view-wrapper"> 
            <h2 style={{ color: '#ebdbb2', fontFamily: 'var(--primary-font)' }}>
              Terminal for {terminalSession.repoName} (Session: {terminalSession.sessionId})
            </h2>

            {/* NEW: Timer Display and Extend Button */}
            <div style={{ margin: '10px 0', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '20px' }}>
              {sessionEndTimeEpoch !== null && <TimerDisplay endTimeEpoch={sessionEndTimeEpoch} />}
              <button 
                onClick={handleExtendTimer}
                disabled={isExtendingTimer || sessionEndTimeEpoch === null} // Disable if no timer or already extending
                style={{ 
                  padding: '0.5em 1em', 
                  backgroundColor: (sessionEndTimeEpoch === null || isExtendingTimer) ? '#7c6f64' : '#8ec07c', // Gruvbox gray if disabled, green if active
                  color: '#282828', // Dark text on light button
                  border: 'none',
                  borderRadius: '4px',
                  cursor: (sessionEndTimeEpoch === null || isExtendingTimer) ? 'not-allowed' : 'pointer',
                  fontSize: '0.9em',
                  opacity: (sessionEndTimeEpoch === null || isExtendingTimer) ? 0.6 : 1,
                }}
              >
                {isExtendingTimer ? 'Extending...' : 'Extend Session (30 mins)'}
              </button>
            </div>

            <TerminalView
              key={terminalSession.sessionId}
              sessionId={terminalSession.sessionId}
              websocketPath={terminalSession.websocketPath}
              onCloseTerminal={handleCloseTerminalAndCleanup}
              isMaximized={false} 
              isFullscreen={false}
            />
            <button 
              onClick={handleCloseTerminalAndCleanup} 
              style={{ 
                marginTop: '1.5rem', 
                padding: '0.75em 1.5em', 
                backgroundColor: '#fb4934',
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
            {/* MODIFIED: ScenarioCards now pass initialEndTimeEpoch to handleStartScenario */}
            <ScenarioCard
              label="Weka Fully Installed" repo="weka-fully-installed"
              onStartScenario={handleStartScenario} />
            <ScenarioCard
              label="Secret Agent Man" repo="secret-agent-man"
              onStartScenario={handleStartScenario} />
            <ScenarioCard
              label="Dual Backend Failure" repo="dual-backend-failure"
              onStartScenario={handleStartScenario} />
            <ScenarioCard
              label="Drives'ing me crazy" repo="drives-ing-me-crazy"
              onStartScenario={handleStartScenario} />
            <ScenarioCard
              label="Setup Weka" repo="setup-weka"
              onStartScenario={handleStartScenario} />
            <ScenarioCard
              label="Client Chaos Showcase" repo="client-chaos-showcase"
              onStartScenario={handleStartScenario} />
            <ScenarioCard
              label="TA-Tool" repo="TA-Tool"
              onStartScenario={handleStartScenario} />
            <ScenarioCard
              label="Krazy-k8s" repo="krazy-k8s"
              onStartScenario={handleStartScenario} />
            <ScenarioCard
              label="CSI-Basic-Lab" repo="csi-basic-lab"
              onStartScenario={handleStartScenario} />
            <ScenarioCard
              label="It's All About that Trace" repo="its-all-about-that-trace"
              onStartScenario={handleStartScenario} />
            <ScenarioCard
              label="No Bucket Quorum" repo="no-bucket-quorum"
              onStartScenario={handleStartScenario} />
            <ScenarioCard
              label="Kubernetes+Weka" repo="kubernetes+weka"
              onStartScenario={handleStartScenario} />
          </ScenarioContainer>
        )}
      </div>
    </ThemeProvider>
  );
}

export default App;
// --- END client/src/App.jsx ---
