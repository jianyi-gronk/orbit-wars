import { describe, expect, it } from "vitest";

import commandCases from "../fixtures/command-batch-cases.json";
import {
  ContractValidationError,
  parseCommandBatchV1,
  parseObservationV1,
} from "../src/validation";

describe("CommandBatchV1 runtime validation", () => {
  for (const testCase of commandCases) {
    it(testCase.name, () => {
      if (testCase.valid) {
        expect(parseCommandBatchV1(testCase.value)).toEqual(testCase.value);
      } else {
        expect(() => parseCommandBatchV1(testCase.value)).toThrow(ContractValidationError);
      }
    });
  }

  it.each([Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    "rejects non-finite angle %s",
    (angle) => {
      const value = {
        schemaVersion: 1,
        matchId: "match_01",
        expectedStep: 12,
        commands: [{ fromPlanetId: 3, angle, ships: 8 }],
        idempotencyKey: "turn-12-alpha",
      };

      expect(() => parseCommandBatchV1(value)).toThrow(ContractValidationError);
    },
  );
});

describe("ObservationV1 runtime validation", () => {
  const observation = {
    schemaVersion: 1,
    matchId: "match_01",
    step: 12,
    player: 0,
    deadlineAt: "2026-07-17T12:00:00Z",
    angularVelocity: 0.01,
    planets: [],
    fleets: [],
    initialPlanets: [],
    comets: [],
  };

  it("accepts the generated wire shape", () => {
    expect(parseObservationV1(observation)).toEqual(observation);
  });

  it("rejects extra information", () => {
    expect(() => parseObservationV1({ ...observation, seed: 42 })).toThrow(ContractValidationError);
  });
});
