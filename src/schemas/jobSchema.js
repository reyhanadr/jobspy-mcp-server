/**
 * JobSpy MCP Server - Job Schema Definitions
 *
 * This file contains schema definitions for job search results
 * based on the structure of data returned by JobSpy.
 */

import { z } from 'zod';

// Job Search Result Schema
// Based on JobSpy's schema
export const jobSpySchema = z.object({
  // ID
  id: z.string().nullish().optional(),

  // Job Information
  jobTitle: z.string().nullish().optional(),
  jobSummary: z.string().nullish().optional(),
  description: z.string().nullish().optional(),
  keywords: z.array(z.string()).nullish().optional(),
  requiredSkills: z.array(z.string()).nullish().optional(),
  niceToHaveSkills: z.array(z.string()).nullish().optional(),

  // URLs
  jobUrl: z.string().nullish().optional(),
  jobUrlDirect: z.string().nullish().optional(),

  // Misc Information
  location: z.string().nullish().optional(),
  country: z.string().nullish().optional(),
  state: z.string().nullish().optional(),
  city: z.string().nullish().optional(),
  postalCode: z.string().nullish().optional(),

  // Dates
  datePosted: z
    .string()
    .nullish()
    .optional()
    .describe(
      'ISO 8601 formatted date string (e.g., "2025-04-29T14:30:00.000Z")'
    ),
  jobType: z.string().nullish().optional(),

  // Salary Information
  salary: z.string().nullish().optional(),
  salaryPeriod: z.string().nullish().optional(),
  salarySource: z.string().nullish().optional(),
  salaryCurrency: z.string().nullish().optional(),
  minAmount: z.number().nullish().optional(),
  maxAmount: z.number().nullish().optional(),

  // Job Categorization
  jobs: z.array(z.string()).nullish().optional(),
  isRemote: z.boolean().nullish().optional(),
  jobLevel: z.string().nullish().optional(),
  jobFunction: z.string().nullish().optional(),
  listingType: z.string().nullish().optional(),

  // Experience
  experience: z.string().nullish().optional(),
  experienceRange: z.string().nullish().optional(),

  // Company Information
  companyName: z.string().nullish().optional(),
  companyIndustry: z.string().nullish().optional(),
  companyUrl: z.string().nullish().optional(),
  companyLogo: z.string().nullish().optional(),
  companyUrlDirect: z.string().nullish().optional(),
  companyAddresses: z.string().nullish().optional(),
  companyNumEmployees: z.string().nullish().optional(),
  companyRevenue: z.string().nullish().optional(),
  companyDescription: z.string().nullish().optional(),
  companyRating: z.string().nullish().optional(),
  companyReviewsCount: z.string().nullish().optional(),

  // Additional Information
  postingStatus: z.string().nullish().optional(),
  vacancyCount: z.string().nullish().optional(),
  workFromHomeType: z.string().nullish().optional(),
});

export const jobSearchResultSchema = z.object({
  query: z.object({
    searchTerm: z.string().nullable().optional(),
    location: z.string().nullable().optional(),
    sitesSearched: z.array(z.string()).nullish().optional(),
    date: z.string().nullable().optional(),
    error: z.string().nullable().optional(),
  }),
  count: z.number().nullish().optional(),
  jobs: z.array(jobSpySchema).optional(),
  message: z.string().nullish().optional(),
});
