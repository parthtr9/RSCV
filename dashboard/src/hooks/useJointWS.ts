import { useEffect, useRef, useState } from 'react'
import useWebSocket from 'react-use-websocket'

export interface JointState {
  ts: number
  qpos: number[]
  qvel: number[]
  torque: number[]
}

const WS_URL = 'ws://localhost:8000/ws/joint_states'
const WINDOW_SIZE = 200
const FLUSH_MS = 100

export function useJointWS() {
  const [jointStates, setJointStates] = useState<JointState[]>([])
  const buffer = useRef<JointState[]>([])

  const { lastMessage, readyState } = useWebSocket(WS_URL, {
    shouldReconnect: () => true,
    reconnectInterval: 1000,
  })

  useEffect(() => {
    if (lastMessage?.data) {
      try {
        const state = JSON.parse(lastMessage.data) as JointState
        buffer.current.push(state)
      } catch {
        // malformed frame — skip
      }
    }
  }, [lastMessage])

  // Flush buffer to state at display rate
  useEffect(() => {
    const id = setInterval(() => {
      if (buffer.current.length > 0) {
        setJointStates(prev => {
          const next = [...prev, ...buffer.current].slice(-WINDOW_SIZE)
          buffer.current = []
          return next
        })
      }
    }, FLUSH_MS)
    return () => clearInterval(id)
  }, [])

  return { jointStates, readyState }
}
