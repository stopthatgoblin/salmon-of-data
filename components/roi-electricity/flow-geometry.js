// Shared map geometry. Positive flow always means an import into ROI.
export const project = ([longitude, latitude]) => ({x:(longitude + 10.8) * 130 + 190, y:(55.6 - latitude) * 216 + 10});

export function flowGeometry(flow) {
  const roi = project(flow.roiLocation);
  // Schematic East-West landfall on the Irish Sea coast near Holyhead.
  // Keep this display geometry current even for older accepted snapshots.
  const remote = project(flow.id === 'eastWest' ? [-4.64, 53.32] : flow.remoteLocation);
  if (flow.id === 'northSouth') {
    // Keep the cross-border flow visibly north/south in both directions.
    remote.x = roi.x;
  }
  const [start,end] = flow.value > 0 ? [remote,roi] : [roi,remote];
  const dx = end.x - start.x;
  return {
    start,end,roi,remote,
    path:flow.id === 'northSouth'
      ? `M${start.x} ${start.y}L${end.x} ${end.y}`
      : `M${start.x} ${start.y}C${start.x + dx * .35} ${start.y} ${end.x - dx * .35} ${end.y} ${end.x} ${end.y}`,
  };
}
