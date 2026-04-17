import React from 'react';
import { render, screen } from '@testing-library/react';
import ExceptionCard from './ExceptionCard';
import { TriageResult } from '../lib/api';

describe('ExceptionCard Component', () => {
  const mockException: TriageResult = {
    exception_id: 'EXC-12345',
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
  };

  it('renders the core exception details', () => {
    render(<ExceptionCard exception={mockException} />);
    
    expect(screen.getByText('Premium Oat Milk')).toBeInTheDocument();
    expect(screen.getByText('Store: NYC Flagship (Tier 1)')).toBeInTheDocument();
    expect(screen.getByText('CRITICAL')).toBeInTheDocument();
  });

  it('renders the financial impact when provided', () => {
    render(<ExceptionCard exception={mockException} />);
    expect(screen.getByText('$12,500')).toBeInTheDocument();
  });

  it('renders phantom flag when phantom_flag is true', () => {
    const phantomException = { ...mockException, phantom_flag: true };
    render(<ExceptionCard exception={phantomException} />);
    
    expect(screen.getByText('PHANTOM DETECTED')).toBeInTheDocument();
  });

  it('renders AI reasoning', () => {
    render(<ExceptionCard exception={mockException} />);
    
    expect(screen.getByText('Vendor delivery delayed by 3 days.')).toBeInTheDocument();
    expect(screen.getByText('Expedite next shipment.')).toBeInTheDocument();
  });
});
