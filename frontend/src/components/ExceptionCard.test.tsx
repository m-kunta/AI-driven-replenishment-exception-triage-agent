import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import ExceptionCard from './ExceptionCard';
import { TriageResult } from '../lib/api';

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
    render(<ExceptionCard exception={minimal} />);
    expect(screen.getByText('LOW')).toBeInTheDocument();
  });
});
