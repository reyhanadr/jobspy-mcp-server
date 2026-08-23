import logger from '../logger.js';
import { searchParams } from '../schemas/searchParamsSchema.js';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const JOBSPY_DIR = path.resolve(__dirname, '../../jobspy');

/**
 * Concurrency Gate (Capacity = 1)
 * Under memory constraints, ensures only one Python scraping process runs at a time
 * while keeping the Bun event loop non-blocking for /health and SSE.
 */
class AsyncQueue {
  constructor(concurrency = 1) {
    this.concurrency = concurrency;
    this.running = 0;
    this.queue = [];
  }

  async run(task) {
    if (this.running >= this.concurrency) {
      await new Promise((resolve) => this.queue.push(resolve));
    }
    this.running++;
    try {
      return await task();
    } finally {
      this.running--;
      if (this.queue.length > 0) {
        const next = this.queue.shift();
        next();
      }
    }
  }
}

const jobQueue = new AsyncQueue(1);

/**
 * Execute a child process asynchronously with timeout and streaming output
 * @param {string} executable - Binary path to execute
 * @param {string[]} args - Command arguments
 * @param {object} options - Options (timeout, cwd)
 * @returns {Promise<string>} stdout output
 */
function executeProcess(executable, args, options = {}) {
  return new Promise((resolve, reject) => {
    const { timeout = 120000, cwd = JOBSPY_DIR } = options;

    logger.info(`[spawn] ${executable} ${args.join(' ')} (cwd: ${cwd}, timeout: ${timeout}ms)`);

    const child = spawn(executable, args, {
      cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });

    let stdoutData = '';
    let stderrData = '';
    let isTimedOut = false;

    const timer = setTimeout(() => {
      isTimedOut = true;
      logger.warn(`Process timed out after ${timeout}ms, sending SIGTERM...`);
      child.kill('SIGTERM');
      setTimeout(() => {
        try {
          child.kill('SIGKILL');
        } catch (_) {}
      }, 5000).unref();
    }, timeout);

    child.stdout.on('data', (chunk) => {
      stdoutData += chunk.toString('utf-8');
    });

    child.stderr.on('data', (chunk) => {
      stderrData += chunk.toString('utf-8');
    });

    child.on('error', (err) => {
      clearTimeout(timer);
      reject(new Error(`Failed to spawn process: ${err.message}`));
    });

    child.on('close', (code, signal) => {
      clearTimeout(timer);
      if (isTimedOut) {
        return reject(new Error(`Job search process timed out after ${timeout}ms`));
      }
      if (code !== 0) {
        logger.error(`Process exited with code ${code} (signal: ${signal})`, { stderr: stderrData });
        return reject(new Error(`Job search failed (exit code ${code}): ${stderrData || 'Unknown error'}`));
      }
      resolve(stdoutData);
    });
  });
}

/**
 * Resolve python executable path
 * Checks venv first, then falls back to PATH python
 * @returns {string}
 */
function resolvePythonExecutable() {
  const isWin = process.platform === 'win32';
  const venvPython = isWin
    ? path.join(JOBSPY_DIR, '.venv', 'Scripts', 'python.exe')
    : path.join(JOBSPY_DIR, '.venv', 'bin', 'python');

  if (fs.existsSync(venvPython)) {
    return venvPython;
  }
  return 'python';
}

/**
 * Resolve which runner to use: docker or direct python
 * Priority: JOBSPY_RUNNER env var > auto-detect docker > python
 * @returns {'docker'|'python'}
 */
function resolveRunner() {
  const forced = process.env.JOBSPY_RUNNER?.toLowerCase();
  if (forced === 'docker' || forced === 'uv' || forced === 'python') {
    return forced === 'docker' ? 'docker' : 'python';
  }
  return 'python';
}

/**
 * Build executable and args for spawn
 * @param {'docker'|'python'} runner
 * @param {string[]} args - CLI arguments for main.py
 * @returns {{ executable: string, args: string[] }}
 */
function buildSpawnCommand(runner, args) {
  if (runner === 'docker') {
    const dockerCmd = process.env.DOCKER_CMD || 'docker';
    return {
      executable: dockerCmd,
      args: ['run', '--rm', 'jobspy', ...args],
    };
  }
  return {
    executable: resolvePythonExecutable(),
    args: ['main.py', ...args],
  };
}

/**
 * Build command arguments from parameters
 * @param {object} params - Validated search parameters
 * @returns {string[]} Command line arguments
 */
function buildCommandArgs(params) {
  const args = [];

  if (params.siteNames) {
    args.push('--site_name', params.siteNames);
  }
  if (params.searchTerm) {
    args.push('--search_term', params.searchTerm);
  }
  if (params.location) {
    args.push('--location', params.location);
  }
  if (params.distance !== undefined && params.distance !== null) {
    args.push('--distance', String(params.distance));
  }
  if (params.jobType) {
    args.push('--job_type', params.jobType);
  }
  if (params.googleSearchTerm) {
    args.push('--google_search_term', params.googleSearchTerm);
  }
  if (params.resultsWanted !== undefined && params.resultsWanted !== null) {
    args.push('--results_wanted', String(params.resultsWanted));
  }
  if (params.easyApply) {
    args.push('--easy_apply');
  }
  if (params.descriptionFormat) {
    args.push('--description_format', params.descriptionFormat);
  }
  if (params.offset !== undefined && params.offset !== null) {
    args.push('--offset', String(params.offset));
  }
  if (params.hoursOld !== undefined && params.hoursOld !== null) {
    args.push('--hours_old', String(params.hoursOld));
  }
  if (params.verbose !== undefined && params.verbose !== null) {
    args.push('--verbose', String(params.verbose));
  }
  if (params.countryIndeed) {
    args.push('--country_indeed', params.countryIndeed);
  }
  if (params.isRemote) {
    args.push('--is_remote');
  }
  if (params.linkedinFetchDescription) {
    args.push('--linkedin_fetch_description');
  }
  if (params.linkedinCompanyIds) {
    args.push('--linkedin_company_ids', params.linkedinCompanyIds);
  }
  if (params.enforceAnnualSalary) {
    args.push('--enforce_annual_salary');
  }
  if (params.proxies) {
    args.push('--proxies', params.proxies);
  }
  if (params.caCert) {
    args.push('--ca_cert', params.caCert);
  }
  args.push('--format', params.format || 'json');
  return args;
}

/**
 * Handler for the search_jobs MCP tool
 * @param {object} params - Search parameters
 * @returns {Promise<object>} Search results
 */
export async function searchJobsHandler(params) {
  let stdout;
  try {
    logger.info('Starting job search with parameters', { params });

    // Clean params by removing empty strings and undefined values
    const cleanedParams = {};
    for (const [key, value] of Object.entries(params)) {
      if (value === null || value === undefined || value === '') {
        continue;
      }
      cleanedParams[key] = value;
    }

    logger.info('Cleaned parameters', { cleanedParams });

    const validatedParams = z.object(searchParams).parse(cleanedParams);
    logger.info('Validated parameters', { validatedParams });

    const args = buildCommandArgs(validatedParams);
    const runner = resolveRunner();
    const { executable, args: spawnArgs } = buildSpawnCommand(runner, args);

    const timeout = validatedParams.timeout; // Fixed: use validatedParams.timeout (default 120000ms)
    const cwd = JOBSPY_DIR;

    stdout = await jobQueue.run(() =>
      executeProcess(executable, spawnArgs, { timeout, cwd })
    );

    let parsedData;
    try {
      parsedData = JSON.parse(stdout.trim());
    } catch (parseError) {
      logger.error('Failed to parse output JSON from JobSpy', {
        stdout,
        parseError: parseError.message,
      });
      throw new Error(`Failed to parse JobSpy output: ${parseError.message}`);
    }

    const count = parsedData.count ?? (Array.isArray(parsedData.jobs) ? parsedData.jobs.length : 0);
    const jobs = parsedData.jobs ?? (Array.isArray(parsedData) ? parsedData : []);

    logger.info(`Found jobs: ${count}`);
    return {
      count,
      message: 'Job search completed successfully',
      jobs,
    };
  } catch (error) {
    logger.error('Error in searchJobsHandler', {
      error: error.message,
      stdout,
    });
    throw error;
  }
}

/**
 * Register search_jobs tool with MCP server
 * @param {object} server - McpServer instance
 * @param {object} sseManager - SseManager instance
 */
export const searchJobsTool = (server, sseManager) =>
  server.tool(
    'search_jobs',
    'Search for jobs across various job listing websites',
    searchParams,
    async (params, extra) => {
      let progressInterval;
      try {
        logger.info('Received search_jobs request', { params, extra });

        // Track progress for SSE clients
        if (extra.sessionId && sseManager.hasConnection(extra.sessionId)) {
          let progress = 0;
          progressInterval = setInterval(() => {
            progress += 5;
            if (progress > 90) {
              progress = 90; // Cap at 90% until complete
            }

            sseManager.notificationProgress(
              {
                type: 'progress',
                tool: 'search_jobs',
                progress,
                message: `Searching for jobs (${progress}%)...`,
              },
              extra.sessionId
            );
          }, 2000);
        }

        // Execute job search asynchronously
        const result = await searchJobsHandler(params);

        // Clean up progress interval
        if (progressInterval) {
          clearInterval(progressInterval);

          if (extra.sessionId && sseManager.hasConnection(extra.sessionId)) {
            sseManager.notificationProgress(
              {
                type: 'progress',
                tool: 'search_jobs',
                progress: 100,
                message: 'Job search completed',
              },
              extra.sessionId
            );
          }
        }

        return {
          isError: false,
          content: [
            {
              type: 'text',
              text: JSON.stringify(result, null, 2),
            },
          ],
        };
      } catch (error) {
        if (progressInterval) {
          clearInterval(progressInterval);
        }
        logger.error('Error in search_jobs handler', { error: error.message });
        return {
          isError: true,
          error: {
            message: error.message,
            code: 'INTERNAL_SERVER_ERROR',
          },
        };
      }
    }
  );

