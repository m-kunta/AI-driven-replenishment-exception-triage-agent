import { api } from './api';

global.fetch = jest.fn();

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
});
