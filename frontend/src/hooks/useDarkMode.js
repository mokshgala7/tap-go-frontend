import { useEffect, useState } from 'react'

const STORAGE_KEY = 'tapgo_dark_mode'

// Same dark-mode mechanism Passenger already used: one class on <html>,
// backed by localStorage, so any page that renders can opt into it without
// a separate theme system. Home/Login/Register never use `.tapgo-dark`
// styling, so toggling it elsewhere never changes how those pages look.
export function useDarkMode() {
  const [dark, setDark] = useState(() => localStorage.getItem(STORAGE_KEY) === '1')

  useEffect(() => {
    document.documentElement.classList.toggle('tapgo-dark', dark)
    localStorage.setItem(STORAGE_KEY, dark ? '1' : '0')
  }, [dark])

  return [dark, setDark]
}
