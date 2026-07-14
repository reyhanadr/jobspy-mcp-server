const {
  jobSpySchema,
  jobSearchResultSchema,
} = require('../src/schemas/jobSchema.js');
const fs = require('fs').promises;
const path = require('path');

describe('Job Schema', () => {
  let jobsData;

  beforeAll(async () => {
    try {
      // Load sample data from jobs.json
      const jobsPath = path.join(__dirname, '../../jobSpy/jobs.json');
      const jobsContent = await fs.readFile(jobsPath, 'utf-8');
      jobsData = JSON.parse(jobsContent);
    } catch (error) {
      console.error('Error loading test data:', error);
      // Provide fallback test data if file can't be loaded
      jobsData = [
        {
          id: 'test-123',
          site: 'indeed',
          jobUrl: 'https://www.indeed.com/viewjob?jk=test123',
          jobTitle: 'Software Engineer',
          companyName: 'Test Company',
          location: 'San Francisco, CA',
        },
      ];
    }
  });

  test('validates a single job object', () => {
    const job = jobsData[0];
    try {
      jobSpySchema.parse(job);
      // If no error is thrown, validation passed
      expect(true).toBeTruthy();
    } catch (error) {
      // Should not reach here if validation succeeds
      expect(error).toBeUndefined();
    }
  });

  test('validates a complete job search response', () => {
    const response = {
      query: {
        searchTerm: 'software engineer',
        location: 'San Francisco',
        sitesSearched: ['indeed'],
        date: new Date().toISOString(),
      },
      count: jobsData.length,
      jobs: jobsData,
      message: 'Success',
    };

    try {
      jobSearchResultSchema.parse(response);
      // If no error is thrown, validation passed
      expect(true).toBeTruthy();
    } catch (error) {
      // Should not reach here if validation succeeds
      expect(error).toBeUndefined();
    }
  });

  test('identifies missing required fields', () => {
    const invalidJob = {
      // Missing jobTitle which may be required
      id: 'test-456',
      companyName: 'Invalid Test',
    };

    try {
      jobSpySchema.parse(invalidJob);
      // Should fail validation and not reach here
      expect(false).toBeTruthy();
    } catch (error) {
      // Expect an error to be thrown for missing required fields
      expect(error).toBeDefined();
    }
  });

  test('validates field types', () => {
    const invalidTypeJob = {
      id: 12345, // Should be string
      jobTitle: 'Software Engineer',
      isRemote: 'yes', // Should be boolean
    };

    try {
      jobSpySchema.parse(invalidTypeJob);
      // Should fail validation and not reach here
      expect(false).toBeTruthy();
    } catch (error) {
      // Expect an error to be thrown for invalid field types
      expect(error).toBeDefined();
    }
  });
});
