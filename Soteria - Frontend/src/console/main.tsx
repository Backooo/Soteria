import React from 'react';
import ReactDOM from 'react-dom/client';
import '../styles/tokens.css';
import { DevConsole } from './DevConsole';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <DevConsole />
  </React.StrictMode>
);
