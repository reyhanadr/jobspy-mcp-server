import { z } from 'zod';

// Single source of truth for all supported site names
export const UPSTREAM_SITES = [
  'indeed',
  'linkedin',
  'zip_recruiter',
  'glassdoor',
  'google',
  'bayt',
  'naukri',
  'bdjobs',
];
export const LOCAL_SITES = ['jobstreet', 'glints'];
export const SUPPORTED_SITES = [...UPSTREAM_SITES, ...LOCAL_SITES];

/**
 * Helper to coerce string/number truthy values into booleans
 * for REST/CLI callers before Zod schema validation.
 * @param {unknown} val
 * @returns {boolean}
 */
export function coerceBoolean(val) {
  if (typeof val === 'boolean') {
    return val;
  }
  if (typeof val === 'string') {
    return ['true', 'yes', '1', 'on', 'y'].includes(val.trim().toLowerCase());
  }
  return Boolean(val);
}

export const searchParams = {
  siteNames: z
    .union([
      z
        .string()
        .describe(
          `Comma-separated list of job sites to search. Options: ${SUPPORTED_SITES.join(',')}`,
        ),
      z
        .array(z.string())
        .describe(
          `Array of job sites to search. Options: ${SUPPORTED_SITES.join(',')}`,
        ),
    ])
    .describe(
      `Job sites to search (comma-separated string or array). Options: ${SUPPORTED_SITES.join(', ')}`,
    )
    .default('indeed')
    .transform((val) => {
      if (typeof val === 'string') {
        return val;
      }
      if (Array.isArray(val)) {
        return val.join(',');
      }
      return val;
    })
    .refine(
      (val) => {
        const sites = val.split(',').map((site) => site.trim());
        return sites.every((site) => SUPPORTED_SITES.includes(site));
      },
      {
        message: `Invalid site names. Allowed values: ${SUPPORTED_SITES.join(', ')}`,
      },
    ),
  searchTerm: z
    .string()
    .describe('Search term for jobs')
    .default('software engineer'),
  location: z.string().describe('Location for job search').default('remote'),
  distance: z.number().int().describe('Distance in miles').default(50),
  jobType: z
    .enum(['fulltime', 'parttime', 'internship', 'contract'])
    .nullable()
    .describe('Type of job')
    .default(null),
  googleSearchTerm: z
    .string()
    .nullable()
    .describe('Google specific search term')
    .default(null),
  resultsWanted: z
    .number()
    .int()
    .describe('Number of results wanted')
    .default(20)
    .transform((val) => (val === 0 ? 20 : val)),
  easyApply: z
    .boolean()
    .describe('Filter for jobs that are hosted on the job board site')
    .default(false),
  descriptionFormat: z
    .enum(['markdown', 'html'])
    .describe('Format type of the job descriptions')
    .default('markdown'),
  offset: z
    .number()
    .int()
    .describe('Starts the search from an offset')
    .default(0),
  hoursOld: z
    .number()
    .int()
    .describe('How many hours old the jobs can be')
    .default(72)
    .transform((val) => (val === 0 ? 72 : val)),
  verbose: z
    .number()
    .int()
    .min(0)
    .max(2)
    .describe(
      'Controls verbosity (0=errors only, 1=errors+warnings, 2=all logs)',
    )
    .default(1),
  countryIndeed: z
    .string()
    .describe('Country for Indeed search')
    .default('USA'),
  isRemote: z
    .boolean()
    .describe('Whether to search for remote jobs only')
    .default(false),
  linkedinFetchDescription: z
    .boolean()
    .describe('Whether to fetch full job descriptions on LinkedIn and Glints (slower)')
    .default(false),
  linkedinCompanyIds: z
    .union([
      z.string().describe('Comma-separated list of LinkedIn company IDs'),
      z.array(z.number()).describe('Array of LinkedIn company IDs'),
    ])
    .nullable()
    .describe('Comma-separated string or array of LinkedIn company IDs')
    .default(null)
    .transform((val) => {
      if (typeof val === 'string') {
        return val;
      }
      if (Array.isArray(val)) {
        return val.join(',');
      }
      return val;
    }),
  enforceAnnualSalary: z
    .boolean()
    .describe('Converts wages to annual salary')
    .default(false),
  proxies: z
    .union([
      z.string().describe('Comma-separated list of proxies'),
      z.array(z.string()).describe('Array of proxies'),
    ])
    .nullable()
    .describe('Comma-separated string or array of proxies')
    .default(null)
    .transform((val) => {
      if (typeof val === 'string') {
        return val;
      }
      if (Array.isArray(val)) {
        return val.join(',');
      }
      return val;
    }),
  caCert: z
    .string()
    .nullable()
    .describe('Path to CA Certificate file for proxies')
    .default(null),
  format: z.enum(['json', 'csv']).describe('Output format').default('json'),
  timeout: z
    .number()
    .int()
    .describe('Timeout in milliseconds for the job search process')
    .default(120000),
};
