/**
 * Prototype-only mock data.
 * These values are used to develop the frontend and are not verified
 * Montgomery County crash statistics.
 */
import type { SourcesResponse } from '@/types/sources'

export const mockSourcesResponse: SourcesResponse = {
  sources: [
    {
      id: 'crash-incidents',
      title: 'Crash Incidents Dataset',
      description: 'Police-reported crashes on county roads including severity, location, and conditions.',
      icon: 'car',
      refreshCadence: 'Monthly',
      lastUpdated: '2025-05-15',
      type: 'dataset',
    },
    {
      id: 'drivers',
      title: 'Drivers Dataset',
      description: 'Licensed driver counts and demographics from MVA for Montgomery County.',
      icon: 'users',
      refreshCadence: 'Quarterly',
      lastUpdated: '2025-04-30',
      type: 'dataset',
    },
    {
      id: 'non-motorists',
      title: 'Non-Motorists Dataset',
      description: 'Pedestrian and cyclist exposure estimates and infrastructure inventory.',
      icon: 'footprints',
      refreshCadence: 'Quarterly',
      lastUpdated: '2025-04-30',
      type: 'dataset',
    },
    {
      id: 'vision-zero-reports',
      title: 'Vision Zero Reports',
      description: 'County Vision Zero Action Plan updates and annual progress reports.',
      icon: 'fileText',
      refreshCadence: 'Annually',
      lastUpdated: '2025-03-31',
      type: 'report',
    },
  ],
  methodologySteps: [
    { step: 1, title: 'Understand the question.', description: 'We clarify what you want to know and where.' },
    { step: 2, title: 'Check county data.', description: 'We look at the best matching public datasets.' },
    { step: 3, title: 'Read public reports.', description: 'We review relevant county plans and reports.' },
    { step: 4, title: 'Explain in plain English.', description: 'We summarize what the evidence shows - and what it doesn’t.' },
  ],
  citations: [
    { id: 'c1', title: 'Vision Zero Action Plan 2023 Update', sourceType: 'report', page: '12-18', publishedAt: '2023-03-01' },
    { id: 'c2', title: 'Annual Road Safety Report 2024', sourceType: 'report', page: '8-15', publishedAt: '2024-03-01' },
    { id: 'c3', title: 'Bicycle Master Plan 2024', sourceType: 'report', page: '22-24', publishedAt: '2024-05-01' },
    { id: 'c4', title: 'Pedestrian Safety Action Plan 2022', sourceType: 'report', page: '10-14', publishedAt: '2022-09-01' },
  ],
  caveats: [
    { id: 'rates', title: 'Counts are not rates.', description: 'More crashes may reflect more people traveling, not necessarily more danger.' },
    { id: 'reporting', title: 'Not all crashes are reported equally.', description: 'Minor crashes are less likely to be reported, which can affect the totals.' },
    { id: 'causation', title: 'Trends do not prove cause.', description: 'Trends show patterns over time, not why something happened.' },
  ],
}
