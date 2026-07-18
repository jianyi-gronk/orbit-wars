import { FactionMark } from "./FactionMark";

type TacticalHudPanelProps = {
  step: number;
  turnTime: string;
};

export function TacticalHudPanel({ step, turnTime }: TacticalHudPanelProps) {
  return (
    <section className="ow-tactical" data-density="tactical" aria-label="战术 HUD 组件预览">
      <div className="ow-tactical__topline">
        <p>LIVE COMMAND WINDOW</p>
        <p>
          STEP <strong>{String(step).padStart(3, "0")}</strong>
        </p>
      </div>

      <div className="ow-battlefield" aria-label="静态战场示意">
        <div className="ow-battlefield__scan ow-motion-scan" aria-hidden="true" />
        <div className="ow-planet ow-planet--aurora">
          <span>48</span>
        </div>
        <div className="ow-planet ow-planet--neutral">
          <span>16</span>
        </div>
        <div className="ow-planet ow-planet--cinder">
          <span>37</span>
        </div>
        <svg className="ow-battlefield__trajectory" viewBox="0 0 100 50" aria-hidden="true">
          <path d="M 18 34 Q 50 2 82 25" pathLength="1" />
        </svg>
      </div>

      <div className="ow-tactical__status">
        <FactionMark faction="aurora" label="AURORA / HUMAN" />
        <div className="ow-turn-clock" aria-label={"本回合剩余 " + turnTime}>
          <span>TURN CLOSES</span>
          <strong>{turnTime}</strong>
        </div>
        <FactionMark faction="cinder" label="CINDER / AGENT" />
      </div>
    </section>
  );
}
