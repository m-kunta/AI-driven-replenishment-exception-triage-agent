import { api } from './api';

global.fetch = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
});

describe('API Client', () => {
  it('triggers the pipeline successfully', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'queued' }),
    });

    const result = await api.triggerPipeline({ run_date: '2026-04-17', sample: true });

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/proxy/pipeline/trigger'),
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
      expect.stringContaining('/api/proxy/exceptions/queue/CRITICAL/2026-04-17'),
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

  it('does not include Authorization header in browser requests', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });

    await api.getQueue('LOW', '2026-04-17');

    const [, options] = (fetch as jest.Mock).mock.calls[0];
    expect(options.headers).not.toHaveProperty('Authorization');
  });

  it('fetches runs successfully', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ run_dates: ['2026-04-17', '2026-04-16'] }),
    });

    const result = await api.getRuns();

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/proxy/runs'),
      expect.objectContaining({ method: 'GET' })
    );
    expect(result).toEqual(['2026-04-17', '2026-04-16']);
  });

  it('returns empty array when getRuns fails', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({ ok: false, status: 500 });
    const result = await api.getRuns();
    expect(result).toEqual([]);
  });

  it('fetches a briefing successfully', async () => {
    const mockBriefing = { run_date: '2026-04-17', content: 'Report...' };
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => mockBriefing,
    });

    const result = await api.getBriefing('2026-04-17');

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/proxy/briefing/2026-04-17'),
      expect.objectContaining({ method: 'GET' })
    );
    expect(result).toEqual(mockBriefing);
  });

  it('returns null on 404 for missing briefing', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({ ok: false, status: 404 });
    const result = await api.getBriefing('2026-04-17');
    expect(result).toBeNull();
  });

  it('checks health via proxy', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'ok' }),
    });

    await api.healthCheck();

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/proxy/health')
    );
  });

  it('submits an override through the proxy', async () => {
    const payload = {
      exception_id: 'EXC-001',
      run_date: '2026-04-24',
      enriched_input_snapshot: { exception_id: 'EXC-001' },
      override_priority: 'HIGH' as const,
    };
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 1, status: 'pending' }),
    });

    const result = await api.submitOverride(payload);

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/proxy/overrides'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload),
      })
    );
    expect(result).toEqual({ id: 1, status: 'pending' });
  });

  it('fetches pending overrides successfully', async () => {
    const pending = [{ id: 11, exception_id: 'EXC-001' }];
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => pending,
    });

    const result = await api.getPendingOverrides();

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/proxy/overrides/pending'),
      expect.objectContaining({ method: 'GET' })
    );
    expect(result).toEqual(pending);
  });

  it('approves an override through the proxy', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'approved', override_id: 11 }),
    });

    const result = await api.approveOverride(11);

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/proxy/overrides/11/approve'),
      expect.objectContaining({ method: 'POST' })
    );
    expect(result).toEqual({ status: 'approved', override_id: 11 });
  });

  it('rejects an override with an optional reason', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'rejected', override_id: 11 }),
    });

    const result = await api.rejectOverride(11, 'Needs more evidence');

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/proxy/overrides/11/reject'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ reason: 'Needs more evidence' }),
      })
    );
    expect(result).toEqual({ status: 'rejected', override_id: 11 });
  });
});
