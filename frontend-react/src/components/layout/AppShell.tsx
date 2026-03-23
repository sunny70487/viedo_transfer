import { Outlet } from 'react-router-dom'
import { Header } from './Header'

export function AppShell() {
  return (
    <div className="min-h-screen bg-bg dark:bg-bg-dark transition-colors duration-300">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <Outlet />
      </main>
      <footer className="border-t border-border dark:border-border-dark py-4 mt-auto">
        <p className="text-center text-sm text-muted dark:text-muted-dark">
          Whisper Transfer &copy; {new Date().getFullYear()}
        </p>
      </footer>
    </div>
  )
}
