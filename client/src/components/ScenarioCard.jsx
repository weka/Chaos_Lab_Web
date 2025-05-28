// client/src/components/ScenarioCard.jsx
import { useState, useCallback } from 'react';
import PropTypes from 'prop-types';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import './ScenarioCard.module.css'; // Using this based on your file list - adjust if wrong

// Ensure VITE_APP_BASE_URL is available, defaulting if not
const API_BASE_URL = import.meta.env.VITE_APP_BASE_URL || 'http://localhost:5000';

function ScenarioCard({ label, repo, onStartScenario }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleStartClick = useCallback(async () => {
    setLoading(true);
    setError(null);
    console.log(`Starting scenario: ${repo}`); // For debugging
    try {
      const response = await fetch(`${API_BASE_URL}/api/scenarios`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo }),
      });

      console.log(`Response status from /api/scenarios: ${response.status}`); // For debugging

      if (!response.ok) {
        let errorData;
        try {
          errorData = await response.json();
        } catch (e) {
          // If response is not JSON, use the status text
          throw new Error(`HTTP error! Status: ${response.status} - ${response.statusText}`);
        }
        throw new Error(errorData.error || `HTTP error! Status: ${response.status}`);
      }

      const data = await response.json();
      console.log('Scenario initialized by backend:', data); // For debugging

      if (data.sessionId && data.websocketPath) {
        onStartScenario(repo, data.sessionId, data.websocketPath);
      } else {
        console.error("Server response missing session ID or WebSocket path.", data);
        throw new Error("Server response missing session ID or WebSocket path.");
      }
    } catch (err) {
      console.error("Failed to start scenario:", err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [repo, onStartScenario]);

  return (
    <div className="weka-scenario-card"> {/* Ensure this class matches your CSS */}
      <h3>{label}</h3>
      {loading ? (
        <div className="weka-scenario-card-loading"> {/* Ensure this class matches your CSS */}
          <FontAwesomeIcon icon="fa-solid fa-circle-notch" spin size="2x" />
          <p>Preparing scenario...</p>
        </div>
      ) : (
        <button className="weka-scenario-card-button" onClick={handleStartClick}> {/* Ensure this class matches your CSS */}
          Start Scenario
        </button>
      )}
      {error && <p style={{ color: 'red', marginTop: '0.5em' }}>Error: {error}</p>}
    </div>
  );
}

ScenarioCard.propTypes = {
  label: PropTypes.string.isRequired,
  repo: PropTypes.string.isRequired,
  onStartScenario: PropTypes.func.isRequired,
};

export default ScenarioCard;
