/**
 * Light theme for the Scaife Viewer embed widget.
 * Matches Scaife's white background + terracotta accent palette.
 */
export const T = {
  bg: "#ffffff", surface: "#f8f9fa", raised: "#e9ecef",
  hover: "#dee2e6", border: "#ced4da", borderL: "#adb5bd",
  text: "#212529", dim: "#6c757d", bright: "#212529",
  gold: "#b45141", goldDim: "#8b3a2e", goldGlow: "rgba(180,81,65,0.10)",
  red: "#c4574a", blue: "#3a6f94", green: "#4a7c4a",
  purple: "#6b4f88", teal: "#3a7e74", orange: "#a4663a",
  rose: "#944959", cyan: "#3a8f94",
  font: "'Noto Serif',Georgia,serif",
  mono: "'JetBrains Mono',monospace",
  xs: 13, sm: 14, md: 16, lg: 18, xl: 26,
};

export const POS_CLR = {
  noun: T.gold, verb: T.blue, adjective: T.green, adverb: T.purple,
  pronoun: T.teal, preposition: T.orange, conjunction: T.rose,
  particle: T.cyan, article: T.dim, "": T.dim,
};
