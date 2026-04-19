export type PythonAgentErrorCode = 'TIMEOUT' | 'HTTP_4XX' | 'HTTP_5XX' | 'NETWORK';

export class PythonAgentError extends Error {
  readonly code: PythonAgentErrorCode;
  readonly retryable: boolean;
  readonly partialResults?: unknown;
  readonly statusCode?: number;

  constructor(opts: {
    message: string;
    code: PythonAgentErrorCode;
    retryable: boolean;
    partialResults?: unknown;
    statusCode?: number;
  }) {
    super(opts.message);
    this.name = 'PythonAgentError';
    this.code = opts.code;
    this.retryable = opts.retryable;
    this.partialResults = opts.partialResults;
    this.statusCode = opts.statusCode;

    // Maintain proper prototype chain in transpiled CommonJS
    Object.setPrototypeOf(this, new.target.prototype);
  }
}
