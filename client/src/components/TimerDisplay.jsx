// --- START client/src/components/TimerDisplay.jsx ---
import React, { useState, useEffect, useMemo } from 'react';
import PropTypes from 'prop-types';

function formatTime(totalSeconds) {
  if (isNaN(totalSeconds) || totalSeconds < 0) totalSeconds = 0;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60); // Ensure seconds are integer for display
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function TimerDisplay({ endTimeEpoch }) { // endTimeEpoch is a Unix timestamp in seconds
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const [isExpired, setIsExpired] = useState(false);

  useEffect(() => {
    // If endTimeEpoch is null or undefined, the timer is not active or has been cleared.
    if (endTimeEpoch === null || typeof endTimeEpoch === 'undefined') {
      setRemainingSeconds(0);
      setIsExpired(true); // Consider this 'not active' or 'expired'
      return;
    }

    let intervalId;

    const calculateRemaining = () => {
      const nowEpoch = Date.now() / 1000; // Current time in seconds
      const secondsLeft = endTimeEpoch - nowEpoch;
      
      if (secondsLeft <= 0) {
        setRemainingSeconds(0);
        setIsExpired(true);
        if (intervalId) clearInterval(intervalId); // Stop interval once expired
      } else {
        setRemainingSeconds(secondsLeft);
        setIsExpired(false);
      }
    };

    calculateRemaining(); // Initial calculation
    intervalId = setInterval(calculateRemaining, 1000); // Update every second

    // Cleanup function: clear the interval when the component unmounts or endTimeEpoch changes.
    return () => clearInterval(intervalId);
  }, [endTimeEpoch]); // Dependency array: re-run effect if endTimeEpoch changes

  const timerText = useMemo(() => {
    if (endTimeEpoch === null || typeof endTimeEpoch === 'undefined') {
      return "Session Time: Not Active";
    }
    if (isExpired) {
      return "Time Remaining: EXPIRED";
    }
    return `Time Remaining: ${formatTime(remainingSeconds)}`;
  }, [endTimeEpoch, isExpired, remainingSeconds]);

  const timerColor = useMemo(() => {
    if (endTimeEpoch === null || typeof endTimeEpoch === 'undefined' || isExpired) {
      return '#fb4934'; // Gruvbox red for expired/inactive
    }
    if (remainingSeconds < 5 * 60) { // Under 5 minutes warning
        return '#fabd2f'; // Gruvbox yellow
    }
    return '#b8bb26'; // Gruvbox green for normal time
  }, [endTimeEpoch, isExpired, remainingSeconds]);

  return (
    <span style={{ color: timerColor, fontFamily: 'var(--primary-font)', marginRight: '20px', fontWeight: 'bold' }}>
      {timerText}
    </span>
  );
}

TimerDisplay.propTypes = {
  // Unix timestamp in seconds, can be null or undefined if no timer is active.
  endTimeEpoch: PropTypes.number, 
};

export default React.memo(TimerDisplay); // Memoize for performance as it updates frequently
// --- END client/src/components/TimerDisplay.jsx ---
