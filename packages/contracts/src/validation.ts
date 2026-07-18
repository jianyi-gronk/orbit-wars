import Ajv2020, { type ErrorObject, type ValidateFunction } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import schema from "../schemas/contracts-v1.json";
import type { CommandBatchV1, ObservationV1 } from "./generated/contracts-v1";

export class ContractValidationError extends Error {
  readonly issues: readonly ErrorObject[];

  constructor(contractName: string, issues: readonly ErrorObject[]) {
    super(`${contractName} does not match schema version 1`);
    this.name = "ContractValidationError";
    this.issues = issues;
  }
}

const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
ajv.addSchema(schema);

function validatorFor(definition: string): ValidateFunction {
  const validator = ajv.getSchema(`${schema.$id}#/$defs/${definition}`);
  if (!validator) {
    throw new Error(`missing generated validator for ${definition}`);
  }
  return validator;
}

const validateCommandBatch = validatorFor("CommandBatchV1");
const validateObservation = validatorFor("ObservationV1");

function parseContract<T>(contractName: string, validator: ValidateFunction, value: unknown): T {
  if (!validator(value)) {
    throw new ContractValidationError(contractName, validator.errors ?? []);
  }
  return value as T;
}

export function parseCommandBatchV1(value: unknown): CommandBatchV1 {
  return parseContract<CommandBatchV1>("CommandBatchV1", validateCommandBatch, value);
}

export function parseObservationV1(value: unknown): ObservationV1 {
  return parseContract<ObservationV1>("ObservationV1", validateObservation, value);
}
