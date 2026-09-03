/**
 * Prototype-only mock data.
 * These values are used to develop the frontend and are not verified
 * Montgomery County crash statistics.
 */
import type { SavedInsight } from '@/types/insight'

export const mockSavedInsights: Record<string, SavedInsight> = {
  'silver-spring-pedestrian-safety': {
    id: 'silver-spring-pedestrian-safety',
    title: 'Silver Spring Pedestrian Safety Snapshot',
    tag: 'Saved insight',
    generatedAt: '2025-05-16',
    summary:
      'Pedestrian crashes in Silver Spring showed a modest decline in 2024, continuing a positive trend since 2022. Most crashes occur on a few key corridors - Georgia Ave, Colesville Rd, and University Blvd - especially at intersections and during evening hours. Targeted infrastructure and speed management can help prevent serious injuries and save lives.',
    metrics: [
      { label: 'Total pedestrian crashes', value: 156, description: 'in 2024' },
      { label: 'Change since 2022', value: '-10.3%', change: -10.3, changeDirection: 'down', changeIsPositive: true, description: 'fewer crashes (2022-2024)' },
      { label: 'Serious injuries', value: 34, description: 'in 2024, vs. 41 in 2022' },
    ],
    crashTrend: [
      { label: '2020', value: 142 },
      { label: '2021', value: 160 },
      { label: '2022', value: 174 },
      { label: '2023', value: 165 },
      { label: '2024', value: 156 },
    ],
    corridors: [
      { corridor: 'Georgia Ave (MD 97)', crashCount: 98 },
      { corridor: 'Colesville Rd (MD 384)', crashCount: 74 },
      { corridor: 'University Blvd (MD 193)', crashCount: 61 },
      { corridor: 'Spring St (MD 320)', crashCount: 48 },
      { corridor: '16th St (MD 650)', crashCount: 35 },
    ],
    findings: [
      'Pedestrian crashes declined 10% from 2022 to 2024.',
      'Most crashes occur at intersections, especially during evening hours (4-8 PM).',
      'Georgia Ave, Colesville Rd, and University Blvd account for 55% of crashes.',
      'Speeding and failure to yield are the leading contributing factors.',
    ],
    followUpPrompts: [
      'Where are the most dangerous intersections?',
      'How do crashes vary by time of day?',
      'What are the leading crash factors?',
      'How do Silver Spring pedestrian crashes compare to other areas?',
    ],
    citations: [
      { id: 'sc1', title: 'MDOT SHA Crash Data (2020-2024)', sourceType: 'dataset' },
      { id: 'sc2', title: 'Montgomery County Vision Zero Action Plan', sourceType: 'report' },
      { id: 'sc3', title: 'MoCo Police Crash Reports', sourceType: 'dataset' },
    ],
  },
}
