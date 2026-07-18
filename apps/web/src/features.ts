export function resolveHumanPlayEnabled(value: string | undefined): boolean {
  return value === "true";
}

export const humanPlayEnabled = resolveHumanPlayEnabled(process.env.NEXT_PUBLIC_ENABLE_HUMAN_PLAY);
