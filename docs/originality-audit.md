# Originality and similarity audit

## Result

Pass for phase 1. All visible assets are project-authored CSS geometry, text, or Pixi canvas primitives listed in `apps/web/public/assets/sources.json`. No film stills, character art, franchise logos, soundtrack, copied interface images, or fashion photography are present.

## Space-opera reference boundary

Retained only broad genre signals: deep space, moving planets, fleet command, orbital rings, warning amber, and military telemetry. Excluded recognizable Star Wars elements: the outlined franchise wordmark, yellow perspective crawl, named factions/characters/locations, lightsabers, specific starfighter/capital-ship silhouettes, Imperial/Rebel insignia, screen compositions, dialogue, sound motifs, and typography intended to imitate the films.

Orbit/Wars uses a slash wordmark, circular coordinate mark, abstract circle/diamond faction encoding, graphite/amber/cyan palette, and planets/fleets derived from the Orbit Wars rules. Its core interaction is synchronous orbital launch vectors, not a film scene or vehicle simulation.

## AgenTank reference boundary

Retained the generic product loop of creating an entity, publishing an Agent version, training, ranking, and replaying. Excluded tanks, brackets, AgenTank naming/copy, page assets, exact navigation, exact card composition, colors, type treatment, icons, and promotional wording. Orbit/Wars adds Human direct control, one shared rating, orbital mechanics, factual battle explanation, and its own editorial/tactical density split.

## Fashion/editorial reference boundary

Retained abstract layout techniques common to print/editorial design: oversized display type, asymmetric columns, generous negative space, numbered rails, rule lines, and a restrained caption system. No specific brand campaign, magazine spread, proprietary font, photo, model, logo, or page composition was reproduced. Tactical pages deliberately abandon the editorial composition for stable command efficiency.

## Review checklist

- Wordmark, faction marks, ship/planet geometry, palette, motion, copy, and sound reviewed independently.
- No external bitmap/audio assets exist in the phase-one web bundle.
- Font stack uses project token system and system fallbacks; no franchise display font.
- Homepage, arena, tactical HUD, leaderboard, profile, and replay have distinct layouts from the reference products.
- Future third-party additions require source, author, URL, license, modification, and usage fields before merge.
