import type { EligibleGame } from '../api'
import { StatusBadge } from './ui'

export default function GameList({ games }: { games: EligibleGame[] }) {
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {games.map((g) => (
        <li key={g.archipelago_game_id} className="overflow-hidden rounded-lg border border-slate-700 bg-slate-900">
          {g.header_image_url && <img src={g.header_image_url} alt="" loading="lazy" className="w-full" />}
          <div className="space-y-1 p-3 text-sm">
            <div className="font-semibold">{g.name}</div>
            <div className="text-xs text-slate-400">Archipelago : {g.archipelago_name}</div>
            <div className="flex items-center gap-2 text-xs">
              Steam ✓ · Archipelago ✓ <StatusBadge status={g.archipelago_status} detail={g.archipelago_detail_status} />
            </div>
            <div className="text-xs text-slate-400">Source : {g.source_name ?? 'inconnue'}</div>
            <div className="text-xs text-slate-400">
              Possédé par {g.owned_by_count} / {g.players_count} joueurs
            </div>
            <a className="text-xs text-indigo-400 underline" href={g.steam_url} target="_blank" rel="noreferrer">
              Steam App ID {g.steam_app_id}
            </a>
          </div>
        </li>
      ))}
    </ul>
  )
}
