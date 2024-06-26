import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';
import RobodogLib from '../../robodoglib/dist/robodoglib.bundle.js';
console.log(RobodogLib)
const consoleService = new RobodogLib.ConsoleService()
if(consoleService){
  console.log('index bundle', consoleService)
}
const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

reportWebVitals();
