import type { Player } from '../api'
import { Button, formatDate } from './ui'

interface Props {
  player: Player
  selected: boolean
  selectDisabled: boolean
  busy: boolean
  onToggle: () => void
  onSync: () => void
  onDelete: () => void
}

export default function PlayerCard({ player, selected, selectDisabled, busy, onToggle, onSync, onDelete }: Props) {
  const private_ = player.last_sync_status === 'private'
  return (
    <div className={`rounded-lg border p-3 ${selected ? 'border-indigo-500 bg-slate-800' : 'border-slate-700 bg-slate-900'}`}>
      <div className="flex items-center gap-3">
        {player.avatar_url ? (
          <img src={player.avatar_url} alt="" className="h-12 w-12 rounded" />
        ) : (
          <div className="h-12 w-12 rounded bg-slate-700" />
        )}
        <div className="min-w-0 flex-1">
          <div className="truncate font-semibold">{player.display_name}</div>
          <div className="text-xs text-slate-400">
            {player.library_valid ? `${player.game_count} jeux` : 'Bibliothèque non synchronisée'}
          </div>
          <div className="text-xs text-slate-500">Sync : {formatDate(player.last_synced_at)}</div>
        </div>
        <input
          type="checkbox"
          aria-label={`Sélectionner ${player.display_name}`}
          className="h-5 w-5"
          checked={selected}
          disabled={!selected && selectDisabled}
          onChange={onToggle}
        />
      </div>
      {private_ && (
        <p className="mt-2 text-xs text-amber-300">
          Impossible de récupérer la bibliothèque : le profil ou la bibliothèque Steam est privé.
          {player.library_valid && ' Dernières données valides conservées.'}
        </p>
      )}
      {player.last_sync_status === 'error' && (
        <p className="mt-2 text-xs text-amber-300">
          Steam indisponible ({player.last_sync_error}).
          {player.library_valid && ` Données du ${formatDate(player.last_synced_at)} conservées.`}
        </p>
      )}
      <div className="mt-3 flex gap-2">
        <Button disabled={busy} onClick={onSync}>
          Synchroniser
        </Button>
        <Button className="bg-red-800 hover:bg-red-700" disabled={busy} onClick={onDelete}>
          Supprimer
        </Button>
      </div>
    </div>
  )
}
