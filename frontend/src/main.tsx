import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import MermaidRegressionPage from './MermaidRegressionPage'
import './styles.css'

const Root = new URLSearchParams(window.location.search).has('mermaid-regression') ? MermaidRegressionPage : App

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
