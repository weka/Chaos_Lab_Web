import React from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { createTheme, ThemeProvider } from '@mui/material/styles'
import {
  Header,
  ScenarioCard,
  ScenarioContainer,
} from './components'
import TerminalWindow from './TerminalWindow'
import './App.css'

const theme = createTheme({
  components: {
    MuiFormLabel: {
      styleOverrides: {
        root: {
          color: 'var(--weka-purple)',
          "&.Mui-focused": {
            color: 'var(--weka-purple)',
          },
        },
      },
    },
    MuiFormHelperText: {
      styleOverrides: {
        root: {
          color: 'var(--weka-purple)',
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          "& .MuiOutlinedInput-root": {
            backgroundColor: 'var(--primary-bg-color)',
            color: 'var(--weka-light-gray)',
            "&.Mui-focused": {
              "& .MuiOutlinedInput-notchedOutline": {
                borderColor: "var(--weka-purple)",
              },
            },
            "& .MuiInputLabel-outlined": {
              color: 'var(--weka-purple)',
            },
          },
        },
      },
    },
  },
})

function MainPage() {
  return (
    <div>
      <Header />
      <ScenarioContainer>
        <ScenarioCard label="Weka Fully Installed" repo="weka-fully-installed" />
        <ScenarioCard label="Weka Agent Failure" repo="weka-agent-failure" />
        <ScenarioCard label="Dual Backend Failure" repo="dual-backend-failure" />
        <ScenarioCard label="Drive 0 Error" repo="drives0-error" />
        <ScenarioCard label="Setup Weka" repo="setup-weka" />
        <ScenarioCard label="Client Scenarios" repo="client-scenarios" />
      </ScenarioContainer>
    </div>
  )
}

function App() {
  return (
    <ThemeProvider theme={theme}>
      <Router>
        <Routes>
          <Route path="/" element={<MainPage />} />
          <Route path="/terminal" element={<TerminalWindow />} />
        </Routes>
      </Router>
    </ThemeProvider>
  )
}

export default App

