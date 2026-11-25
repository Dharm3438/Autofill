import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import { CatalogProvider } from './context/CatalogContext'
import ProtectedRoute, { HomeRedirect } from './components/ProtectedRoute'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import CustomersPage from './pages/CustomersPage'
import InstallationsPage from './pages/InstallationsPage'
import UsersPage from './pages/UsersPage'
import WelcomePage from './pages/WelcomePage'
import { PERM, CUSTOMERS_VIEW } from './utils/access'

function Page({ perm, children }) {
  return (
    <ProtectedRoute perm={perm}>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <CatalogProvider>
          <BrowserRouter>
            <Toaster position="top-right" toastOptions={{ duration: 3000 }} />
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              {/* No Layout: pending users get no navbar or tabs at all. */}
              <Route path="/welcome" element={<ProtectedRoute><WelcomePage /></ProtectedRoute>} />
              <Route path="/dashboard" element={<Page perm={PERM.DASHBOARD_VIEW}><DashboardPage /></Page>} />
              <Route path="/customers" element={<Page perm={CUSTOMERS_VIEW}><CustomersPage /></Page>} />
              <Route path="/installations" element={<Page perm={PERM.INSTALLATIONS_READ}><InstallationsPage /></Page>} />
              <Route path="/users" element={<Page perm={PERM.USERS_MANAGE}><UsersPage /></Page>} />
              <Route path="*" element={<HomeRedirect />} />
            </Routes>
          </BrowserRouter>
        </CatalogProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
