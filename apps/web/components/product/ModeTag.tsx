type ModeTagProps = {
  children: string;
  tone?: "human" | "agent" | "ranked" | "training";
};

export function ModeTag({ children, tone = "training" }: ModeTagProps) {
  return (
    <span className="mode-tag" data-tone={tone}>
      {children}
    </span>
  );
}
