import { useCallback, useEffect, useState } from 'react'
import {
  api,
  ApiError,
  MAX_PLAYERS,
  type CommonGames,
  type DrawHistoryItem,
  type DrawResult,
  type Mode,
  type PerPlayerDrawResponse,
  type PlayerGames,
  type Player,
} from '../api'
import DrawResultCard from '../components/DrawResultCard'
import GameList from '../components/GameList'
import PlayerCard from '../components/PlayerCard'
import { Button, ErrorBanner, formatDate, StatusBadge } from '../components/ui'

const errorMessage = (e: unknown) => (e instanceof Error ? e.message : 'Erreur inconnue')

export default function PickerPage() {
  const [players, setPlayers] = useState<Player[]>([])
  const [selected, setSelected] = useState<number[]>([])
  const [input, setInput] = useState('')
  const [drawMode, setDrawMode] = useState<'per_player' | 'common'>('per_player')
  const [mode, setMode] = useState<Mode>('recommended')
  const [excludeDrawn, setExcludeDrawn] = useState(false)
  const [common, setCommon] = useState<CommonGames | null>(null)
  const [playerGames, setPlayerGames] = useState<PlayerGames | null>(null)
  const [result, setResult] = useState<DrawResult | null>(null)
  const [perPlayerResult, setPerPlayerResult] = useState<PerPlayerDrawResponse | null>(null)
  const [history, setHistory] = useState<DrawHistoryItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [noGames, setNoGames] = useState(false)
  const [busy, setBusy] = useState(false)

  const guard = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const loadPlayers = useCallback(async () => {
    const list = await api.players()
    setPlayers(list)
    setSelected((cur) => cur.filter((id) => list.some((p) => p.id === id)))
  }, [])
  const loadHistory = useCallback(async () => setHistory(await api.draws()), [])

  useEffect(() => {
    loadPlayers().catch((e) => setError(errorMessage(e)))
    loadHistory().catch(() => undefined)
  }, [loadPlayers, loadHistory])

  const filters = { mode, exclude_drawn: excludeDrawn }

  useEffect(() => {
    setNoGames(false)
    if (selected.length === 0) {
      setCommon(null)
      setPlayerGames(null)
      return
    }
    let cancelled = false
    const preview =
      drawMode === 'per_player'
        ? api.playerGames(selected, { mode, exclude_drawn: excludeDrawn })
        : api.commonGames(selected, { mode, exclude_drawn: excludeDrawn })
    preview
      .then((c) => {
        if (!cancelled) {
          if (drawMode === 'per_player') {
            setPlayerGames(c as PlayerGames)
            setCommon(null)
          } else {
            setCommon(c as CommonGames)
            setPlayerGames(null)
          }
          setError(null)
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setCommon(null)
          setPlayerGames(null)
          setError(errorMessage(e))
        }
      })
    return () => {
      cancelled = true
    }
  }, [selected, drawMode, mode, excludeDrawn, history.length])

  const clearHistory = async () => {
    if (!window.confirm("Vider tout l'historique des tirages ? Les jeux déjà tirés pourront de nouveau être proposés.")) return
    try {
      await api.clearDraws()
      await loadHistory()
      setError(null)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const toggle = (id: number) =>
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : cur.length < MAX_PLAYERS ? [...cur, id] : cur))

  const add = () =>
    guard(async () => {
      const p = await api.addPlayer(input)
      setInput('')
      await loadPlayers()
      const r = await api.syncPlayer(p.id)
      if (r.status !== 'ok') setError(r.message)
      await loadPlayers()
    })

  const syncOne = (id: number) =>
    guard(async () => {
      const r = await api.syncPlayer(id)
      if (r.status !== 'ok' && r.message) setError(r.message)
      await loadPlayers()
    })

  const syncAll = () =>
    guard(async () => {
      const results = await api.syncAll()
      const failed = results.find((r) => r.status !== 'ok' && r.status !== 'cached')
      if (failed?.message) setError(failed.message)
      await loadPlayers()
    })

  const remove = (id: number) =>
    guard(async () => {
      await api.deletePlayer(id)
      await loadPlayers()
    })

  const draw = () =>
    guard(async () => {
      setNoGames(false)
      try {
        if (drawMode === 'per_player') {
          setPerPlayerResult(await api.drawPerPlayer(selected, filters))
          setResult(null)
        } else {
          setResult(await api.draw(selected, filters))
          setPerPlayerResult(null)
        }
        await loadHistory()
      } catch (e) {
        if (e instanceof ApiError && e.code === 'NO_COMMON_GAMES') {
          setNoGames(true)
          setResult(null)
        } else if (e instanceof ApiError && e.code === 'NO_COMPATIBLE_GAMES') {
          setPerPlayerResult(null)
          setError(errorMessage(e))
        } else throw e
      }
    })

  const full = selected.length >= MAX_PLAYERS

  return (
    <div>
      <ErrorBanner message={error} />
      <section className="mb-6">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <h2 className="text-lg font-semibold">Joueurs</h2>
          <span className="text-sm text-slate-400">
            {selected.length} / {MAX_PLAYERS} joueurs sélectionnés
          </span>
          <Button disabled={busy || players.length === 0} onClick={syncAll}>
            Synchroniser tous
          </Button>
        </div>
        <form
          className="mb-4 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (input.trim()) add()
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="SteamID64, URL de profil ou vanity URL"
            className="flex-1 rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm"
          />
          <Button type="submit" disabled={busy || !input.trim()}>
            Ajouter
          </Button>
        </form>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {players.map((p) => (
            <PlayerCard
              key={p.id}
              player={p}
              selected={selected.includes(p.id)}
              selectDisabled={full}
              busy={busy}
              onToggle={() => toggle(p.id)}
              onSync={() => syncOne(p.id)}
              onDelete={() => remove(p.id)}
            />
          ))}
        </div>
      </section>

      <section className="mb-6 rounded-lg border border-slate-700 bg-slate-900 p-4">
        <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
          <label>
            Type de tirage :{' '}
            <select
              value={drawMode}
              onChange={(e) => {
                setDrawMode(e.target.value as 'per_player' | 'common')
                setResult(null)
                setPerPlayerResult(null)
              }}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-1"
            >
              <option value="per_player">Individuel — un jeu par joueur</option>
              <option value="common">Commun — le même jeu pour tous</option>
            </select>
          </label>
          <label>
            Mode :{' '}
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as Mode)}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-1"
            >
              <option value="official">Official</option>
              <option value="recommended">Recommended</option>
              <option value="extended">Extended</option>
            </select>
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={excludeDrawn} onChange={(e) => setExcludeDrawn(e.target.checked)} />
            Ne pas proposer les jeux déjà tirés
          </label>
          <Button
            disabled={busy || selected.length === 0 || (drawMode === 'common' && common?.eligible_games_count === 0)}
            onClick={draw}
          >
            {drawMode === 'per_player' ? '🎲 Tirer un jeu par joueur' : '🎲 Tirer un jeu commun'}
          </Button>
        </div>
        {drawMode === 'common' && common && (
          <p className="text-sm">
            {common.eligible_games_count} jeux compatibles avec les joueurs sélectionnés
          </p>
        )}
        {drawMode === 'per_player' && playerGames && (
          <div className="space-y-1 text-sm">
            {selected.map((id) => {
              const entry = playerGames.players[id]
              return (
                <p key={id}>
                  {entry?.player.display_name ?? players.find((p) => p.id === id)?.display_name}: {entry?.games_count ?? 0}{' '}
                  jeux compatibles
                </p>
              )
            })}
          </div>
        )}
        {drawMode === 'common' && (noGames || common?.eligible_games_count === 0) && (
          <p className="mt-2 rounded border border-amber-700 bg-amber-950 p-2 text-sm text-amber-200">
            Aucun jeu compatible Archipelago n'est possédé par tous les joueurs sélectionnés. Modifiez les joueurs ou
            les filtres.
          </p>
        )}
        {drawMode === 'per_player' &&
          playerGames &&
          Object.values(playerGames.players).some((entry) => entry.games_count === 0) && (
            <p className="mt-2 rounded border border-amber-700 bg-amber-950 p-2 text-sm text-amber-200">
              Au moins un joueur n'a aucun jeu compatible Archipelago. Modifiez les joueurs ou les filtres.
            </p>
          )}
      </section>

      {result && <DrawResultCard result={result} />}
      {perPlayerResult && (
        <section className="mb-6 space-y-3">
          {perPlayerResult.results.map(({ draw_id, player, eligible_games_count, selected_game: game }) => (
            <article key={draw_id} className="rounded-xl border-2 border-indigo-500 bg-slate-900 p-5">
              <div className="text-sm uppercase tracking-wide text-indigo-300">🎲 Jeu de {player.display_name}</div>
              <h2 className="mb-2 text-2xl font-bold">{game.name}</h2>
              {game.header_image_url && <img src={game.header_image_url} alt="" className="mb-3 max-w-sm rounded" />}
              <p className="text-sm">
                Archipelago : <StatusBadge status={game.archipelago_status} detail={game.archipelago_detail_status} /> (
                {game.archipelago_name})
              </p>
              <p className="text-sm">
                Mapping Steam ↔ Archipelago : {game.mapping_verified ? '✓ Vérifié' : '⚠ Non vérifié'} (
                {game.mapping_type})
              </p>
              <p className="mb-3 text-xs text-slate-400">
                Tiré parmi {eligible_games_count} jeux compatibles pour ce joueur.
              </p>
              <a
                href={game.steam_url}
                target="_blank"
                rel="noreferrer"
                className="inline-block rounded bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500"
              >
                Ouvrir dans Steam
              </a>
            </article>
          ))}
        </section>
      )}
      {drawMode === 'common' && common && common.games.length > 0 && (
        <section className="mb-6">
          <GameList games={common.games} />
        </section>
      )}

      <section>
        <div className="mb-2 flex items-center gap-3">
          <h2 className="text-lg font-semibold">Historique</h2>
          {history.length > 0 && (
            <Button className="bg-red-800 hover:bg-red-700" onClick={clearHistory}>
              Vider l'historique
            </Button>
          )}
        </div>
        {history.length === 0 && <p className="text-sm text-slate-400">Aucun tirage.</p>}
        <ul className="space-y-1 text-sm">
          {history.map((d) => (
            <li key={d.id} className="rounded bg-slate-900 px-3 py-2">
              <span className="font-medium">{d.archipelago_name}</span> — {formatDate(d.created_at)} —{' '}
              {d.players.map((p) => p.display_name).join(', ')}
              {d.steam_url && (
                <>
                  {' '}
                  <a className="text-indigo-400 underline" href={d.steam_url} target="_blank" rel="noreferrer">
                    Steam
                  </a>
                </>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
