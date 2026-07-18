import type { ReactNode } from "react";

type OrbitMastheadProps = {
  eyebrow: string;
  index: string;
  title: ReactNode;
  lede: string;
};

export function OrbitMasthead({ eyebrow, index, title, lede }: OrbitMastheadProps) {
  return (
    <header className="ow-masthead ow-motion-reveal" data-density="editorial">
      <div className="ow-masthead__rail" aria-hidden="true">
        <span>{index}</span>
        <span>ORBITAL FIELD NOTES</span>
      </div>
      <div className="ow-masthead__copy">
        <p className="ow-kicker">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="ow-masthead__lede">{lede}</p>
      </div>
      <div className="ow-orbit-mark" aria-hidden="true">
        <span className="ow-orbit-mark__axis ow-motion-orbit" />
        <span className="ow-orbit-mark__core" />
      </div>
    </header>
  );
}
