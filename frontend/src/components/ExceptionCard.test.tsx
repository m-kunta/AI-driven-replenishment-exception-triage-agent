import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import ExceptionCard from './ExceptionCard';
import { TriageResult, ActionRecord, api } from '../lib/api';

jest.mock('../lib/api', () => {
  const actual = jest.requireActual('../lib/api');
  return {
    ...actual,
    api: {
      ...actual.api,
      getActions: jest.fn(),
      retryAction: jest.fn(),
      submitAction: jest.fn(),
    },
  };
});

const mockGetActions = api.getActions as jest.MockedFunction<typeof api.getActions>;
const mockRetryAction = api.retryAction as jest.MockedFunction<typeof api.retryAction>;
const mockSubmitAction = api.submitAction as jest.MockedFunction<typeof api.submitAction>;

// Default: no existing actions — keeps all non-action tests clean.
beforeEach(() => {
  mockGetActions.mockResolvedValue([]);
});

const makeActionRecord = (overrides: Partial<ActionRecord> = {}): ActionRecord => ({
  request_id: 'req-1',
  exception_id: 'EXC-12345-abcd',
  run_date: '2026-04-25',
  action_type: 'CREATE_REVIEW',
  requested_by: 'admin',
  requested_by_role: 'analyst',
  payload: {},
  status: 'completed',
  created_at: '2026-04-25T00:00:00Z',
  updated_at: '2026-04-25T00:00:00Z',
  ...overrides,
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const base: TriageResult = {
  exception_id: 'EXC-12345-abcd',
  priority: 'CRITICAL',
  confidence: 'HIGH',
  root_cause: 'Vendor delivery delayed by 3 days.',
  recommended_action: 'Expedite next shipment.',
  financial_impact_statement: 'High risk of stockout.',
  planner_brief: 'Brief description.',
  compounding_risks: [],
  missing_data_flags: [],
  phantom_flag: false,
  item_name: 'Premium Oat Milk',
  store_name: 'NYC Flagship',
  store_tier: 1,
  est_lost_sales_value: 12500,
  promo_active: true,
  dc_inventory_days: 14,
  vendor_fill_rate_90d: 0.887,
};

const minimal: TriageResult = {
  exception_id: 'EXC-MIN-0001',
  priority: 'LOW',
  confidence: 'LOW',
  root_cause: 'Minor variance.',
  recommended_action: 'Monitor.',
  financial_impact_statement: 'Negligible.',
  planner_brief: '',
  compounding_risks: [],
  missing_data_flags: [],
  phantom_flag: false,
};

// ---------------------------------------------------------------------------
// Core details
// ---------------------------------------------------------------------------

describe('ExceptionCard — core details', () => {
  it('renders item name when provided', () => {
    render(<ExceptionCard exception={base} />);
    expect(screen.getByText('Premium Oat Milk')).toBeInTheDocument();
  });

  it('falls back to item_id when item_name is absent', () => {
    render(<ExceptionCard exception={{ ...minimal, item_id: 'ITEM-9988' }} />);
    expect(screen.getByText('ITEM-9988')).toBeInTheDocument();
  });

  it('shows "Unknown Item" when neither item_name nor item_id exist', () => {
    render(<ExceptionCard exception={minimal} />);
    expect(screen.getByText('Unknown Item')).toBeInTheDocument();
  });

  it('renders store name with tier', () => {
    render(<ExceptionCard exception={base} />);
    expect(screen.getByText('Store: NYC Flagship (Tier 1)')).toBeInTheDocument();
  });

  it('renders store_id when store_name is absent', () => {
    render(<ExceptionCard exception={{ ...minimal, store_id: 'STR-099' }} />);
    expect(screen.getByText(/STR-099/)).toBeInTheDocument();
  });

  it('does not show tier when store_tier is absent', () => {
    render(<ExceptionCard exception={{ ...minimal, store_name: 'Test Store' }} />);
    expect(screen.getByText('Store: Test Store')).toBeInTheDocument();
    expect(screen.queryByText(/Tier/)).not.toBeInTheDocument();
  });

  it('renders exception_id short form in the footer', () => {
    render(<ExceptionCard exception={base} />);
    // exception_id is 'EXC-12345-abcd' — split('-')[0] = 'EXC'
    expect(screen.getByText('ID: EXC')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// AI reasoning section
// ---------------------------------------------------------------------------

describe('ExceptionCard — AI reasoning', () => {
  it('renders root_cause', () => {
    render(<ExceptionCard exception={base} />);
    expect(screen.getByText('Vendor delivery delayed by 3 days.')).toBeInTheDocument();
  });

  it('renders recommended_action', () => {
    render(<ExceptionCard exception={base} />);
    expect(screen.getByText('Expedite next shipment.')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Priority badge — all four priorities
// ---------------------------------------------------------------------------

describe('ExceptionCard — priority badge', () => {
  const priorities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const;

  priorities.forEach((priority) => {
    it(`renders ${priority} priority badge`, () => {
      render(<ExceptionCard exception={{ ...minimal, priority }} />);
      expect(screen.getByText(priority)).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Financial impact
// ---------------------------------------------------------------------------

describe('ExceptionCard — financial impact', () => {
  it('renders formatted lost sales value', () => {
    render(<ExceptionCard exception={base} />);
    expect(screen.getByText('$12,500')).toBeInTheDocument();
  });

  it('does not render financial block when est_lost_sales_value is absent', () => {
    render(<ExceptionCard exception={minimal} />);
    expect(screen.queryByText('Est. Lost Sales')).not.toBeInTheDocument();
  });

  it('does not render financial block when est_lost_sales_value is zero', () => {
    render(<ExceptionCard exception={{ ...minimal, est_lost_sales_value: 0 }} />);
    expect(screen.queryByText('Est. Lost Sales')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Phantom flag
// ---------------------------------------------------------------------------

describe('ExceptionCard — phantom flag', () => {
  it('shows PHANTOM DETECTED badge when phantom_flag is true', () => {
    render(<ExceptionCard exception={{ ...base, phantom_flag: true }} />);
    expect(screen.getByText('PHANTOM DETECTED')).toBeInTheDocument();
  });

  it('does not show PHANTOM DETECTED badge when phantom_flag is false', () => {
    render(<ExceptionCard exception={base} />);
    expect(screen.queryByText('PHANTOM DETECTED')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Footer metadata
// ---------------------------------------------------------------------------

describe('ExceptionCard — footer metadata', () => {
  it('shows Active Promo indicator when promo_active is true', () => {
    render(<ExceptionCard exception={base} />);
    expect(screen.getByText('Active Promo')).toBeInTheDocument();
  });

  it('does not show Active Promo when promo_active is false', () => {
    render(<ExceptionCard exception={{ ...base, promo_active: false }} />);
    expect(screen.queryByText('Active Promo')).not.toBeInTheDocument();
  });

  it('shows DC supply days when dc_inventory_days is provided', () => {
    render(<ExceptionCard exception={base} />);
    expect(screen.getByText('DC Supply: 14d')).toBeInTheDocument();
  });

  it('does not show DC supply when dc_inventory_days is absent', () => {
    render(<ExceptionCard exception={minimal} />);
    expect(screen.queryByText(/DC Supply/)).not.toBeInTheDocument();
  });

  it('shows vendor fill rate as percentage', () => {
    render(<ExceptionCard exception={base} />);
    expect(screen.getByText('Vendor Fill: 88.7%')).toBeInTheDocument();
  });

  it('does not show vendor fill rate when absent', () => {
    render(<ExceptionCard exception={minimal} />);
    expect(screen.queryByText(/Vendor Fill/)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Minimal exception — no optional fields should cause a crash
// ---------------------------------------------------------------------------

describe('ExceptionCard — minimal exception (no optional fields)', () => {
  it('renders without crashing when only required fields are present', () => {
    expect(() => render(<ExceptionCard exception={minimal} />)).not.toThrow();
  });

  it('still renders priority badge for minimal exception', () => {
    render(<ExceptionCard exception={minimal} runDate="2026-04-23" />);
    expect(screen.getByText('LOW')).toBeInTheDocument();
  });
});

describe('ExceptionCard — override flow', () => {
  it('opens the override modal from the card action', () => {
    render(<ExceptionCard exception={base} runDate="2026-04-23" />);
    fireEvent.click(screen.getByRole('button', { name: /override/i }));
    expect(screen.getByRole('dialog', { name: /submit override/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Action flow
// ---------------------------------------------------------------------------

describe('ExceptionCard — action flow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetActions.mockResolvedValue([]);
  });

  it('renders the Take Action button', () => {
    render(<ExceptionCard exception={base} runDate="2026-04-25" actorRole="analyst" />);
    expect(screen.getByRole('button', { name: /take action/i })).toBeInTheDocument();
  });

  it('Take Action button is disabled while actorRole is null (role fetch in flight)', () => {
    render(<ExceptionCard exception={base} runDate="2026-04-25" actorRole={null} />);
    expect(screen.getByRole('button', { name: /take action/i })).toBeDisabled();
  });

  it('Take Action button is enabled once actorRole resolves', () => {
    render(<ExceptionCard exception={base} runDate="2026-04-25" actorRole="analyst" />);
    expect(screen.getByRole('button', { name: /take action/i })).not.toBeDisabled();
  });

  it('opens the action modal when Take Action is clicked', () => {
    render(<ExceptionCard exception={base} runDate="2026-04-25" actorRole="analyst" />);
    fireEvent.click(screen.getByRole('button', { name: /take action/i }));
    expect(screen.getByRole('button', { name: /confirm action/i })).toBeInTheDocument();
  });

  it('loads and renders existing actions on mount', async () => {
    const record = makeActionRecord({ status: 'completed' });
    mockGetActions.mockResolvedValue([record]);

    render(<ExceptionCard exception={base} runDate="2026-04-25" />);

    expect(await screen.findByText('CREATE_REVIEW')).toBeInTheDocument();
    expect(screen.getByText('by admin')).toBeInTheDocument();
    expect(screen.getByText('completed')).toBeInTheDocument();
  });

  it('shows no action history section when there are no actions', async () => {
    mockGetActions.mockResolvedValue([]);
    render(<ExceptionCard exception={base} runDate="2026-04-25" />);

    await waitFor(() => expect(mockGetActions).toHaveBeenCalled());
    expect(screen.queryByText('Action History')).not.toBeInTheDocument();
  });

  it('shows a soft backend warning instead of crashing when action history fails to load', async () => {
    mockGetActions.mockRejectedValue(
      new Error("Backend is not running. Start it with `bash scripts/dev.sh` after setting API_PASSWORD in .env.")
    );

    render(<ExceptionCard exception={base} runDate="2026-04-25" actorRole="analyst" />);

    expect(
      await screen.findByText(/action history is unavailable until the backend is running/i)
    ).toBeInTheDocument();
  });

  it('renders queued status badge without a Retry button', async () => {
    mockGetActions.mockResolvedValue([
      makeActionRecord({ request_id: 'req-q', status: 'queued' }),
    ]);

    render(<ExceptionCard exception={base} runDate="2026-04-25" />);

    expect(await screen.findByText('queued')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
  });

  it('shows Retry button only for failed actions', async () => {
    mockGetActions.mockResolvedValue([
      makeActionRecord({ request_id: 'req-ok', status: 'completed' }),
      makeActionRecord({ request_id: 'req-fail', status: 'failed' }),
    ]);

    render(<ExceptionCard exception={base} runDate="2026-04-25" />);

    await screen.findByText('completed');
    const retryButtons = screen.getAllByRole('button', { name: /retry/i });
    expect(retryButtons).toHaveLength(1);
  });

  it('calls retryAction and updates the record in-place on retry', async () => {
    const failed = makeActionRecord({ request_id: 'req-fail', status: 'failed' });
    const retried = makeActionRecord({ request_id: 'req-fail', status: 'completed' });
    mockGetActions.mockResolvedValue([failed]);
    mockRetryAction.mockResolvedValue(retried);

    render(<ExceptionCard exception={base} runDate="2026-04-25" />);

    fireEvent.click(await screen.findByRole('button', { name: /retry/i }));

    await waitFor(() => {
      expect(mockRetryAction).toHaveBeenCalledWith('req-fail');
      expect(screen.queryByText('failed')).not.toBeInTheDocument();
      expect(screen.getByText('completed')).toBeInTheDocument();
    });
  });

  it('passes actorRole=planner through to the action modal, exposing planner-only options', () => {
    render(<ExceptionCard exception={base} runDate="2026-04-25" actorRole="planner" />);
    fireEvent.click(screen.getByRole('button', { name: /take action/i }));

    expect(screen.getByRole('option', { name: /store check/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /vendor follow-up/i })).toBeInTheDocument();
  });

  it('prepends submitted action to history and shows success message', async () => {
    mockGetActions.mockResolvedValue([]);
    const newRecord = makeActionRecord({ request_id: 'req-new', action_type: 'DEFER', status: 'completed' });
    mockSubmitAction.mockResolvedValue(newRecord);

    render(<ExceptionCard exception={base} runDate="2026-04-25" actorRole="analyst" />);
    fireEvent.click(screen.getByRole('button', { name: /take action/i }));

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'DEFER' } });
    fireEvent.click(screen.getByRole('button', { name: /confirm action/i }));

    await waitFor(() => {
      expect(screen.getByText(/DEFER.*queued successfully/i)).toBeInTheDocument();
      expect(screen.getByText('DEFER')).toBeInTheDocument();
    });
  });
});
