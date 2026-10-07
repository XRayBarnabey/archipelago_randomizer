import { useEffect, useState, type FormEvent } from 'react'
import { api, getToken, setToken, UNAUTHORIZED_EVENT, type AdminSession } from '../api'
import { Button, ErrorBanner } from '../components/ui'
import AdminPage from './AdminPage'

const errorMessage = (e: unknown) => (e instanceof Error ? e.message : 'Erreur inconnue')
const inputClass = 'w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm'

function LoginForm({ onLogin }: { onLogin: (s: AdminSession) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const s = await api.login(username, password)
      setToken(s.token)
      onLogin(s)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-sm space-y-3">
      <h2 className="text-lg font-semibold">Administration</h2>
      <ErrorBanner message={error} />
      <label className="block text-sm">
        Identifiant
        <input className={inputClass} value={username} autoComplete="username" onChange={(e) => setUsername(e.target.value)} />
      </label>
      <label className="block text-sm">
        Mot de passe
        <input
          className={inputClass}
          type="password"
          value={password}
          autoComplete="current-password"
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <Button type="submit" disabled={busy || !username || !password}>
        Se connecter
      </Button>
    </form>
  )
}

function PasswordForm({ onChanged }: { onChanged: (s: AdminSession) => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [username, setUsername] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setDone(false)
    if (next !== confirm) {
      setError('La confirmation ne correspond pas au nouveau mot de passe.')
      return
    }
    try {
      const s = await api.changePassword(current, next, confirm, username.trim() || undefined)
      setToken(s.token)
      onChanged(s)
      setCurrent('')
      setNext('')
      setConfirm('')
      setUsername('')
      setDone(true)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <section>
      <h2 className="mb-2 text-lg font-semibold">Changer le mot de passe</h2>
      <form onSubmit={submit} className="max-w-sm space-y-3">
        <ErrorBanner message={error} />
        {done && <p className="text-sm text-emerald-400">Identifiants mis à jour.</p>}
        <label className="block text-sm">
          Mot de passe actuel
          <input className={inputClass} type="password" value={current} autoComplete="current-password" onChange={(e) => setCurrent(e.target.value)} />
        </label>
        <label className="block text-sm">
          Nouvel identifiant (optionnel)
          <input className={inputClass} value={username} autoComplete="username" onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="block text-sm">
          Nouveau mot de passe
          <input className={inputClass} type="password" value={next} autoComplete="new-password" onChange={(e) => setNext(e.target.value)} />
        </label>
        <label className="block text-sm">
          Confirmation
          <input className={inputClass} type="password" value={confirm} autoComplete="new-password" onChange={(e) => setConfirm(e.target.value)} />
        </label>
        <Button type="submit" disabled={!current || !next || !confirm}>
          Changer le mot de passe
        </Button>
      </form>
    </section>
  )
}

export default function AdminGate() {
  const [session, setSession] = useState<AdminSession | null>(null)
  const [checking, setChecking] = useState(!!getToken())

  useEffect(() => {
    if (!getToken()) return
    api
      .session()
      .then(setSession)
      .catch(() => setToken(null))
      .finally(() => setChecking(false))
  }, [])

  useEffect(() => {
    const onUnauthorized = () => setSession(null)
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [])

  const logout = async () => {
    await api.logout().catch(() => undefined)
    setToken(null)
    setSession(null)
  }

  if (checking) return <p className="text-sm text-slate-400">Chargement…</p>
  if (!session) return <LoginForm onLogin={setSession} />

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-400">Connecté en tant que {session.username}</span>
        <Button onClick={logout}>Se déconnecter</Button>
      </div>
      {session.default_credentials && (
        <div className="rounded border border-amber-600 bg-amber-950 p-3 text-sm text-amber-200">
          Les identifiants par défaut (admin / admin) sont toujours actifs : changez le mot de passe ci-dessous.
        </div>
      )}
      <AdminPage />
      <PasswordForm onChanged={setSession} />
    </div>
  )
}
