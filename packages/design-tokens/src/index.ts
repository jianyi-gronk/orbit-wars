export const DESIGN_SYSTEM_NAME = "Orbit Language";

export const COLOR_TOKENS = {
  canvas: "#07090c",
  surface: "#10141a",
  ink: "#f0eadc",
  muted: "#8f969e",
  warning: "#ffb84d",
  signal: "#ff4b3e",
  energy: "#62c8ff",
} as const;

export const DENSITY_TOKENS = {
  editorial: {
    contentMax: "92rem",
    gap: "clamp(1.5rem, 4vw, 5rem)",
    sectionPadding: "clamp(4rem, 11vw, 10rem)",
  },
  tactical: {
    contentMax: "100%",
    gap: "0.75rem",
    sectionPadding: "1rem",
  },
} as const;

export const MOTION_TOKENS = {
  standard: {
    orbitDuration: "18s",
    revealDuration: "640ms",
    scanDuration: "2.4s",
  },
  reduced: {
    orbitDuration: "0ms",
    revealDuration: "0ms",
    scanDuration: "0ms",
  },
} as const;

export const FACTION_ENCODINGS = {
  aurora: {
    color: COLOR_TOKENS.energy,
    pattern: "diagonal-stripe",
    shape: "ring",
  },
  cinder: {
    color: COLOR_TOKENS.signal,
    pattern: "cross-hatch",
    shape: "wedge",
  },
} as const;
