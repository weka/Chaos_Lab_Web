// --- START client/src/components/ScenarioCard.jsx ---
import React, { useState, useCallback } from 'react';
import PropTypes from 'prop-types';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import './ScenarioCard.module.css'; // Or your relevant CSS import

const API_BASE_URL = import.meta.env.VITE_APP_BASE_URL || 'http://localhost:5000';

const DEFAULT_GUIDE_URL = "https://www.notion.so/wekaio/CEL-All-Info-Page-12930b0d101c80f8bdc0e188ea994709";

const SCENARIO_SPECIFIC_GUIDE_URLS = {
  "setup-weka": "https://www.notion.so/wekaio/Setup-Weka-a3fce840985a4bb9b24ba521924c671c",
  "weka-fully-installed": "https://www.notion.so/wekaio/Weka-Fully-Installed-588a732407e1490999d7a293967f734f",
  "TA-Tool": "https://www.notion.so/wekaio/TA-Tool-Testing-1fa30b0d101c80d88063e6518b63d173"
};

function ScenarioCard({ label, repo, onStartScenario }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleStartClick = useCallback(async () => {
    setLoading(true);
    setError(null);
    console.log(`Starting scenario: ${repo}`);

    const guideUrl = SCENARIO_SPECIFIC_GUIDE_URLS[repo] || DEFAULT_GUIDE_URL;
    window.open(guideUrl, '_blank', 'noopener,noreferrer');
    console.log(`Opened guide: ${guideUrl}`);

    try {
      const response = await fetch(`${API_BASE_URL}/api/scenarios`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo }),
      });

      console.log(`Response status from /api/scenarios: ${response.status}`);
      const responseData = await response.json();

      if (!response.ok) {
        const errorMessage = responseData.error || responseData.message || `HTTP error! Status: ${response.status}`;
        console.error("Failed to start scenario (response not ok):", errorMessage, responseData);
        throw new Error(errorMessage);
      }

      // MODIFIED: Check for endTime and pass it to onStartScenario
      if (responseData.sessionId && responseData.websocketPath && typeof responseData.endTime === 'number') {
        console.log('Scenario initialized by backend:', responseData);
        // Pass all data including initialEndTime (which is responseData.endTime)
        onStartScenario(repo, responseData.sessionId, responseData.websocketPath, responseData.endTime);
      } else {
        console.error("Server response missing session ID, WebSocket path, or valid endTime.", responseData);
        throw new Error("Server response missing critical data (sessionId, websocketPath, or endTime).");
      }
    } catch (err) {
      console.error("Error in handleStartClick:", err);
      setError(err.message || "An unknown error occurred.");
    } finally {
      setLoading(false);
    }
  }, [repo, onStartScenario]);

  return (
    <div className="weka-scenario-card">
      <h3>{label}</h3>
      {loading ? (
        <div className="weka-scenario-card-loading">
          <FontAwesomeIcon icon="fa-solid fa-circle-notch" spin size="2x" />
          <p>Preparing scenario...May take 2-5 minutes</p>
        </div>
      ) : (
        <button className="weka-scenario-card-button" onClick={handleStartClick}>
          Start Scenario & Open Guide
        </button>
      )}
      {error && <p style={{ color: 'red', marginTop: '0.5em' }}>Error: {error}</p>}
    </div>
  );
}

ScenarioCard.propTypes = {
  label: PropTypes.string.isRequired,
  repo: PropTypes.string.isRequired,
  // MODIFIED: onStartScenario now expects (repoName, sessionId, websocketPath, initialEndTimeEpoch)
  onStartScenario: PropTypes.func.isRequired, 
};

export default ScenarioCard;
// --- END client/src/components/ScenarioCard.jsx ---
