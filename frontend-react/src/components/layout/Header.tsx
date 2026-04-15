import { useState } from 'react'
import { AudioWaveform, Cpu, Sun, Moon, Monitor, Settings } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { LlmSettingsDialog } from '@/components/ui/LlmSettingsDialog'
import { useThemeStore } from '@/stores/theme-store'
import { useGpuInfo } from '@/hooks/use-gpu-info'

export function Header() {
  const { mode, setMode } = useThemeStore()
  const [gpuOpen, setGpuOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const gpuQuery = useGpuInfo(gpuOpen)

  const ThemeIcon = mode === 'dark' ? Moon : mode === 'light' ? Sun : Monitor

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-border dark:border-border-dark bg-surface/80 dark:bg-surface-dark/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-text dark:text-text-dark hover:opacity-80 transition-opacity">
            <AudioWaveform className="h-6 w-6 text-primary" />
            <span className="text-lg font-semibold">Whisper Transfer</span>
          </Link>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSettingsOpen(true)}
              title="LLM API 設定"
              aria-label="LLM API 設定"
            >
              <Settings className="h-5 w-5" aria-hidden="true" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setMode(mode === 'dark' ? 'light' : mode === 'light' ? 'system' : 'dark')}
              title={`主題: ${mode === 'dark' ? '深色' : mode === 'light' ? '淺色' : '系統'}`}
            >
              <ThemeIcon className="h-5 w-5" />
            </Button>
            <Button variant="outline" size="sm" onClick={() => setGpuOpen(true)}>
              <Cpu className="h-4 w-4" />
              <span className="hidden sm:inline">GPU</span>
            </Button>
          </div>
        </div>
      </header>

      <LlmSettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      <Dialog open={gpuOpen} onClose={() => setGpuOpen(false)} title="GPU 狀態">
        {gpuQuery.isLoading ? (
          <p className="text-muted dark:text-muted-dark">載入中...</p>
        ) : gpuQuery.isError ? (
          <p className="text-danger">無法取得 GPU 資訊</p>
        ) : gpuQuery.data ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${gpuQuery.data.available ? 'bg-success' : 'bg-danger'}`} />
              <span className="font-medium text-text dark:text-text-dark">
                {gpuQuery.data.available
                  ? `可用 (${gpuQuery.data.device_count} 裝置)`
                  : gpuQuery.data.device_count > 0
                    ? `偵測到 ${gpuQuery.data.device_count} 裝置（CUDA 未就緒）`
                    : '不可用'}
              </span>
            </div>
            {gpuQuery.data.devices.map((dev, i) => (
              <div key={i} className="rounded-lg bg-bg dark:bg-bg-dark p-3 space-y-1 text-sm">
                <p className="font-medium text-text dark:text-text-dark">{dev.name}</p>
                <p className="text-muted dark:text-muted-dark">已用: {dev.memory_allocated} / 最大: {dev.max_memory}</p>
              </div>
            ))}
          </div>
        ) : null}
      </Dialog>
    </>
  )
}
