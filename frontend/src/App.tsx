import { useState } from 'react'
import AdminGate from './pages/AdminGate'
import PickerPage from './pages/PickerPage'

export default function App() {
  const [tab, setTab] = useState<'picker' | 'admin'>('picker')
  const tabClass = (t: string) =>
    `rounded px-4 py-2 text-sm font-medium ${tab === t ? 'bg-indigo-600' : 'bg-slate-800 hover:bg-slate-700'}`
  return (
    <div className="mx-auto max-w-6xl p-4">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Steam × Archipelago Game Picker</h1>
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
