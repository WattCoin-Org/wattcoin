export const AGENT_COLORS = [
  "#F59E0B", // amber
  "#3B82F6", // blue
  "#10B981", // emerald
  "#A855F7", // purple
  "#EF4444", // red
  "#06B6D4", // cyan
  "#EC4899", // pink
  "#84CC16", // lime
];

export function getAgentColor(index) {
  return AGENT_COLORS[index % AGENT_COLORS.length];
}
