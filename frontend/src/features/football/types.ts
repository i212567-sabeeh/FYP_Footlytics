export interface Page<T> { items: T[]; total: number; offset: number; limit: number }
export interface ClubReference { id: number; name: string; is_active: boolean }
export interface TeamReference extends ClubReference { club_id: number }
export interface AccountReference { id: number; full_name: string }
export interface Club extends ClubReference {
  short_name: string | null; description: string | null; created_at: string; updated_at: string
}
export interface Team extends Club { club_id: number; club: ClubReference }
export const POSITIONS = ['goalkeeper', 'defender', 'midfielder', 'forward', 'other'] as const
export type Position = typeof POSITIONS[number]
export interface PlayerReference {
  id: number; first_name: string; last_name: string; display_name: string | null
  preferred_position: Position | null; is_active: boolean
}
export interface FootballPlayer extends PlayerReference {
  club_id: number; club: ClubReference; user_id: number | null
  linked_user: AccountReference | null; date_of_birth: string | null
  created_at: string; updated_at: string
}
export interface ClubMember { id: number; club_id: number; user_id: number; user: AccountReference; created_at: string }
export interface SquadMembership {
  id: number; team_id: number; player_id: number; team: TeamReference; player: PlayerReference
  shirt_number: number | null; is_active: boolean; joined_at: string | null; left_at: string | null
}
export type MatchFormat = '11v11' | '5v5'
export interface MatchFields {
  title: string; team_a_id: number; team_b_id: number; match_format: MatchFormat
  match_date: string; pitch_length_metres: number; pitch_width_metres: number
  venue: string | null; notes: string | null
}
export interface FootballMatch extends MatchFields {
  id: number; club_id: number; club: ClubReference; team_a: TeamReference; team_b: TeamReference
  is_archived: boolean; created_by_user_id: number; created_by: AccountReference
  created_at: string; updated_at: string
}
export function playerName(player: PlayerReference) {
  return player.display_name || `${player.first_name} ${player.last_name}`
}
