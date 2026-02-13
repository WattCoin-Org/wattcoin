export default function StatusBadge({ status = 'idle' }) {
  const statusConfig = {
    idle: { color: 'bg-gray-500', text: 'Idle', pulse: false },
    thinking: { color: 'bg-amber-500', text: 'Thinking', pulse: true },
    complete: { color: 'bg-green-500', text: 'Complete', pulse: false },
    error: { color: 'bg-red-500', text: 'Error', pulse: false },
  };

  const config = statusConfig[status] || statusConfig.idle;

  return (
    <div className="flex items-center gap-2">
      <div className="relative">
        <div className={`w-2 h-2 rounded-full ${config.color}`} />
        {config.pulse && (
          <div className={`absolute inset-0 w-2 h-2 rounded-full ${config.color} animate-ping opacity-75`} />
        )}
      </div>
      <span className="text-xs text-text-secondary">{config.text}</span>
    </div>
  );
}
