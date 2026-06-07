import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { JointState } from '../hooks/useJointWS'

const COLORS = [
  '#e74c3c', '#e67e22', '#f1c40f', '#2ecc71',
  '#1abc9c', '#3498db', '#9b59b6', '#ecf0f1',
]

const JOINT_NAMES = [
  'J1', 'J2', 'J3', 'J4', 'J5', 'J6', 'J7', 'Grip',
]

interface Props {
  states: JointState[]
  field?: 'qpos' | 'qvel' | 'torque'
}

export function JointPlot({ states, field = 'qpos' }: Props) {
  const data = states.map((s, i) => {
    const row: Record<string, number> = { t: i }
    s[field].forEach((v, j) => { row[JOINT_NAMES[j]] = v })
    return row
  })

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#222" />
        <XAxis dataKey="t" hide />
        <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: '#888' }} />
        <Tooltip
          contentStyle={{ background: '#1a1a1a', border: '1px solid #333' }}
          labelStyle={{ color: '#888' }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {JOINT_NAMES.map((name, i) => (
          <Line
            key={name}
            type="monotone"
            dataKey={name}
            stroke={COLORS[i]}
            dot={false}
            isAnimationActive={false}
            strokeWidth={1.5}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
