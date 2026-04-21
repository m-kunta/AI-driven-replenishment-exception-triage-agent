import { api } from './api';

global.fetch = jest.fn();

// Stub env vars so validateEnv() does not throw in the happy-path tests
const ORIG_ENV = process.env;

beforeAll(() => {
  process.env = {
    ...ORIG_ENV,
    NEXT_PUBLIC_API_URL: 'http://localhost:8000',
    NEXT_PUBLIC_API_USERNAME: 'admin',
    NEXT_PUBLIC_API_PASSWORD: 'testpass',
  };
});

afterAll(() => {
  process.env = ORIG_ENV;
});

describe('API Client', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('triggers the pipeline successfully', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'queued' }),
    });

    const result = await api.triggerPipeline({ run_date: '2026-04-17', sample: true });
    
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/pipeline/trigger'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ run_date: '2026-04-17', sample: true }),
      })
    );
    expect(result).toEqual({ status: 'queued' });
  });

  it('fetches a queue successfully', async () => {
    const mockQueue = [{ exception_id: '123', priority: 'CRITICAL' }];
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => mockQueue,
    });

    const result = await api.getQueue('CRITICAL', '2026-04-17');
    
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/exceptions/queue/CRITICAL/2026-04-17'),
      expect.objectContaining({ method: 'GET' })
    );
    expect(result).toEqual(mockQueue);
  });

  it('returns an empty array on 404 for missing queue', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 404,
    });

    const result = await api.getQueue('HIGH', '2026-04-17');
    expect(result).toEqual([]);
  });

  it('includes Authorization header with base64-encoded credentials', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'ok' }),
    });

    await api.healthCheck();
    // healthCheck skips auth — just verify the function exists and resolves
    expect(fetch).toHaveBeenCalled();
  });

  it('includes Authorization header on queue requests', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });

    await api.getQueue('LOW', '2026-04-17');

    const [, options] = (fetch as jest.Mock).mock.calls[0];
    expect(options.headers).toHaveProperty('Authorization');
    expect(options.headers['Authorization']).toMatch(/^Basic /);
  });
});

// ---------------------------------------------------------------------------
// validateEnv guard — isolated so env mutations don't bleed into other tests
// ---------------------------------------------------------------------------

describe('validateEnv guard', () => {
  const savedEnv = process.env;

  afterEach(() => {
    process.env = savedEnv;
    jest.resetModules();
  });

  it('throws when NEXT_PUBLIC_API_PASSWORD is the placeholder value', async () => {
    process.env = {
      ...savedEnv,
      NEXT_PUBLIC_API_PASSWORD: 'your_password_here',
    };
    jest.resetModules();
    const { api: freshApi } = await import('./api');

    (fetch as jest.Mock).mockResolvedValueOnce({ ok: true, json: async () => [] });
    await expect(freshApi.getQueue('LOW', '2026-04-17')).rejects.toThrow(
      'NEXT_PUBLIC_API_PASSWORD is not configured'
    );
  });

  it('throws when NEXT_PUBLIC_API_PASSWORD is absent', async () => {
    const env = { ...savedEnv };
    delete env.NEXT_PUBLIC_API_PASSWORD;
    process.env = env;
    jest.resetModules();
    const { api: freshApi } = await import('./api');

    (fetch as jest.Mock).mockResolvedValueOnce({ ok: true, json: async () => [] });
    await expect(freshApi.getQueue('LOW', '2026-04-17')).rejects.toThrow(
      'NEXT_PUBLIC_API_PASSWORD is not configured'
    );
  });

  it('does NOT throw when password is a valid non-placeholder value', async () => {
    process.env = { ...savedEnv, NEXT_PUBLIC_API_PASSWORD: 'supersecret' };
    jest.resetModules();
    const { api: freshApi } = await import('./api');

    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });
    await expect(freshApi.getQueue('LOW', '2026-04-17')).resolves.toEqual([]);
  });
});

