import * as React from 'react'
import PropTypes from 'prop-types'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import TextField from '@mui/material/TextField'

// Add these imports:
import FormControl from '@mui/material/FormControl'
import InputLabel from '@mui/material/InputLabel'
import Select from '@mui/material/Select'
import MenuItem from '@mui/material/MenuItem'

import { addClasses } from '../utils'
import { useScenarioContext } from './context'
import Conditionally from './Conditionally'
import BackButton from './BackButton'

import styles from './ScenarioCard.module.css'

/**
 * @name ScenarioCard
 * @component
 *
 * @param {object} props
 * @param {string} props.label
 * @param {string} props.repo
 *
 * @returns {React.ReactNode}
 */

function ScenarioCard(props) {
  const {
    label,
    repo,
  } = props

  const [formValues, setFormValues] = React.useState({})

  const handleChange = React.useCallback(
    (event) => {
      const { name, value } = event.target

      setFormValues((values) => {
        return {
          ...values,
          [name]: value,
        }
      })
    },
    []
  )

  const {
    isSelected,
    handleSelect,
  } = useScenarioContext()

  const [isFetching, setIsFetching] = React.useState(false)
  const [downloadUrl, setDownloadUrl] = React.useState('')

  const handleSubmit = React.useCallback(
    (event) => {
      event.preventDefault()

      setIsFetching(true)

      const url = `${import.meta.env.VITE_APP_BASE_URL}/api/scenarios`

      const config = {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          repo,
          // form values
          backend_count: Number(formValues.backend_count),
          client_count: Number(formValues.client_count),
          expiration_hours: Number(formValues.expiration_hours),
          weka_version: formValues.weka_version,
        }),
      }

      fetch(url, config).then(
          (response) => { return response.json() }
        ).then(
          (data) => {
            if (data.download_url) {
              const downloadUrl = `${import.meta.env.VITE_APP_BASE_URL}${data.download_url}`

              setDownloadUrl(downloadUrl)
            }
          }
        ).catch(
          (error) => {
            if (import.meta.env.NODE_ENV === 'development') {
              console.error(error)
            }
          }
        ).finally(
          () => {
          setIsFetching(false)
        }
      )
    },
    [
      repo,
      formValues,
    ]
  )

  const isSelection = isSelected(repo)

  const containerClassNames = addClasses({
    [styles.card]: true,
    [styles.card_hidden]: isSelection === false,
    [styles.card_selected]: isSelection === true,
  })

  return (
    <div className={containerClassNames}>
      <h3>{label}</h3>

      <Conditionally when={isSelection}>
        <BackButton />
      </Conditionally>

      <Conditionally when={isSelection}>
        <TextField
          autoFocus={true}
          fullWidth={true}
          label="Weka Version"
          margin="normal"
          name="weka_version"
          onChange={handleChange}
          placeholder="4.2.15"
          size="small"
          value={formValues.weka_version}
        />

        <TextField
          fullWidth={true}
          helperText="(+1) for the Scenario Installer"
          label="Backend Count"
          margin="normal"
          name="backend_count"
          onChange={handleChange}
          placeholder="5"
          size="small"
          value={formValues.backend_count}
        />

        <TextField
          fullWidth={true}
          label="Client Count"
          margin="normal"
          name="client_count"
          onChange={handleChange}
          placeholder="1"
          size="small"
          value={formValues.client_count}
        />

        <TextField
          fullWidth={true}
          label="Expiration Time (Hours)"
          margin="normal"
          name="expiration_hours"
          onChange={handleChange}
          placeholder="4"
          size="small"
          value={formValues.expiration_hours}
        />
<FormControl fullWidth margin="normal" size="small" required>
  <InputLabel id="region-label">Region</InputLabel>
  <Select
    labelId="region-label"
    name="region"
    value={formValues.region || ''}
    onChange={handleChange}
    label="Region"
  >
    <MenuItem value="california">California</MenuItem>
    <MenuItem value="london">London</MenuItem>
    <MenuItem value="mumbai">Mumbai</MenuItem>
    <MenuItem value="sydney">Sydney</MenuItem>
    <MenuItem value="virginia">Virginia</MenuItem>
  </Select>
</FormControl>


      </Conditionally>

      <span className={styles.form_button}>
        <Conditionally
          when={!isFetching}
          otherwise={(
            <div className={styles.card_loading}>
              <FontAwesomeIcon icon="fa-solid fa-circle-notch" spin />
            </div>
          )}
        >
          <Conditionally
            when={!downloadUrl}
            otherwise={(
              <a
                className="weka-scenario-card-link"
                href={downloadUrl}
                target="_blank"
                rel="noreferrer"
              >
                Download
              </a>
            )}
          >
            <Conditionally
              when={!isSelection}
              otherwise={(
                <button
                  onClick={handleSubmit}
                  className={styles.card_button}
                  type="submit"
                >
                  Start
                </button>
              )}
            >
              <button
                className={styles.card_button}
                onClick={handleSelect}
                data-repo={repo}
                type="button"
              >
                Select Scenario
              </button>
            </Conditionally>
          </Conditionally>
        </Conditionally>
      </span>
    </div>
  )
}

ScenarioCard.propTypes = {
  label: PropTypes.string.isRequired,
  repo: PropTypes.string.isRequired,
}

export {
  ScenarioCard as default,
}
