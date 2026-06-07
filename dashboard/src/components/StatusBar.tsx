import { ReadyState } from 'react-use-websocket'

interface Props {
  readyState: ReadyState
  latestTs?: number
}

const STATE_LABEL: Record<number, string> = {
  [ReadyState.CONNECTING]: 'CONNECTING',
  [ReadyState.OPEN]:       'LIVE',
  [ReadyState.CLOSING]:    'CLOSING',
  [ReadyState.CLOSED]:     'DISCONNECTED',
}

const STATE_COLOR: Record<number, string> = {
  [ReadyState.CONNECTING]: '#f39c12',
  [ReadyState.OPEN]:       '#2ecc71',
  [ReadyState.CLOSING]:    '#e67e22',
  [ReadyState.CLOSED]:     '#e74c3c',
}

export function StatusBar({ readyState, latestTs }: Props) {
  const label = STATE_LABEL[readyState] ?? 'UNKNOWN'
  const color = STATE_COLOR[readyState] ?? '#888'

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 16,
      padding: '6px 16px', background: '#111', borderBottom: '1px solid #222',
      fontSize: 12, color: '#888',
    }}>
      <span style={{ color, fontWeight: 'bold' }}>● {label}</span>
      <span>OpenArm 2.0 Data Collection</span>
      {latestTs !== undefined && (
        <span style={{ marginLeft: 'auto' }}>ts={latestTs.toFixed(3)}</span>
      )}
    </div>
  )
}
