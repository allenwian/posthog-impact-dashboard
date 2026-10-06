export type DimKey = 'delivery' | 'review' | 'stewardship' | 'sustained'

export interface Dimension {
  key: DimKey
  label: string
  weight: number
  summary: string
  formula: string
}

export interface DimScore {
  raw: number
  norm: number
  pct: number
}

export interface TopPR {
  number: number
  title: string
  url: string
  mergedAt: string
  prScore: number
  critPR: number
  size: number
  spread: number
  testBonus: number
  typeMult: number
  primaryArea: string
  layer: string
  E: number
  filesCounted: number
  filesDropped: number
  changedFiles: number
  truncated: boolean
}

export interface StewardArea {
  area: string
  crit: number
  nPRs: number
  share: number
  authored: number
  reviews: number
  silo: boolean
  coContributors: { login: string; share: number }[]
}

export interface ReviewExcerpt {
  number: number
  title: string
  author: string
  state: string
  url: string
  prScore: number
  body: string
}

export interface LeaderRow {
  rank: number
  login: string
  avatar: string
  score: number
  dims: Record<DimKey, DimScore>
  mergedPRs: number
  scoredPRs: number
  layerMix: Record<string, number>
}

export interface Engineer extends LeaderRow {
  topPRs: TopPR[]
  stewardship: StewardArea[]
  reviews: {
    changesRequested: number
    substantiveComments: number
    substantiveApprovals: number
    rubberStamps: number
    lightComments: number
    authorsUnblocked: number
    soleGate: number
    prsReviewed: number
    excerpts: ReviewExcerpt[]
  }
  weeks: boolean[]
  adjustments: {
    templated: { sig: string; count: number; countedAs: number }[]
    noiseLinesRemoved: number
    revertedPRs: number[]
    revertRate: number
    stamphogOnlyShare: number
    zeroScorePRs: number
  }
  robustness: { top5In: number; of: number; badge: 'Stable' | 'Weight-sensitive' }
  naiveRanks: { prCount: number | null; linesChanged: number | null; reviewCount: number | null }
  verdict: string
}

export interface NaiveRow {
  login: string
  value: number
  cpisRank: number | null
}

export interface ImpactData {
  generatedAt: string
  repo: string
  window: { start: string; end: string; days: number }
  totals: {
    mergedPRs: number
    humanPRs: number
    botPRs: number
    scoredPRs: number
    engineers: number
    eligible: number
    botAccounts: number
    aiReviews: number
    humanReviews: number
  }
  dimensions: Dimension[]
  top: Engineer[]
  tieAtCutoff: boolean
  leaderboard: LeaderRow[]
  robustness: { variants: Record<string, string[]>; baseTop5InTop7Everywhere: number }
  naive: { prCount: NaiveRow[]; linesChanged: NaiveRow[]; reviewCount: NaiveRow[] }
  tiers: { prefix: string; area: string; layer: string; crit: number }[]
}
