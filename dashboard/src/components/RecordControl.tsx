import { useState, useEffect } from 'react'

interface Status {
  recording: boolean
  episode_id?: string
  frames_so_far?: number
  elapsed_s?: number
}

export function RecordControl() {
  const [status, setStatus] = useState<Status>({ recording: false })
  const [task, setTask] = useState('')
  const [episodeCount, setEpisodeCount] = useState(0)

  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const res = await fetch('/record/status')
        const data = await res.json() as Status
        setStatus(data)
      } catch { /* ignore */ }
    }, 500)
    return () => clearInterval(id)
  }, [])

  const startRecording = async () => {
    if (!task.trim()) return
    try {
      await fetch('/record/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: task.trim(), fps: 30 }),
      })
    } catch (e) { console.error(e) }
  }

  const stopRecording = async () => {
    try {
      await fetch('/record/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_failure: false }),
      })
      setEpisodeCount(c => c + 1)
    } catch (e) { console.error(e) }
  }

  const btnStyle: React.CSSProperties = {
    padding: '8px 20px',
    fontSize: 14,
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontFamily: 'monospace',
  }

  return (
    <div style={{ padding: 16, background: '#1a1a1a', borderRadius: 8, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
      <input
        value={task}
        onChange={e => setTask(e.target.value)}
        placeholder="Task description..."
        disabled={status.recording}
        style={{
          flex: 1, minWidth: 200, padding: '8px 12px', background: '#111',
          border: '1px solid #333', borderRadius: 4, color: '#e0e0e0',
          fontFamily: 'monospace', fontSize: 14,
        }}
      />

      {!status.recording ? (
        <button
          onClick={startRecording}
          disabled={!task.trim()}
          style={{ ...btnStyle, background: '#27ae60', color: '#fff' }}
        >
          ● REC
        </button>
      ) : (
        <button
          onClick={stopRecording}
          style={{ ...btnStyle, background: '#e74c3c', color: '#fff' }}
        >
          ■ STOP
        </button>
      )}

      <div style={{ fontSize: 12, color: '#888', minWidth: 140 }}>
        {status.recording ? (
          <>
            <span style={{ color: '#e74c3c' }}>● </span>
            {status.frames_so_far ?? 0} frames &nbsp;|&nbsp; {(status.elapsed_s ?? 0).toFixed(1)}s
          </>
        ) : (
          <span>Episodes: {episodeCount}</span>
        )}
      </div>
    </div>
  )
}
