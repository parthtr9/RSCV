interface Props {
  camName: string
  label?: string
}

export function CameraFeed({ camName, label }: Props) {
  return (
    <div style={{ background: '#111', borderRadius: 6, overflow: 'hidden' }}>
      {label && (
        <div style={{ padding: '4px 8px', fontSize: 11, color: '#888', background: '#1a1a1a' }}>
          {label}
        </div>
      )}
      <img
        src={`/stream/${camName}`}
        alt={camName}
        style={{ width: '100%', display: 'block' }}
        onError={(e) => {
          // Show placeholder on load error
          ;(e.target as HTMLImageElement).style.opacity = '0.3'
        }}
      />
    </div>
  )
}
