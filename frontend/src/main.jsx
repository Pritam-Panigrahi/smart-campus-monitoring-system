import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { MonitoringProvider } from './context/MonitoringContext'
import { ThemeProvider } from './context/ThemeContext'
import './index.css'
import 'leaflet/dist/leaflet.css'

createRoot(document.getElementById('root')).render(<StrictMode><ThemeProvider><MonitoringProvider><BrowserRouter><App /></BrowserRouter></MonitoringProvider></ThemeProvider></StrictMode>)
