import React from 'react';
import './SettingsComponent.css';

function SettingsComponent({ showSettings, yamlConfig, handleYamlConfigKeyChange }) {
    return (
        <div className={`settings-content ${showSettings ? 'visible' : 'hidden'}`}>
            <label htmlFor="yamlConfig">Config:</label>
            <textarea
                id="yamlConfig"
                rows="30"
                className="input-field"
                value={yamlConfig}
                onChange={(e) => handleYamlConfigKeyChange(e.target.value)}
            />
        </div>
    );
}

export { SettingsComponent };