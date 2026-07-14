import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js';
import logger from './logger.js';

/**
 * Manages SSE server transports for multiple client connections
 */
class SseManager {
  /**
   * @type {Object.<string, SSEServerTransport>}
   * Storage for active transports mapped by their sessionId
   */
  transports = {};

  /**
   * @type McpServer
   */
  mcpServer;

  /**
   * Storage for progress tokens by sessionId
   */
  progressTokens = {};

  /**
   * Storage for tool calls by connectionId and toolCallId
   */
  toolCalls = {};

  constructor(server) {
    this.mcpServer = server;
  }

  /**
   * Adds a new SSE transport for a client
   * @param {string} sendPath - Path for client to send messages to
   * @param {Response} res - Express response object
   * @returns {SSEServerTransport} The created transport
   */
  createTransport(sendPath, res) {
    const transport = new SSEServerTransport(sendPath, res);
    this.transports[transport.sessionId] = transport;
    return transport;
  }

  /**
   * Gets a transport by sessionId
   * @param {string} sessionId - Session ID
   * @returns {SSEServerTransport|undefined} The transport or undefined if not found
   */
  getTransport(req) {
    const sessionId = req.query.sessionId;
    this.progressTokens[sessionId] = req.body?.params?._meta?.progressToken;
    return this.transports[sessionId];
  }

  /**
   * Removes a transport when client disconnects
   * @param {string} sessionId - Session ID to remove
   */
  removeTransport(sessionId) {
    if (this.transports[sessionId]) {
      delete this.transports[sessionId];
      delete this.progressTokens[sessionId];
      logger.info(`Removed transport for session: ${sessionId}`);
      return true;
    }
    return false;
  }

  /**
   * Sends an update to all connected clients
   * @param {object} message - Message to broadcast
   */
  async notificationProgress(message, sessionId) {
    const clients = Object.values(this.transports);
    if (clients.length === 0) {return;}
    await this.mcpServer.server.notification({
      method: 'notifications/progress',
      params: {
        ...message,
        progressToken: this.progressTokens[sessionId],
      },
    });
  }

  /**
   * Checks if there are any active connections
   * @returns {boolean} True if there are active connections
   */
  hasConnection(sessionId) {
    return this.transports[sessionId];
  }

  /**
   * Process a stream event from a model
   * @param {Object} event - The event to process
   * @param {string} connectionId - The connection ID
   * @param {string} toolCallId - The tool call ID
   */
  handleStreamEvent(event, connectionId, toolCallId) {
    if (!event || !event.choices || !event.choices[0]) {
      return;
    }

    const delta = event.choices[0].delta;
    if (delta && delta.tool_calls && delta.tool_calls[0]) {
      const toolCall = delta.tool_calls[0];
      
      // Store or update the tool call in our cache
      if (!this.toolCalls[connectionId]) {
        this.toolCalls[connectionId] = {};
      }
      
      if (!this.toolCalls[connectionId][toolCallId]) {
        this.toolCalls[connectionId][toolCallId] = {
          function: {
            name: '',
            arguments: '',
          },
          index: toolCall.index,
          id: toolCallId,
        };
      }

      const currentToolCall = this.toolCalls[connectionId][toolCallId];

      if (toolCall.function) {
        if (toolCall.function.name) {
          currentToolCall.function.name = toolCall.function.name;
        }
        
        if (toolCall.function.arguments) {
          currentToolCall.function.arguments += toolCall.function.arguments;
        }
      }
    }
  }
}

export default SseManager;
