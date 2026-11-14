import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { DashboardPage } from './pages/DashboardPage'
import { WaterTanksPage } from './pages/WaterTanksPage'
import { WasteBinsPage } from './pages/WasteBinsPage'
import { AqiMonitoringPage } from './pages/AqiMonitoringPage'
import { DataManagementPage } from './pages/DataManagementPage'
import { SettingsPage } from './pages/SettingsPage'

export default function App() {
  return <Routes><Route element={<AppShell />}><Route index element={<DashboardPage />} /><Route path="water-tanks" element={<WaterTanksPage />} /><Route path="waste-bins" element={<WasteBinsPage />} /><Route path="aqi-monitoring" element={<AqiMonitoringPage />} /><Route path="data-management" element={<DataManagementPage />} /><Route path="settings" element={<SettingsPage />} /><Route path="*" element={<Navigate to="/" replace />} /></Route></Routes>
}
