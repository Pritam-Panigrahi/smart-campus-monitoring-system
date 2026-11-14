import { createContext, useContext, useEffect, useMemo, useState } from 'react'
const ThemeContext = createContext(null); const KEY = 'gate-monitoring-theme'
export function ThemeProvider({ children }) { const [theme, setTheme] = useState(() => { const saved = localStorage.getItem(KEY); return saved === 'dark' || saved === 'light' ? saved : 'light' }); useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem(KEY, theme) }, [theme]); const value = useMemo(() => ({ theme, setTheme, toggleTheme: () => setTheme((current) => current === 'light' ? 'dark' : 'light') }), [theme]); return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider> }
// eslint-disable-next-line react-refresh/only-export-components
export function useTheme() { const context = useContext(ThemeContext); if (!context) throw new Error('useTheme must be used within ThemeProvider.'); return context }
