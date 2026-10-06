import { useEffect, useMemo, useState } from 'react'
import type { DimKey, Dimension, Engineer, ImpactData, NaiveRow } from './types'
import './App.css'

const DIM_COLORS: Record<DimKey, string> = {
  delivery: 'var(--c-delivery)',
  review: 'var(--c-review)',
  stewardship: 'var(--c-stewardship)',
  sustained: 'var(--c-sustained)',
}

const LAYER_LABELS: Record<string, string> = {
  ingestion: 'Ingestion',
  'query-engine': 'Query engine',
  'data-pipeline': 'Data pipeline',
  'backend-core': 'Backend core',
  'backend-product': 'Backend product',
  'frontend-core': 'Frontend core',
  'frontend-product': 'Frontend product',
  'infra-ci': 'Infra / CI',
  tests: 'Tests',
  docs: 'Docs',
  other: 'Other',
}
const BACKEND_LAYERS = new Set(['ingestion', 'query-engine', 'data-pipeline', 'backend-core', 'backend-product'])

const fmt = new Intl.NumberFormat('en-US')

async function loadData(): Promise<ImpactData> {
  // Primary source is the Cloud Function; the static copy is a fallback so the page never fails to load.
  for (const url of ['/api/impact', '/impact.json']) {
    try {
      const res = await fetch(url)
      if (res.ok) return (await res.json()) as ImpactData
    } catch {
      /* try next source */
    }
  }
  throw new Error('Could not load analysis data')
}

export default function App() {
  const [data, setData] = useState<ImpactData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState(0)

  useEffect(() => {
    loadData().then(setData, (e: Error) => setError(e.message))
  }, [])

  if (error) return <div className="state">⚠️ {error}. Please refresh.</div>
  if (!data) return <div className="state">Loading analysis…</div>

  const eng = data.top[selected]
  return (
    <div className="page">
      <Header data={data} />
      <main className="grid">
        <section className="panel ranking" aria-label="Top engineers">
          <div className="panel-head">
            <h2>Top 5 most impactful engineers{data.tieAtCutoff && <span className="muted"> (+1 tied)</span>}</h2>
            <span className="muted small">Click to see the evidence</span>
          </div>
          <ol className="top-list">
            {data.top.map((e, i) => (
              <TopRow key={e.login} e={e} dims={data.dimensions} active={i === selected} onSelect={() => setSelected(i)} />
            ))}
          </ol>
          {data.tieAtCutoff && (
            <p className="note">
              #{data.top.length - 1} and #{data.top.length} are within 1 point. That's a statistical tie, so both are shown.
            </p>
          )}
          <Legend dims={data.dimensions} />
        </section>
        <Detail e={eng} dims={data.dimensions} />
      </main>
      <section className="lower">
        <Methodology data={data} />
        <WhyNotCounts data={data} />
        <Robustness data={data} />
      </section>
      <footer className="footer muted small">
        Data: {fmt.format(data.totals.mergedPRs)} merged PRs from github.com/{data.repo}, {data.window.start} → {data.window.end}.
        Generated {data.generatedAt.slice(0, 16).replace('T', ' ')} UTC. Data through {data.window.end}.
      </footer>
    </div>
  )
}

function Header({ data }: { data: ImpactData }) {
  const t = data.totals
  const steps = [
    { n: t.mergedPRs, l: 'merged PRs' },
    { n: t.humanPRs, l: 'by humans' },
    { n: t.scoredPRs, l: 'with real code' },
    { n: t.eligible, l: 'engineers ranked' },
  ]
  return (
    <header className="header">
      <div>
        <p className="eyebrow">PostHog · last {data.window.days} days</p>
        <h1>Who carries PostHog's critical path?</h1>
        <p className="lede">
          Impact = <b>hard work on the systems customers' data depends on</b>, plus <b>being the human gate</b> on
          teammates' risky changes, <b>owning</b> a critical area, and doing it <b>all quarter</b>. Raw PR, line and
          review counts are never scored directly.
        </p>
      </div>
      <div className="funnel" aria-label="Data funnel">
        {steps.map((s, i) => (
          <div key={s.l} className="funnel-step">
            <span className="funnel-n">{fmt.format(s.n)}</span>
            <span className="funnel-l">{s.l}</span>
            {i < steps.length - 1 && <span className="funnel-arrow">→</span>}
          </div>
        ))}
        <p className="muted small funnel-note">
          {fmt.format(t.aiReviews)} AI/bot reviews (stamphog, CodeRabbit, Greptile…) and {fmt.format(t.botPRs)} bot PRs excluded.
        </p>
      </div>
    </header>
  )
}

function StackBar({ e, dims, height = 10 }: { e: { dims: Engineer['dims'] }; dims: Dimension[]; height?: number }) {
  return (
    <div className="stack" style={{ height }} role="img"
      aria-label={dims.map((d) => `${d.label} ${Math.round(d.weight * e.dims[d.key].norm * 100)}`).join(', ')}>
      {dims.map((d) => (
        <span key={d.key} style={{ width: `${d.weight * e.dims[d.key].norm * 100}%`, background: DIM_COLORS[d.key] }}
          title={`${d.label}: ${(d.weight * e.dims[d.key].norm * 100).toFixed(1)} pts (percentile ${e.dims[d.key].pct})`} />
      ))}
    </div>
  )
}

function TopRow({ e, dims, active, onSelect }: { e: Engineer; dims: Dimension[]; active: boolean; onSelect: () => void }) {
  return (
    <li>
      <button className={`top-row ${active ? 'active' : ''}`} onClick={onSelect} aria-pressed={active}>
        <span className="rank">{e.rank}</span>
        <img className="avatar" src={e.avatar} alt="" width={40} height={40} loading="lazy" />
        <span className="who">
          <span className="login">
            {e.login}
            <span className={`badge ${e.robustness.badge === 'Stable' ? 'ok' : 'warn'}`}
              title={`Stayed in the top 5 in ${e.robustness.top5In} of ${e.robustness.of} alternative weightings`}>
              {e.robustness.badge}
            </span>
          </span>
          <span className="verdict">{e.verdict}</span>
          <StackBar e={e} dims={dims} />
        </span>
        <span className="score">
          {e.score.toFixed(1)}
          <span className="muted small">/100</span>
        </span>
      </button>
    </li>
  )
}

function Legend({ dims }: { dims: Dimension[] }) {
  return (
    <div className="legend">
      {dims.map((d) => (
        <span key={d.key} title={d.summary}>
          <i style={{ background: DIM_COLORS[d.key] }} /> {d.label} <span className="muted">({Math.round(d.weight * 100)}%)</span>
        </span>
      ))}
    </div>
  )
}

function Detail({ e, dims }: { e: Engineer; dims: Dimension[] }) {
  const layerTotal = Object.values(e.layerMix).reduce((a, b) => a + b, 0) || 1
  const backendShare = Object.entries(e.layerMix).filter(([l]) => BACKEND_LAYERS.has(l)).reduce((a, [, v]) => a + v, 0) / layerTotal
  const layers = Object.entries(e.layerMix).sort((a, b) => b[1] - a[1])
  return (
    <section className="panel detail" aria-label={`Evidence for ${e.login}`}>
      <div className="detail-head">
        <img className="avatar lg" src={e.avatar} alt="" width={56} height={56} />
        <div>
          <h2>
            <a href={`https://github.com/${e.login}`} target="_blank" rel="noreferrer">{e.login}</a>
            <span className="muted"> · #{e.rank} · {e.score.toFixed(1)}</span>
          </h2>
          <p className="muted small">
            {e.mergedPRs} merged PRs ({e.scoredPRs} scored) · reviewed {e.reviews.prsReviewed} teammates' PRs ·
            naive ranks: #{e.naiveRanks.prCount ?? '–'} by PR count, #{e.naiveRanks.linesChanged ?? '–'} by lines
          </p>
        </div>
      </div>

      <div className="dims">
        {dims.map((d) => (
          <div key={d.key} className="dim" title={d.formula}>
            <span className="dim-label"><i style={{ background: DIM_COLORS[d.key] }} />{d.label}</span>
            <span className="dim-val">{Math.round(e.dims[d.key].norm * 100)}</span>
            <span className="muted small">top {Math.max(1, 100 - e.dims[d.key].pct)}%</span>
          </div>
        ))}
      </div>
      <p className="equation mono small" aria-label="How this score is computed">
        {e.score.toFixed(1)} = 100 × ({dims.map((d) => `${Math.round(d.weight * 100)}% × ${e.dims[d.key].norm.toFixed(3)}`).join(' + ')})
      </p>

      <div className="detail-scroll">
        <h3>Where the work landed <span className="muted small">· {Math.round(backendShare * 100)}% backend / data systems</span></h3>
        <div className="layer-bar">
          {layers.map(([l, v]) => (
            <span key={l} className={BACKEND_LAYERS.has(l) ? 'be' : 'fe'} style={{ width: `${(v / layerTotal) * 100}%` }}
              title={`${LAYER_LABELS[l] ?? l}: ${Math.round((v / layerTotal) * 100)}%`} />
          ))}
        </div>
        <p className="muted small layer-legend">
          {layers.slice(0, 4).map(([l, v]) => `${LAYER_LABELS[l] ?? l} ${Math.round((v / layerTotal) * 100)}%`).join(' · ')}
        </p>

        <h3>Highest-impact PRs</h3>
        <ul className="prs">
          {e.topPRs.map((p) => (
            <li key={p.number}>
              <a href={p.url} target="_blank" rel="noreferrer">#{p.number} {p.title}</a>
              <span className="pr-meta">
                <b>{p.prScore.toFixed(1)}</b>
                <span className="muted"> = crit {p.critPR.toFixed(2)} × size {p.size.toFixed(1)}
                  {p.spread > 1 && ` × spread ${p.spread.toFixed(1)}`}{p.testBonus > 1 && ' × tests 1.1'}
                  {p.typeMult !== 1 && ` × type ${p.typeMult}`} · {p.primaryArea} · {p.mergedAt}</span>
              </span>
            </li>
          ))}
        </ul>

        {e.stewardship.length > 0 && (
          <>
            <h3>Critical areas they anchor</h3>
            <ul className="steward">
              {e.stewardship.map((s) => (
                <li key={s.area}>
                  <span className="steward-area">{s.area} <span className="muted small">crit {s.crit.toFixed(2)}</span></span>
                  <span className="share"><span style={{ width: `${s.share * 100}%` }} /></span>
                  <span className="small">
                    <b>{Math.round(s.share * 100)}%</b> of {s.nPRs} PRs' work · {s.authored} authored, {s.reviews} reviewed
                    {s.silo && <span className="badge warn">silo risk</span>}
                    {s.coContributors[0] && <span className="muted"> · next: {s.coContributors[0].login} {Math.round(s.coContributors[0].share * 100)}%</span>}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}

        <h3>As a reviewer</h3>
        <p className="small">
          <b>{e.reviews.changesRequested}</b> change requests · <b>{e.reviews.substantiveComments}</b> substantive comments ·{' '}
          <b>{e.reviews.substantiveApprovals}</b> approvals with feedback · {e.reviews.rubberStamps} plain approvals ·
          unblocked <b>{e.reviews.authorsUnblocked}</b> teammates · sole human reviewer on <b>{e.reviews.soleGate}</b> PRs
        </p>
        {e.reviews.excerpts.slice(0, 2).map((x) => (
          <blockquote key={x.number} className="excerpt">
            “{x.body}{x.body.length >= 220 ? '…' : ''}”
            <cite><a href={x.url} target="_blank" rel="noreferrer">#{x.number}</a> by {x.author} · PR score {x.prScore}</cite>
          </blockquote>
        ))}

        <h3>Cadence <span className="muted small">· meaningful weeks {e.weeks.filter(Boolean).length}/13</span></h3>
        <div className="weeks" aria-label="Weekly cadence">
          {e.weeks.map((w, i) => <span key={i} className={w ? 'on' : ''} title={`Week ${i + 1}: ${w ? 'meaningful contribution' : 'none'}`} />)}
        </div>

        <h3>Adjustments applied</h3>
        <ul className="adjust small">
          {e.adjustments.templated.slice(0, 2).map((t) => (
            <li key={t.sig}>Templated work: <b>{t.count}</b> near-identical PRs counted as <b>{t.countedAs}</b> <span className="muted mono">{t.sig.length > 90 ? t.sig.slice(0, 90) + '…' : t.sig}</span></li>
          ))}
          <li>{fmt.format(e.adjustments.noiseLinesRemoved)} lines of lockfiles / snapshots / generated code ignored</li>
          <li>{e.adjustments.zeroScorePRs} PRs scored zero (no hand-written code, or reverts)</li>
          <li>Revert rate {(e.adjustments.revertRate * 100).toFixed(1)}%{e.adjustments.revertedPRs.length > 0 && ` (${e.adjustments.revertedPRs.map((n) => '#' + n).join(', ')})`}</li>
          <li>{Math.round(e.adjustments.stamphogOnlyShare * 100)}% of their PRs were approved only by the stamphog AI reviewer</li>
        </ul>
      </div>
    </section>
  )
}

function Methodology({ data }: { data: ImpactData }) {
  const [showTiers, setShowTiers] = useState(false)
  return (
    <div className="panel">
      <h2>How the score works</h2>
      <ol className="method">
        {data.dimensions.map((d) => (
          <li key={d.key}>
            <span className="dim-label"><i style={{ background: DIM_COLORS[d.key] }} />{d.label} · {Math.round(d.weight * 100)}%</span>
            <p>{d.summary}</p>
            <p className="muted small">{d.formula}</p>
          </li>
        ))}
      </ol>
      <ol className="steps small">
        <li><b>Score every PR.</b> Criticality of the code it touches × log₂(1 + lines after noise removal) × spread, test and change-type factors, capped at 15. Templated repeats and the k-th PR in the same area are discounted.</li>
        <li><b>Add up four raw totals per engineer</b>, one per dimension above.</li>
        <li><b>Put each on 0–1 relative to the leader:</b> log(1 + you) ÷ log(1 + top engineer). Sustained is already a 0–1 share of weeks.</li>
        <li><b>Weight and add:</b> score = 100 × (40% Delivery + 25% Review + 20% Stewardship + 15% Sustained). Each engineer's panel shows this sum with their numbers.</li>
      </ol>
      <p className="small muted">
        <b>Criticality</b> comes from a
        published {data.tiers.length}-row path map. The capture endpoint, HogQL engine and ingestion pipeline are 1.0;
        generic UI components are 0.3; tests and stories count 0.3×. The rules apply to all {data.totals.eligible} engineers alike (≥ 5 scored PRs or ≥ 15 reviews).
      </p>
      <button className="link" onClick={() => setShowTiers((s) => !s)}>{showTiers ? 'Hide' : 'Show'} criticality map</button>
      {showTiers && (
        <div className="tiers">
          {data.tiers.map((t) => (
            <div key={t.prefix}><span className="mono">{t.prefix}</span><span>{t.area}</span><b>{t.crit.toFixed(2)}</b></div>
          ))}
        </div>
      )}
    </div>
  )
}

function NaiveList({ title, rows, unit }: { title: string; rows: NaiveRow[]; unit: string }) {
  return (
    <div className="naive">
      <h4>{title}</h4>
      <ol>
        {rows.map((r) => (
          <li key={r.login}>
            <span>{r.login}</span>
            <span className="muted small">{fmt.format(r.value)} {unit}</span>
            <span className={`small ${r.cpisRank && r.cpisRank <= 5 ? 'hit' : 'miss'}`}>{r.cpisRank ? `#${r.cpisRank}` : '–'}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

function WhyNotCounts({ data }: { data: ImpactData }) {
  return (
    <div className="panel">
      <h2>Why not just count?</h2>
      <p className="small">
        Here is what naive leaderboards would say, with each person's impact rank on the right. In this repo, AI agents let one person
        merge <b>{fmt.format(data.naive.prCount[0].value)}</b> PRs in 90 days, and lockfiles and generated code can add hundreds of
        thousands of lines. Counts mostly measure tooling, not impact.
      </p>
      <div className="naive-grid">
        <NaiveList title="By merged PRs" rows={data.naive.prCount} unit="PRs" />
        <NaiveList title="By lines changed" rows={data.naive.linesChanged} unit="lines" />
        <NaiveList title="By reviews given" rows={data.naive.reviewCount} unit="reviews" />
      </div>
    </div>
  )
}

function Robustness({ data }: { data: ImpactData }) {
  const top = useMemo(() => new Set(data.top.slice(0, 5).map((e) => e.login)), [data])
  return (
    <div className="panel">
      <h2>How sensitive is this to my choices?</h2>
      <p className="small">
        I re-ranked under 7 alternative assumptions. Names in <b>bold</b> are in the main top 5.{' '}
        {data.robustness.baseTop5InTop7Everywhere} of the top 5 stay in the top 7 under every variant; the rest trade places with a close pack of strong engineers, so read #4–#8 as near-equals.
      </p>
      <table className="robust">
        <tbody>
          {Object.entries(data.robustness.variants).map(([name, list]) => (
            <tr key={name}>
              <th>{name}</th>
              {list.map((l) => <td key={l} className={top.has(l) ? 'in' : ''}>{l}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
