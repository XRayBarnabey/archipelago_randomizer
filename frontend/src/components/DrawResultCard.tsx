import type { DrawResult } from '../api'
import { StatusBadge } from './ui'

export default function DrawResultCard({ result }: { result: DrawResult }) {
  const g = result.selected_game
  return (
    <section className="mb-6 max-w-md rounded-lg border-2 border-indigo-500 bg-slate-900 p-3">
      <div className="text-xs uppercase tracking-wide text-indigo-300">🎲 Votre jeu</div>
      <h2 className="mb-2 text-lg font-bold leading-tight">{g.name}</h2>
      {g.header_image_url && <img src={g.header_image_url} alt="" className="mb-2 max-h-24 w-full rounded object-cover" />}
      <p className="text-sm">
        Archipelago : <StatusBadge status={g.archipelago_status} detail={g.archipelago_detail_status} /> ({g.archipelago_name})
      </p>
      <p className="text-sm">Steam App ID : {g.steam_app_id}</p>
      <p className="mt-2 text-sm font-medium">Possédé par :</p>
      <ul className="mb-2 text-sm">
        {result.owners.map((o) => (
          <li key={o.id}>✓ {o.display_name}</li>
        ))}
      </ul>
      <p className="text-sm">
        Mapping Steam ↔ Archipelago : {g.mapping_verified ? '✓ Vérifié' : '⚠ Non vérifié'} ({g.mapping_type})
      </p>
      <p className="mb-3 text-xs text-slate-400">
        Tiré parmi {result.eligible_games_count} jeux compatibles, {result.players_count} joueurs.
      </p>
      <a
        href={g.steam_url}
        target="_blank"
        rel="noreferrer"
        className="inline-block rounded bg-indigo-600 px-3 py-1 text-xs font-medium hover:bg-indigo-500"
      >
        Ouvrir dans Steam
      </a>
    </section>
  )
}
