import { describe, test, expect } from 'bun:test';
import { z } from 'zod';
import {
  searchParams,
  coerceBoolean,
  SUPPORTED_SITES,
  UPSTREAM_SITES,
  LOCAL_SITES,
} from '../src/schemas/searchParamsSchema.js';

describe('Search Params Schema', () => {
  const schema = z.object(searchParams);

  test('contains all expected supported sites', () => {
    expect(SUPPORTED_SITES).toContain('bdjobs');
    expect(SUPPORTED_SITES).toContain('jobstreet');
    expect(SUPPORTED_SITES).toContain('glints');
    expect(SUPPORTED_SITES).toContain('indeed');
    expect(SUPPORTED_SITES).toContain('linkedin');
    expect(SUPPORTED_SITES).toContain('glassdoor');
    expect(UPSTREAM_SITES).toContain('bdjobs');
    expect(LOCAL_SITES).toEqual(['jobstreet', 'glints']);
  });

  test('validates valid single site string', () => {
    const result = schema.parse({ siteNames: 'bdjobs' });
    expect(result.siteNames).toBe('bdjobs');
  });

  test('validates valid jobstreet and glints sites', () => {
    expect(schema.parse({ siteNames: 'jobstreet' }).siteNames).toBe('jobstreet');
    expect(schema.parse({ siteNames: 'glints' }).siteNames).toBe('glints');
  });

  test('validates multiple comma-separated sites', () => {
    const result = schema.parse({ siteNames: 'indeed,jobstreet,glints,bdjobs' });
    expect(result.siteNames).toBe('indeed,jobstreet,glints,bdjobs');
  });

  test('validates array of sites and transforms to string', () => {
    const result = schema.parse({ siteNames: ['indeed', 'jobstreet', 'glints'] });
    expect(result.siteNames).toBe('indeed,jobstreet,glints');
  });

  test('rejects invalid site names', () => {
    expect(() => {
      schema.parse({ siteNames: 'unknown_portal' });
    }).toThrow();
  });

  test('generates strict JSON Schema for MCP Inspector with no untyped properties', () => {
    const jsonSchema = z.toJSONSchema(schema, { io: 'input', unrepresentable: 'any' });
    expect(jsonSchema.type).toBe('object');
    expect(jsonSchema.properties.isRemote.type).toBe('boolean');
    expect(jsonSchema.properties.isRemote.default).toBe(false);
    expect(jsonSchema.properties.linkedinFetchDescription.type).toBe('boolean');
    expect(jsonSchema.properties.linkedinFetchDescription.default).toBe(false);

    for (const [, prop] of Object.entries(jsonSchema.properties)) {
      const hasTypeConstraint = Boolean(prop.type || prop.anyOf || prop.enum);
      expect(hasTypeConstraint).toBe(true);
      expect('default' in prop).toBe(true);
      expect(typeof prop.description).toBe('string');
    }
  });

  test('coerceBoolean handles strings, booleans, and numbers', () => {
    expect(coerceBoolean(true)).toBe(true);
    expect(coerceBoolean(false)).toBe(false);
    expect(coerceBoolean('true')).toBe(true);
    expect(coerceBoolean('YES')).toBe(true);
    expect(coerceBoolean('1')).toBe(true);
    expect(coerceBoolean('false')).toBe(false);
    expect(coerceBoolean('0')).toBe(false);
  });
});
