import { useEffect, useState } from 'react'
import { LOGO_CHANGED_EVENT } from './api'
import AdminGate from './pages/AdminGate'
import PickerPage from './pages/PickerPage'

type LogoSrc = 'api' | 'static' | 'none'

function Logo({ onClick }: { onClick: () => void }) {
  const [src, setSrc] = useState<LogoSrc>('api')
  const [version, setVersion] = useState(0)
  useEffect(() => {
    const reload = () => {
      setSrc('api')
      setVersion((v) => v + 1)
    }
    window.addEventListener(LOGO_CHANGED_EVENT, reload)
    return () => window.removeEventListener(LOGO_CHANGED_EVENT, reload)
  }, [])
  const url = src === 'api' ? `/api/logo?v=${version}` : '/logo.png'
  return (
    <a
      href="/"
      onClick={(e) => {
        e.preventDefault()
        onClick()
      }}
      className="flex items-center gap-3"
    >
      {src !== 'none' && (
        <img
          src={url}
          alt="Logo"
          className="max-h-10 object-contain"
          onError={() => setSrc(src === 'api' ? 'static' : 'none')}
        />
      )}
      <h1 className={src === 'none' ? 'text-2xl font-bold' : 'sr-only'}>Steam × Archipelago Game Picker</h1>
    </a>
  )
}

export default function App() {
  const [tab, setTab] = useState<'picker' | 'admin'>('picker')
  const tabClass = (t: string) =>
    `rounded px-4 py-2 text-sm font-medium ${tab === t ? 'bg-indigo-600' : 'bg-slate-800 hover:bg-slate-700'}`
  return (
    <div className="mx-auto max-w-6xl p-4">
      <header className="mb-6 flex items-center justify-between">
        <Logo onClick={() => setTab('picker')} />
        <nav className="flex gap-2">
          <button className={tabClass('picker')} onClick={() => setTab('picker')}>
            Tirage
          </button>
          <button className={tabClass('admin')} onClick={() => setTab('admin')}>
            Administration
          </button>
        </nav>
      </header>
      {tab === 'picker' ? <PickerPage /> : <AdminGate />}
    </div>
  )
}
