import Navbar from './Navbar'
import { VerifyEmailBanner } from './AccountNotices'

export default function Layout({ children }) {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <VerifyEmailBanner />
      <main className="flex-1">{children}</main>
    </div>
  )
}
