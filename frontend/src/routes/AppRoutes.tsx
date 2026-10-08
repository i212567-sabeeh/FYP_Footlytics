import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router'
import { AppLayout } from '../layouts/AppLayout'
import { FoundationPage } from '../pages/FoundationPage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { LoginPage } from '../pages/LoginPage'
import { SignupPage } from '../pages/SignupPage'
import { SignupRequestsPage } from '../pages/SignupRequestsPage'
import { UsersPage } from '../pages/UsersPage'
import { ProtectedRoute } from './ProtectedRoute'
import { RoleRoute } from './RoleRoute'
import { ClubsPage, ClubDetailPage } from '../pages/ClubsPage'
import { TeamsPage, TeamDetailPage } from '../pages/TeamsPage'
import { PlayersPage, PlayerDetailPage } from '../pages/PlayersPage'
import { MatchesPage, NewMatchPage, MatchDetailPage } from '../pages/MatchesPage'
import { CalibrationPage } from '../pages/CalibrationPage'
import { ReviewPage } from '../pages/ReviewPage'

const AnalyticsPage = lazy(() => import('../pages/AnalyticsPage').then((module) => ({ default: module.AnalyticsPage })))

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="login" element={<LoginPage />} />
        <Route path="signup" element={<SignupPage />} />
        <Route element={<ProtectedRoute />}>
          <Route index element={<FoundationPage />} />
          <Route path="clubs" element={<ClubsPage />} />
          <Route path="clubs/:clubId" element={<ClubDetailPage />} />
          <Route path="teams" element={<TeamsPage />} />
          <Route path="teams/:teamId" element={<TeamDetailPage />} />
          <Route path="players" element={<PlayersPage />} />
          <Route path="players/:playerId" element={<PlayerDetailPage />} />
          <Route path="matches" element={<MatchesPage />} />
          <Route element={<RoleRoute roles={['admin', 'coach', 'analyst']} />}>
            <Route path="matches/new" element={<NewMatchPage />} />
          </Route>
          <Route path="matches/:matchId" element={<MatchDetailPage />} />
          <Route path="matches/:matchId/calibration" element={<CalibrationPage />} />
          <Route element={<RoleRoute roles={['admin', 'coach', 'analyst', 'club_management']} />}>
            <Route path="matches/:matchId/review" element={<ReviewPage />} />
            <Route path="matches/:matchId/analytics" element={<Suspense fallback={<p role="status" className="py-8 text-slate-400">Loading analytics dashboard…</p>}><AnalyticsPage /></Suspense>} />
          </Route>
          <Route element={<RoleRoute roles={['admin']} />}>
            <Route path="admin/users" element={<UsersPage />} />
            <Route path="admin/signup-requests" element={<SignupRequestsPage />} />
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
