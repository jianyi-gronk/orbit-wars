type EditorialFeatureProps = {
  number: string;
  title: string;
  body: string;
  tone: "signal" | "energy" | "warning";
};

export function EditorialFeature({ number, title, body, tone }: EditorialFeatureProps) {
  return (
    <article className="ow-feature" data-tone={tone}>
      <p className="ow-feature__number">{number}</p>
      <div>
        <h2>{title}</h2>
        <p>{body}</p>
      </div>
    </article>
  );
}
