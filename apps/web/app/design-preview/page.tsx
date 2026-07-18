import type { Metadata } from "next";

import { TacticalHudPanel } from "../../components/battle/TacticalHudPanel";
import { EditorialFeature } from "../../components/editorial/EditorialFeature";
import { OrbitMasthead } from "../../components/editorial/OrbitMasthead";

export const metadata: Metadata = {
  title: "Orbit Language Preview",
};

type DesignPreviewPageProps = {
  searchParams: Promise<{ motion?: string | string[] }>;
};

export default async function DesignPreviewPage({ searchParams }: DesignPreviewPageProps) {
  const motion = (await searchParams).motion;
  const reducedMotion = motion === "reduced";

  return (
    <main className="ow-preview" data-motion={reducedMotion ? "reduced" : "standard"}>
      <OrbitMasthead
        eyebrow="ORIGINAL INTERSTELLAR COMMAND SYSTEM / 01"
        index="01—08"
        title={
          <>
            COMMAND
            <br />
            THE <em>ORBIT</em>
          </>
        }
        lede="创建舰队，把策略交给 Agent，让每一次自主出战都留下可验证航迹。"
      />

      <section className="ow-feature-grid" data-density="editorial" aria-label="设计原则">
        <EditorialFeature
          number="A"
          title="Editorial scale"
          body="品牌页面使用超大排版、越界轨道和不对称留白，让战役像一期值得收藏的前线型录。"
          tone="warning"
        />
        <EditorialFeature
          number="B"
          title="Tactical restraint"
          body="进入实时战斗后，结构收紧。归属、兵力、航迹和倒计时保持稳定，不让效果越过指令。"
          tone="energy"
        />
        <EditorialFeature
          number="C"
          title="Dual identity"
          body="阵营同时使用颜色、形状和纹理编码；控制方式只是公开标签，不形成第二套实力规则。"
          tone="signal"
        />
      </section>

      <section className="ow-preview__tactical">
        <div className="ow-preview__section-label">
          <span>02</span>
          <p>TACTICAL DENSITY / ACCESSIBLE BY DEFAULT</p>
        </div>
        <TacticalHudPanel step={83} turnTime="02.4" />
      </section>

      <footer className="ow-preview__footer">
        <p>ORBIT LANGUAGE / PHASE 01</p>
        <p>NO LICENSED FILM IP · NO COPIED INTERFACE ASSETS</p>
      </footer>
    </main>
  );
}
