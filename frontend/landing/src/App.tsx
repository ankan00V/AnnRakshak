import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Landing from './Landing'
import FarmerApp from './farmer/FarmerApp'
import Home from './farmer/screens/Home'
import { AuthProvider } from './auth/AuthContext'
import RequireRole from './auth/RequireRole'
import { PageSkeleton } from './ui/kit'

// Farmers load only their own screens on slow rural networks; the expert
// console, the Leaflet-heavy officials' dashboard and the sign-up forms are
// separate chunks.
const Scan = lazy(() => import('./farmer/screens/Scan'))
const Live = lazy(() => import('./farmer/screens/Live'))
const Weather = lazy(() => import('./farmer/screens/Weather'))
const Result = lazy(() => import('./farmer/screens/Result'))
const Spray = lazy(() => import('./farmer/screens/Spray'))
const Alerts = lazy(() => import('./farmer/screens/Alerts'))
const History = lazy(() => import('./farmer/screens/History'))
const ProblemDetail = lazy(() => import('./farmer/screens/History').then((m) => ({ default: m.ProblemDetail })))
const ExpertConsole = lazy(() => import('./expert/ExpertConsole'))
const OfficerShell = lazy(() => import('./officer/OfficerShell'))
const OfficerToday = lazy(() => import('./officer/pages/Today'))
const OfficerMap = lazy(() => import('./officer/pages/MapPage'))
const OfficerAdvisories = lazy(() => import('./officer/pages/Advisories'))
const OfficerInputs = lazy(() => import('./officer/pages/Inputs'))
const OfficerModel = lazy(() => import('./officer/pages/ModelGaps'))
const OfficerOfficers = lazy(() => import('./officer/pages/Officers'))
const OfficerReference = lazy(() => import('./officer/pages/Reference'))
const AuthLayout = lazy(() => import('./auth/AuthLayout'))
const Login = lazy(() => import('./auth/Login'))
const SignupChoose = lazy(() => import('./auth/SignupChoose'))
const SignupFarmer = lazy(() => import('./auth/SignupFarmer'))
const SignupExpert = lazy(() => import('./auth/SignupExpert'))

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Suspense fallback={<PageSkeleton />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route element={<AuthLayout />}>
              <Route path="/login" element={<Login />} />
              <Route path="/signup" element={<SignupChoose />} />
              <Route path="/signup/farmer" element={<SignupFarmer />} />
              <Route path="/signup/expert" element={<SignupExpert />} />
            </Route>
            <Route path="/app" element={<RequireRole role="farmer"><FarmerApp /></RequireRole>}>
              <Route index element={<Home />} />
              <Route path="scan" element={<Scan />} />
              <Route path="live" element={<Live />} />
              <Route path="weather" element={<Weather />} />
              <Route path="result" element={<Result />} />
              <Route path="spray" element={<Spray />} />
              <Route path="alerts" element={<Alerts />} />
              <Route path="history" element={<History />} />
              <Route path="history/:id" element={<ProblemDetail />} />
            </Route>
            <Route path="/expert" element={<RequireRole role="expert"><ExpertConsole /></RequireRole>} />
            <Route path="/officer" element={<RequireRole role="expert"><OfficerShell /></RequireRole>}>
              <Route index element={<OfficerToday />} />
              <Route path="map" element={<OfficerMap />} />
              <Route path="advisories" element={<OfficerAdvisories />} />
              <Route path="inputs" element={<OfficerInputs />} />
              <Route path="model" element={<OfficerModel />} />
              <Route path="officers" element={<OfficerOfficers />} />
              <Route path="reference" element={<OfficerReference />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  )
}
