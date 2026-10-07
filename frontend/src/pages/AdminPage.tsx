import { useCallback, useEffect, useState } from 'react'
import { api, LOGO_CHANGED_EVENT, type ApGame, type Mapping, type Source } from '../api'
import { Button, ErrorBanner, StatusBadge, formatDate } from '../components/ui'

const errorMessage = (e: unknown) => (e instanceof Error ? e.message : 'Erreur inconnue')

export default function AdminPage() {
  const [games, setGames] = useState<ApGame[]>([])
  const [mappings, setMappings] = useState<Mapping[]>([])
  const [sources, setSources] = useState<Source[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('')
  const [drafts, setDrafts] = useState<Record<number, string>>({})

  const load = useCallback(async () => {
    const [g, m, s] = await Promise.all([api.apGames(), api.mappings(), api.sources()])
    setGames(g)
    setMappings(m)
    setSources(s)
  }, [])

  useEffect(() => {
    load().catch((e) => setError(errorMessage(e)))
  }, [load])

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      await load()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const syncSources = () =>
    run(async () => {
      const res = await api.syncArchipelago()
      const failed = res.filter((r) => r.status === 'error')
      if (failed.length) setError(failed.map((f) => `${f.source} : ${f.error}`).join(' | '))
    })

  const [logoFile, setLogoFile] = useState<File | null>(null)
  const [logoVersion, setLogoVersion] = useState(0)
  const [logoVisible, setLogoVisible] = useState(true)
  const logoChanged = () => {
    setLogoVersion((v) => v + 1)
    setLogoVisible(true)
    window.dispatchEvent(new Event(LOGO_CHANGED_EVENT))
  }
  const uploadLogo = () =>
    run(async () => {
      if (!logoFile) return
      await api.uploadLogo(logoFile)
      setLogoFile(null)
      logoChanged()
    })
  const removeLogo = () =>
    run(async () => {
      await api.deleteLogo()
      logoChanged()
    })

  const unverified = mappings.filter((m) => !m.verified)
  const visible = games.filter((g) => g.name.toLowerCase().includes(filter.toLowerCase()))

  return (
    <div className="space-y-8">
      <ErrorBanner message={error} />

      <section>
        <h2 className="mb-2 text-lg font-semibold">Logo de l'application</h2>
        <div className="mb-2 flex h-20 items-center rounded bg-slate-950 p-2">
          {logoVisible ? (
            <img
              src={`/api/logo?v=${logoVersion}`}
              alt="Aperçu du logo"
              className="max-h-16 object-contain"
              onError={() => setLogoVisible(false)}
            />
          ) : (
            <span className="text-sm text-slate-400">Aucun logo personnalisé</span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="file"
            accept="image/png"
            className="text-sm"
            onChange={(e) => setLogoFile(e.target.files?.[0] ?? null)}
          />
          <Button disabled={busy || !logoFile} onClick={uploadLogo}>
            Téléverser
          </Button>
          <Button disabled={busy || !logoVisible} onClick={removeLogo}>
            Supprimer le logo
          </Button>
        </div>
        <p className="mt-1 text-xs text-slate-400">PNG transparent, 2 Mo maximum.</p>
      </section>

      <section>
        <div className="mb-2 flex items-center gap-3">
          <h2 className="text-lg font-semibold">Sources Archipelago</h2>
          <Button disabled={busy} onClick={syncSources}>
            Synchroniser les sources Archipelago
          </Button>
          <Button disabled={busy} onClick={() => run(api.autoMatch)}>
            Rapprochement par nom
          </Button>
        </div>
        <ul className="space-y-1 text-sm">
          {sources.map((s) => (
            <li key={s.id} className="rounded bg-slate-900 px-3 py-2">
              <b>{s.name}</b> <StatusBadge status={s.trust_level} /> — {s.last_sync_status ?? 'jamais synchronisée'} (
              {formatDate(s.last_synced_at)}){s.last_error && <span className="text-amber-300"> — {s.last_error}</span>}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Mappings à vérifier ({unverified.length})</h2>
        <ul className="space-y-1 text-sm">
          {unverified.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center gap-2 rounded bg-slate-900 px-3 py-2">
              <span className="flex-1">
                {m.archipelago_game_name} ↔ {m.steam_game_name ?? 'jeu Steam inconnu'} (#{m.steam_app_id}) — {m.mapping_type},
                confiance {Math.round(m.confidence * 100)} %
              </span>
              <Button disabled={busy} onClick={() => run(() => api.updateMapping(m.id, { verified: true }))}>
                Valider
              </Button>
              <Button className="bg-red-800 hover:bg-red-700" disabled={busy} onClick={() => run(() => api.deleteMapping(m.id))}>
                Supprimer
              </Button>
            </li>
          ))}
          {unverified.length === 0 && <li className="text-slate-400">Aucun mapping à vérifier.</li>}
        </ul>
      </section>

      <section>
        <div className="mb-2 flex items-center gap-3">
          <h2 className="text-lg font-semibold">Jeux Archipelago ({games.length})</h2>
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filtrer…"
            className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-slate-400">
              <tr>
                <th className="p-2">Nom</th>
                <th className="p-2">Source / statut</th>
                <th className="p-2">Mappings Steam</th>
                <th className="p-2">Nouveau Steam App ID</th>
                <th className="p-2">Actif</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((g) => (
                <tr key={g.id} className="border-t border-slate-800">
                  <td className="p-2">{g.name}</td>
                  <td className="p-2">
                    {g.source_name} <StatusBadge status={g.status} detail={g.detail_status} />
                  </td>
                  <td className="p-2">
                    {mappings
                      .filter((m) => m.archipelago_game_id === g.id)
                      .map((m) => (
                        <span key={m.id} className="mr-2 inline-flex items-center gap-1">
                          #{m.steam_app_id} {m.verified ? '✓' : '?'}
                          <button
                            className="text-red-400"
                            aria-label="Supprimer le mapping"
                            disabled={busy}
                            onClick={() => run(() => api.deleteMapping(m.id))}
                          >
                            ✕
                          </button>
                        </span>
                      ))}
                  </td>
                  <td className="p-2">
                    <form
                      className="flex gap-1"
                      onSubmit={(e) => {
                        e.preventDefault()
                        const id = Number(drafts[g.id])
                        if (Number.isInteger(id) && id > 0)
                          run(async () => {
                            await api.createMapping(g.id, id)
                            setDrafts((d) => ({ ...d, [g.id]: '' }))
                          })
                      }}
                    >
                      <input
                        inputMode="numeric"
                        value={drafts[g.id] ?? ''}
                        onChange={(e) => setDrafts((d) => ({ ...d, [g.id]: e.target.value }))}
                        className="w-28 rounded border border-slate-700 bg-slate-900 px-2 py-1"
                      />
                      <Button type="submit" disabled={busy}>
                        Lier
                      </Button>
                    </form>
                  </td>
                  <td className="p-2">
                    <input
                      type="checkbox"
                      checked={g.enabled}
                      disabled={busy}
                      onChange={(e) => run(() => api.setGameEnabled(g.id, e.target.checked))}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
