import { useState } from 'react'
import { useJointWS } from './hooks/useJointWS'
import { JointPlot } from './components/JointPlot'
import { CameraFeed } from './components/CameraFeed'
import { RecordControl } from './components/RecordControl'
import { StatusBar } from './components/StatusBar'

const CAMERAS = [
  { name: 'cam_left_wrist',  label: 'Left Wrist' },
  { name: 'cam_right_wrist', label: 'Right Wrist' },
  { name: 'cam_ceiling',     label: 'Ceiling' },
  { name: 'cam_zed_left',    label: 'ZED Left' },
]

type PlotField = 'qpos' | 'qvel' | 'torque'

export default function App() {
  const { jointStates, readyState } = useJointWS()
  const [field, setField] = useState<PlotField>('qpos')

  const latestTs = jointStates.at(-1)?.ts

  const tabStyle = (active: boolean): React.CSSProperties => ({
    padding: '4px 12px', border: 'none', borderRadius: 4, cursor: 'pointer',
    fontFamily: 'monospace', fontSize: 12,
    background: active ? '#3498db' : '#222',
    color: active ? '#fff' : '#888',
  })

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <StatusBar readyState={readyState} latestTs={latestTs} />

      <div style={{ padding: 16, flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <RecordControl />

        {/* Camera grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 12,
        }}>
          {CAMERAS.map(cam => (
            <CameraFeed key={cam.name} camName={cam.name} label={cam.label} />
          ))}
        </div>

        {/* Joint plot */}
        <div style={{ background: '#1a1a1a', borderRadius: 8, padding: 12 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 10, alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: '#888', marginRight: 4 }}>Show:</span>
            {(['qpos', 'qvel', 'torque'] as PlotField[]).map(f => (
              <button key={f} style={tabStyle(field === f)} onClick={() => setField(f)}>
                {f}
              </button>
            ))}
            <span style={{ marginLeft: 'auto', fontSize: 11, color: '#555' }}>
              {jointStates.length} samples
            </span>
          </div>
          <JointPlot states={jointStates} field={field} />
        </div>
      </div>
    </div>
  )
}
