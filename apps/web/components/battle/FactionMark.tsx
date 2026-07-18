type FactionMarkProps = {
  faction: "aurora" | "cinder";
  label: string;
};

export function FactionMark({ faction, label }: FactionMarkProps) {
  return (
    <span className="ow-faction-mark" data-faction={faction}>
      <span className="ow-faction-mark__glyph" aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}
