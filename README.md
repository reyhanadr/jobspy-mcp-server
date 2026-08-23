# JobSpy MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that lets AI assistants like Claude search for jobs across multiple job listing platforms using the [JobSpy](https://github.com/Bunsly/JobSpy) tool.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Runtime: Bun](https://img.shields.io/badge/runtime-Bun-14151a.svg)
![Protocol: MCP](https://img.shields.io/badge/Protocol-MCP-000000.svg)

## Why this project?

- **Search multiple job boards at once** — Indeed, LinkedIn, ZipRecruiter, Glassdoor, Google, Bayt, and Naukri
- **Structured results for AI** — clean JSON with camelCase keys and ISO-8601 dates that models and applications can consume directly
- **Fine-grained filtering** — keywords, location, distance, job type, posting recency, remote-only, salary normalization, and more
- **Two transports** — stdio for desktop clients like Claude Desktop, plus Server-Sent Events (SSE) for web apps with live progress updates
- **Flexible execution** — runs JobSpy locally with `uv` + Python or inside Docker; the runner is auto-detected (or forced with `JOBSPY_RUNNER`)
- **Ready-made prompts** — bundled prompts for extracting search parameters, job recommendations, and resume feedback
- **Easy deployment** — a multi-stage `Dockerfile` and `docker-compose.yml` are included

## How it works

```mermaid
flowchart LR
    A[MCP Client<br/>Claude Desktop / web app] -->|stdio or SSE| B[JobSpy MCP Server<br/>Bun/Node + Express + MCP SDK]
    B -->|"uv run python main.py" or docker| C[JobSpy runner]
    C --> D[Indeed / LinkedIn / Glassdoor / ...]
    D -->|JSON| B
    B -->|count + jobs| A
```

The server registers an MCP **tool** (`search_jobs`) and three **prompts**. When the tool is called, it builds a JobSpy CLI command, runs it with the selected runner (`uv` + Python or Docker), parses the JSON output, normalizes field names to camelCase and dates to ISO-8601, and returns the results to the client.

## Prerequisites

- [Bun](https://bun.sh/) (or Node.js 18+) — JavaScript runtime & package manager
- [uv](https://docs.astral.sh/uv/) — fast Python package & project manager
- Python 3.12+ (installed and managed via `uv`)
- [Docker](https://www.docker.com/) + Docker Compose (optional — only needed for the containerized run or the `docker` runner)

## Installation

```bash
# Clone the repository
git clone https://github.com/borgius/jobspy-mcp-server.git
cd jobspy-mcp-server

# Install Node.js/Bun dependencies
bun install

# Set up the Python environment for JobSpy (used by the "uv" runner)
cd jobspy
uv venv
uv pip install -r requirements.txt
cd ..

# Optional: copy the example env file
cp .env.example .env
```

## Configuration

Configuration is read from environment variables or a `.env` file in the project root.

### Environment variables

| Variable        | Description                                                          | Default    |
|-----------------|----------------------------------------------------------------------|------------|
| `JOBSPY_PORT`   | Port for the HTTP/SSE server                                         | `9423`     |
| `JOBSPY_HOST`   | Host to bind the HTTP/SSE server to                                  | `0.0.0.0`  |
| `ENABLE_SSE`    | Set to `true` to enable the SSE/HTTP transport (`false` uses stdio)  | `false`    |
| `JOBSPY_RUNNER` | Force the JobSpy runner: `python`, `uv`, or `docker`                 | `python`   |
| `DOCKER_CMD`    | Docker command used by the `docker` runner                           | `docker`   |

Example `.env`:

```
JOBSPY_RUNNER=python
JOBSPY_HOST=0.0.0.0
JOBSPY_PORT=9423
ENABLE_SSE=true
```

### How the JobSpy runner is selected

1. If `JOBSPY_RUNNER` is set to `docker`, `python`, or `uv`, that runner is used.
2. Otherwise the server checks whether Docker is available **and** a `jobspy` image exists; if so, it uses `docker`.
3. Otherwise it runs Python directly with the virtual environment inside the `jobspy/` folder.

## Usage

### Starting the server

```bash
bun start            # runs: node src/index.js
# or, if you only have Bun installed:
bun run src/index.js
```

With the default configuration (`ENABLE_SSE=false`) the server starts in **stdio** mode, ideal for MCP desktop clients. With `ENABLE_SSE=true` it starts the HTTP server on port `9423`.

### Connecting with Claude Desktop

Add the following to your Claude Desktop configuration file (typically at `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "jobspy": {
      "command": "bun",
      "args": ["run", "/path/to/jobspy-mcp-server/src/index.js"],
      "env": {
        "ENABLE_SSE": "false"
      }
    }
  }
}
```

Then ask Claude something like:

> I need to find senior software engineer jobs in Boston posted in the last 24 hours on both LinkedIn and Indeed.

### Using with web clients (SSE transport)

Start the server with SSE enabled:

```bash
ENABLE_SSE=true bun start
```

The server exposes HTTP endpoints that let web applications talk to the MCP server:

| Endpoint     | Method | Description                                                                                                |
|--------------|--------|------------------------------------------------------------------------------------------------------------|
| `/sse`       | GET    | Opens a Server-Sent Events stream. Each connection receives an `endpoint` event with a session messages URL |
| `/messages`  | POST   | Accepts MCP JSON-RPC requests (tool calls, etc.) for a given `sessionId`                                    |
| `/api`       | POST   | Simplified REST endpoint that runs a job search and returns the results directly                           |
| `/health`    | GET    | Health check — returns `{ "status": "ok" }`                                                                |

Example browser client:

```javascript
// 1. Connect to the SSE endpoint
const eventSource = new EventSource('http://localhost:9423/sse');

// 2. The MCP SDK sends an "endpoint" event with the messages URL for this session
eventSource.addEventListener('endpoint', (event) => {
  sendSearchRequest(event.data); // e.g. http://localhost:9423/messages?sessionId=...
});

// 3. Listen for server messages (results, progress, etc.)
eventSource.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Server message:', message);
};

// 4. Send an MCP tool call
async function sendSearchRequest(messagesUrl) {
  await fetch(messagesUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      method: 'tools/call',
      params: {
        name: 'search_jobs',
        arguments: {
          searchTerm: 'software engineer',
          location: 'San Francisco, CA',
          siteNames: 'indeed,linkedin',
          resultsWanted: 10
        }
      }
    })
  });
}
```

> **Note:** Tool parameters use **camelCase** keys (`searchTerm`, `siteNames`, `resultsWanted`, …) — the same names exposed by the tool schema.

### Quick REST test

```bash
curl -X POST "http://localhost:9423/api" \
  -H "Content-Type: application/json" \
  -d '{
    "searchTerm": "software engineer",
    "location": "San Francisco, CA",
    "siteNames": "indeed,linkedin",
    "resultsWanted": 10,
    "format": "json"
  }'
```

## Tools

### `search_jobs`

Searches for jobs across one or more job listing websites.

**Parameters** (all keys are camelCase):

| Parameter                | Type              | Description                                                          | Default            |
|--------------------------|-------------------|----------------------------------------------------------------------|--------------------|
| `siteNames`              | string \| string[] | Sites to search: `indeed,linkedin,zip_recruiter,glassdoor,google,bayt,naukri` | `"indeed"` |
| `searchTerm`             | string            | Search term for jobs                                                 | `"software engineer"` |
| `location`               | string            | Job location                                                         | `"remote"`         |
| `distance`               | integer           | Search radius in miles                                               | `50`               |
| `jobType`                | string            | `fulltime`, `parttime`, `internship`, or `contract`                  | `null`             |
| `googleSearchTerm`       | string            | Google-specific search term                                          | `null`             |
| `resultsWanted`          | integer           | Number of results to retrieve per site                               | `20`               |
| `easyApply`              | boolean           | Only jobs hosted on the job board site                               | `false`            |
| `descriptionFormat`      | string            | `markdown` or `html`                                                 | `"markdown"`       |
| `offset`                 | integer           | Start the search from an offset                                      | `0`                |
| `hoursOld`               | integer           | Only jobs posted within this many hours                              | `72`               |
| `verbose`                | integer           | `0`=errors only, `1`=+warnings, `2`=all logs                         | `1`                |
| `countryIndeed`          | string            | Country for Indeed search                                            | `"USA"`            |
| `isRemote`               | boolean           | Search for remote jobs only                                          | `false`            |
| `linkedinFetchDescription` | boolean         | Fetch LinkedIn job descriptions (slower)                             | `false`            |
| `linkedinCompanyIds`     | string \| number[] | Restrict LinkedIn results to company IDs                             | `null`             |
| `enforceAnnualSalary`    | boolean           | Normalize wages to an annual salary                                  | `false`            |
| `proxies`                | string \| string[] | Comma-separated list of proxies                                      | `null`             |
| `caCert`                 | string            | Path to a CA certificate for proxies                                 | `null`             |
| `format`                 | string            | Output format: `json` or `csv`                                       | `"json"`           |
| `timeout`                | integer           | Timeout in milliseconds for the search process                       | `120000`           |

**Response shape:**

```json
{
  "count": 42,
  "message": "Job search completed successfully",
  "jobs": [
    {
      "id": "8d1d5f...",
      "site": "indeed",
      "jobUrl": "https://www.indeed.com/viewjob?jk=...",
      "jobTitle": "Senior Software Engineer",
      "companyName": "Example Corp",
      "location": "San Francisco, CA",
      "datePosted": "2026-08-20T00:00:00.000Z"
    }
  ]
}
```

Dates are normalized to ISO-8601 and all field names are camelCase, so the output is easy for AI models to consume and for applications to map.

## Prompts

The server also registers ready-to-use prompts:

| Prompt                  | Description                                                      | Inputs                                                                                          |
|-------------------------|------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| `search_jobs`           | Extracts job search parameters from a natural-language query     | `query`                                                                                         |
| `job_recommendations`   | Generates personalized job recommendations from a candidate profile | `skills`, `experienceLevel`, `preferredLocation`, `jobSeekerInterests`, `jobType`             |
| `resume_feedback`       | Provides structured feedback on a resume for a target role/industry | `resumeText`, `targetRole`, `targetIndustry`, `experienceLevel`                               |

## Docker Support

A multi-stage [`Dockerfile`](./Dockerfile) (Bun + Python 3.12 via uv) and a [`docker-compose.yml`](./docker-compose.yml) are included:

```bash
# Build & start (SSE enabled, port 9423)
docker compose up --build -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

Compose reads configuration from `.env` (with defaults), e.g.:

```
ENABLE_SSE=true
JOBSPY_RUNNER=python
JOBSPY_HOST=0.0.0.0
JOBSPY_PORT=9423
```

To use the `docker` runner instead of `python`, build the JobSpy image first and set `JOBSPY_RUNNER=docker`:

```bash
docker build -t jobspy jobspy/
```

## Development

### Running in development mode

```bash
bun run dev
```

### Linting

```bash
bun run lint        # or: npm run lint
bun run lint:fix    # auto-fix
```

### Running tests

```bash
bun test
```

Runs the schema validation tests in `tests/`.

### Testing with MCP Inspector

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) lets you interactively test and debug your MCP server:

```bash
# Run the inspector against your server (stdio)
bunx @modelcontextprotocol/inspector -e ENABLE_SSE=false --cwd "C:\path-to-project\jobspy-mcp-server" bun run "C:\path-to-project\jobspy-mcp-server\src\index.js"
```

This opens a browser UI where you can:

- List available tools, prompts, and resources
- Invoke `search_jobs` with custom parameters and see responses
- Inspect JSON-RPC messages between client and server
- Debug connection and transport issues

### Testing SSE with MCP Inspector

1. Enable SSE and start the server:

   ```bash
   ENABLE_SSE=true bun run src/index.js
   ```

   The server listens at `http://localhost:9423/sse`.

2. In a second terminal, connect the Inspector to the SSE endpoint:

   ```bash
   bunx @modelcontextprotocol/inspector --server-url http://localhost:9423/sse
   ```

   This opens the Inspector web UI connected over SSE (the `/sse` path is auto-detected as SSE transport). For a scriptable command-line client, add `--cli`:

   ```bash
   bunx @modelcontextprotocol/inspector --cli --server-url http://localhost:9423/sse --method tools/list
   ```

> **Note:** Current Inspector versions point at a running server with `--server-url`. Older versions used `--transport sse --url <url>` instead.

## Project structure

```
├── src/
│   ├── index.js                 # Entry point: MCP server + transports
│   ├── logger.js                # Winston logging
│   ├── sseManager.js            # SSE transport/session management
│   ├── schemas/                 # Zod schemas for tools
│   ├── prompts/                 # Prompt definitions
│   └── tools/                   # Tool definitions & handlers
├── jobspy/                      # Python side: JobSpy CLI wrapper
│   ├── main.py
│   └── requirements.txt
├── tests/                       # Schema tests + api.http
├── Dockerfile                   # Multi-stage Bun + Python image
└── docker-compose.yml
```

## Getting help

- Open an [issue](https://github.com/borgius/jobspy-mcp-server/issues) on GitHub for bugs or feature requests
- See the [JobSpy documentation](https://github.com/Bunsly/JobSpy) for search capabilities and platform coverage
- See the [MCP documentation](https://modelcontextprotocol.io) for the protocol and SDK

## Contributing

Contributions are welcome! Please:

1. Fork the repository and create a feature branch
2. Follow the existing code style (run `bun run lint`)
3. Add tests for new functionality where possible
4. Open a pull request with a clear description of your changes

## License

This project is licensed under the [MIT License](https://opensource.org/licenses/MIT).
